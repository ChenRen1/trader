"""Web 视图。"""

from __future__ import annotations

from decimal import Decimal
import re

from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from trader.database import Account, DailyMarketReport, Instrument, InstrumentPrice, Position
from trader.market.config import CN10Y, HKDCNH, USDCNH
from trader.market.services import IndexBasisService
from trader.market.source.provider import get_kline, get_spot_price


def _split_markdown_sections(markdown: str) -> dict[str, list[str]]:
    """按二级标题拆分日报 Markdown。"""
    sections: dict[str, list[str]] = {}
    current_title = ""
    current_lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current_title:
                sections[current_title] = current_lines
            current_title = line.removeprefix("## ").strip()
            current_lines = []
            continue
        if current_title:
            current_lines.append(line)

    if current_title:
        sections[current_title] = current_lines
    return sections


def _parse_hs300_sector_summary(lines: list[str]) -> tuple[str, list[dict[str, str]]]:
    """将沪深300行业统计拆成卡片数据。"""
    intro = ""
    cards: list[dict[str, str]] = []

    for line in lines:
        normalized = line.lstrip("- ").strip()
        if "样本范围" in normalized and not intro:
            intro = normalized
            continue

        match = re.match(
            r"^(?P<sector>[^：]+)：样本\s+(?P<sample>[^，]+)，上涨\s+(?P<up>\d+)，下跌\s+(?P<down>\d+)，平盘\s+(?P<flat>\d+)，均值\s+(?P<mean>[^，]+)，中位数\s+(?P<median>.+)$",
            normalized,
        )
        if match:
            cards.append(
                {
                    "sector": match.group("sector"),
                    "sample": match.group("sample"),
                    "up": match.group("up"),
                    "down": match.group("down"),
                    "flat": match.group("flat"),
                    "mean": match.group("mean"),
                    "median": match.group("median"),
                }
            )
            continue

        simple_match = re.match(r"^(?P<sector>[^：]+)：样本\s+(?P<sample>.+)$", normalized)
        if simple_match:
            cards.append(
                {
                    "sector": simple_match.group("sector"),
                    "sample": simple_match.group("sample"),
                    "up": "-",
                    "down": "-",
                    "flat": "-",
                    "mean": "-",
                    "median": "-",
                }
            )

    return intro, cards


def _parse_conclusion_cards(lines: list[str]) -> list[dict[str, str]]:
    """解析核心结论卡片。"""
    cards: list[dict[str, str]] = []
    for line in lines:
        normalized = line.strip()
        if not normalized.startswith("<p>• "):
            continue
        text = re.sub(r"</?p>", "", normalized).removeprefix("• ").strip()
        title, _, detail = text.partition(":")
        summary, _, tag = detail.rpartition("->")
        cards.append(
            {
                "title": title.strip() or "核心结论",
                "value": tag.rstrip("。").strip() if tag else "-",
                "detail": summary.strip() if summary else detail.strip(),
            }
        )
    return cards


def _parse_sector_distribution_cards(lines: list[str]) -> list[dict[str, str]]:
    """解析证券板块涨跌分布卡片。"""
    cards: list[dict[str, str]] = []
    for line in lines:
        normalized = line.lstrip("- ").strip()
        if normalized.startswith("板块："):
            cards.append({"title": "样本概览", "value": "证券", "detail": normalized.removeprefix("板块：").strip()})
        elif normalized.startswith("上涨："):
            cards.append({"title": "上涨分布", "value": "上涨", "detail": normalized.removeprefix("上涨：").strip()})
        elif normalized.startswith("下跌："):
            cards.append({"title": "下跌分布", "value": "下跌", "detail": normalized.removeprefix("下跌：").strip()})
        elif normalized.startswith("平盘："):
            cards.append({"title": "平盘数量", "value": normalized.removeprefix("平盘：").strip(), "detail": "当日平盘样本数"})
    return cards


def _parse_basis_cards(lines: list[str]) -> tuple[str, list[dict[str, str]]]:
    """解析股指期货基差卡片。"""
    calculated_at = ""
    cards: list[dict[str, str]] = []

    for line in lines:
        normalized = line.lstrip("- ").strip()
        if normalized.startswith("计算时间："):
            calculated_at = normalized.removeprefix("计算时间：").strip()
            continue

        match = re.match(
            r"^(?P<title>[^:]+):\s+期货\s+(?P<future>[^，]+)，现货\s+(?P<spot>[^，]+)，基差\s+(?P<basis>[^（]+)\s+\((?P<basis_pct>[^)]+)\)，口径\s+(?P<source>.+)$",
            normalized,
        )
        if not match:
            continue

        cards.append(
            {
                "title": match.group("title"),
                "value": match.group("basis_pct"),
                "detail": (
                    f"期货 {match.group('future')} / 现货 {match.group('spot')} / "
                    f"基差 {match.group('basis').strip()} / {match.group('source')}"
                ),
            }
        )

    return calculated_at, cards


def _parse_daily_report_summary(report: DailyMarketReport | None) -> dict[str, object]:
    """将日报正文转换为首页摘要结构。"""
    if report is None:
        return {
            "conclusion_cards": [],
            "sector_distribution_cards": [],
            "hs300_intro": "",
            "hs300_cards": [],
            "basis_calculated_at": "",
            "basis_cards": [],
        }

    if report.markdown_content:
        sections = _split_markdown_sections(report.markdown_content)
        hs300_intro, hs300_cards = _parse_hs300_sector_summary(sections.get("沪深300成分股行业涨跌幅统计", []))
        basis_calculated_at, basis_cards = _parse_basis_cards(sections.get("股指期货基差（期货-现货）", []))
        conclusion_cards = _parse_conclusion_cards(sections.get("核心结论", []))
        sector_distribution_cards = _parse_sector_distribution_cards(sections.get("证券板块涨跌幅分布（1% / 3% / 5%）", []))
    else:
        hs300_intro, hs300_cards = _parse_hs300_sector_summary(report.hs300_sector_summary.splitlines())
        basis_calculated_at = ""
        basis_cards = []
        conclusion_cards = []
        sector_distribution_cards = []

    return {
        "conclusion_cards": conclusion_cards,
        "sector_distribution_cards": sector_distribution_cards,
        "hs300_intro": hs300_intro,
        "hs300_cards": hs300_cards,
        "basis_calculated_at": basis_calculated_at,
        "basis_cards": basis_cards,
    }


def home(request: HttpRequest) -> HttpResponse:
    """首页视图。"""
    accounts = Account.objects.order_by("account_code")
    open_positions = (
        Position.objects.select_related("account", "instrument")
        .filter(status=Position.Status.OPEN)
        .order_by("-market_value", "-updated_at")
    )
    position_overview_queryset = (
        open_positions.values(
            "instrument__symbol",
            "instrument__name",
            "instrument__market",
            "pricing_currency",
        )
        .annotate(
            account_count=Count("account", distinct=True),
            position_count=Count("id"),
            total_quantity=Coalesce(Sum("quantity"), Value(Decimal("0"))),
            total_cost_basis=Coalesce(Sum("cost_basis"), Value(Decimal("0"))),
            total_market_value=Coalesce(Sum("market_value"), Value(Decimal("0"))),
            total_unrealized_pnl=Coalesce(Sum("unrealized_pnl"), Value(Decimal("0"))),
        )
        .order_by("-total_market_value", "instrument__symbol")
    )

    totals = accounts.aggregate(
        total_equity=Sum("total_equity"),
        available_cash=Sum("available_cash"),
        frozen_cash=Sum("frozen_cash"),
        liability=Sum("liability"),
        total_market_value=Sum("total_market_value"),
        total_unrealized_pnl=Sum("total_unrealized_pnl"),
    )
    total_market_value = totals.get("total_market_value") or Decimal("0")
    position_overview = list(position_overview_queryset[:12])
    for item in position_overview:
        cost_basis = item["total_cost_basis"] or Decimal("0")
        unrealized_pnl = item["total_unrealized_pnl"] or Decimal("0")
        item["pnl_ratio"] = None
        item["weight_ratio"] = None
        if cost_basis not in {None, Decimal("0")}:
            item["pnl_ratio"] = (unrealized_pnl / cost_basis * Decimal("100")).quantize(Decimal("0.01"))
        if total_market_value not in {None, Decimal("0")}:
            item["weight_ratio"] = (item["total_market_value"] / total_market_value * Decimal("100")).quantize(
                Decimal("0.01")
            )
    position_totals = open_positions.aggregate(
        position_count=Count("id"),
        total_quantity=Sum("quantity"),
    )
    side_counts = open_positions.values("side").annotate(count=Count("id"))
    side_summary = {item["side"]: item["count"] for item in side_counts}
    latest_report = DailyMarketReport.objects.order_by("-report_date", "-id").first()
    daily_summary = _parse_daily_report_summary(latest_report)

    macro_watchlist = [USDCNH, HKDCNH, CN10Y]
    macro_cards: list[dict[str, object]] = []
    for item in macro_watchlist:
        market_map = {
            "FX": Instrument.Market.MACRO,
            "BOND": Instrument.Market.MACRO,
        }
        model_market = market_map.get(item.market, item.market)
        instrument = Instrument.objects.filter(symbol=item.symbol, market=model_market).first()
        price = None
        if instrument is not None:
            price = (
                InstrumentPrice.objects.filter(
                    instrument=instrument,
                    bar_type=InstrumentPrice.BarType.SPOT,
                )
                .order_by("-priced_at", "-id")
                .first()
            )
        macro_cards.append(
            {
                "name": item.name,
                "symbol": item.symbol,
                "market": item.market,
                "last_price": price.last_price if price is not None else None,
                "prev_close": price.prev_close if price is not None else None,
                "source": price.source if price is not None else "",
            }
        )

    return render(
        request,
        "trader/home.html",
        {
            "accounts": accounts,
            "position_overview": position_overview,
            "latest_report": latest_report,
            "daily_summary": daily_summary,
            "macro_cards": macro_cards,
            "summary": {
                "account_count": accounts.count(),
                "position_count": position_totals.get("position_count") or 0,
                "instrument_count": position_overview_queryset.count(),
                "available_cash": totals.get("available_cash") or Decimal("0"),
                "frozen_cash": totals.get("frozen_cash") or Decimal("0"),
                "liability": totals.get("liability") or Decimal("0"),
                "total_market_value": total_market_value,
                "total_unrealized_pnl": totals.get("total_unrealized_pnl") or Decimal("0"),
                "total_equity": totals.get("total_equity") or Decimal("0"),
                "long_count": side_summary.get(Position.Side.LONG, 0),
                "short_count": side_summary.get(Position.Side.SHORT, 0),
            },
        },
    )


def market_chart_index(request: HttpRequest) -> HttpResponse:
    """行情图入口页。"""
    watchlist = [
        {"name": "沪深300", "market": "CN", "symbol": "000300"},
        {"name": "上证50", "market": "CN", "symbol": "000016"},
        {"name": "中证500", "market": "CN", "symbol": "000905"},
        {"name": "中证1000", "market": "CN", "symbol": "000852"},
        {"name": "创业板指", "market": "CN", "symbol": "399006"},
        {"name": "科创50", "market": "CN", "symbol": "000688"},
        {"name": "恒生科技", "market": "HK", "symbol": "HSTECH"},
    ]
    return render(request, "trader/market_chart_index.html", {"watchlist": watchlist})


def market_chart_page(request: HttpRequest, market: str, symbol: str) -> HttpResponse:
    """单标的行情图页面。"""
    return render(
        request,
        "trader/market_chart.html",
        {
            "market": market.upper(),
            "symbol": symbol.upper(),
        },
    )


def market_chart_data(request: HttpRequest, market: str, symbol: str) -> JsonResponse:
    """单标的 K 线与现价接口。"""
    market_key = market.upper()
    symbol_key = symbol.upper()

    try:
        bars = get_kline(symbol_key, market_key, limit=120)
    except Exception as exc:
        return JsonResponse({"error": f"kline unavailable: {exc}"}, status=502)

    try:
        spot = get_spot_price(symbol_key, market_key)
    except Exception:
        spot = None

    def _float(value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except Exception:
            return None

    basis_row = None
    if market_key == "CN":
        basis_row = IndexBasisService.calculate_for_spot_symbol(symbol_key)

    payload = {
        "symbol": symbol_key,
        "market": market_key,
        "spot": (
            {
                "last_price": _float(spot.get("last_price")),
                "prev_close": _float(spot.get("prev_close")),
                "change_pct": _float(spot.get("change_pct")),
                "source": str(spot.get("source", "")),
            }
            if spot is not None
            else None
        ),
        "bars": [
            {
                "time": str(item["date"]),
                "open": _float(item["open"]),
                "high": _float(item["high"]),
                "low": _float(item["low"]),
                "close": _float(item["close"]),
                "volume": _float(item["volume"]),
            }
            for item in bars
        ],
        "basis": (
            {
                "future_code": basis_row.future_code,
                "future_price": _float(basis_row.future_close),
                "spot_price": _float(basis_row.spot_price),
                "basis": _float(basis_row.basis),
                "basis_pct": _float(basis_row.basis_pct),
                "trade_date": str(basis_row.trade_date) if basis_row.trade_date else None,
                "source": basis_row.future_source,
                "status": basis_row.status,
                "error": basis_row.error or None,
            }
            if basis_row is not None
            else None
        ),
    }
    return JsonResponse(payload)
