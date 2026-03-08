"""每日市场分析报告服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.utils import timezone

from trader.database.models import (
    DailyMarketIndicator,
    DailyMarketQuote,
    DailyMarketSnapshot,
    Instrument,
    InstrumentPrice,
)
from trader.market.config import INDEX_WATCHLIST, MarketInstrument

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class QuoteRow:
    """报告明细行。"""

    key: str
    name: str
    symbol: str
    market: str
    last_price: Decimal | None
    prev_close: Decimal | None
    change_pct: Decimal | None
    priced_at: datetime | None
    source: str
    status: str


class MarketDailyReportService:
    """基于数据库最新现价生成日报。"""

    _KEY_ALIAS = {
        "SH_CORE": "INDEX_50",
        "INDEX_300": "INDEX_300",
        "CSI_2000": "CSI_2000",
        "CHINEXT": "CHINEXT",
        "HSTECH": "HSTECH",
    }

    _MARKET_MAP = {
        "CN": Instrument.Market.CN,
        "HK": Instrument.Market.HK,
        "FX": Instrument.Market.MACRO,
        "BOND": Instrument.Market.MACRO,
    }

    @classmethod
    def _resolve_instrument(cls, item: MarketInstrument) -> Instrument | None:
        model_market = cls._MARKET_MAP.get(item.market.strip().upper())
        if model_market is None:
            return None
        return Instrument.objects.filter(symbol=item.symbol, market=model_market).first()

    @staticmethod
    def _compute_change_pct(last_price: Decimal | None, prev_close: Decimal | None) -> Decimal | None:
        if last_price is None or prev_close in {None, ZERO}:
            return None
        return ((last_price - prev_close) / prev_close * HUNDRED).quantize(Decimal("0.01"))

    @staticmethod
    def _latest_spot_price(instrument: Instrument) -> InstrumentPrice | None:
        return (
            InstrumentPrice.objects.filter(
                instrument=instrument,
                bar_type=InstrumentPrice.BarType.SPOT,
            )
            .order_by("-priced_at", "-id")
            .first()
        )

    @classmethod
    def collect_quotes(cls) -> list[QuoteRow]:
        rows: list[QuoteRow] = []
        for item in INDEX_WATCHLIST:
            instrument = cls._resolve_instrument(item)
            if instrument is None:
                rows.append(
                    QuoteRow(
                        key=item.key,
                        name=item.name,
                        symbol=item.symbol,
                        market=item.market,
                        last_price=None,
                        prev_close=None,
                        change_pct=None,
                        priced_at=None,
                        source="",
                        status="missing_instrument",
                    )
                )
                continue

            spot = cls._latest_spot_price(instrument)
            if spot is None:
                rows.append(
                    QuoteRow(
                        key=item.key,
                        name=item.name,
                        symbol=item.symbol,
                        market=item.market,
                        last_price=None,
                        prev_close=None,
                        change_pct=None,
                        priced_at=None,
                        source="",
                        status="missing_price",
                    )
                )
                continue

            rows.append(
                QuoteRow(
                    key=item.key,
                    name=item.name,
                    symbol=item.symbol,
                    market=item.market,
                    last_price=spot.last_price,
                    prev_close=spot.prev_close,
                    change_pct=cls._compute_change_pct(spot.last_price, spot.prev_close),
                    priced_at=spot.priced_at,
                    source=spot.source,
                    status="ok",
                )
            )
        return rows

    @staticmethod
    def _format_pct(value: Decimal | None) -> str:
        if value is None:
            return "-"
        return f"{value:+.2f}%"

    @staticmethod
    def _format_price(value: Decimal | None) -> str:
        if value is None:
            return "-"
        return f"{value:.4f}"

    @staticmethod
    def _pick(rows: list[QuoteRow], key: str) -> QuoteRow | None:
        for row in rows:
            if row.key == key:
                return row
        return None

    @classmethod
    def _build_indicator_payloads(cls, rows: list[QuoteRow]) -> list[dict[str, object]]:
        row_300 = cls._pick(rows, "INDEX_300")
        row_2000 = cls._pick(rows, "CSI_2000")
        row_sh = cls._pick(rows, "INDEX_50")
        row_cy = cls._pick(rows, "CHINEXT")
        row_hk = cls._pick(rows, "HSTECH")

        indicator_payloads: list[dict[str, object]] = []

        diff_300_2000 = None
        category_300_2000 = "数据不足"
        if row_300 and row_2000 and row_300.change_pct is not None and row_2000.change_pct is not None:
            diff_300_2000 = (row_300.change_pct - row_2000.change_pct).copy_abs().quantize(Decimal("0.01"))
            if diff_300_2000 >= Decimal("2"):
                category_300_2000 = "严重分歧"
            elif diff_300_2000 >= Decimal("1"):
                category_300_2000 = "较重分歧"
            elif diff_300_2000 >= Decimal("0.5"):
                category_300_2000 = "存在分歧"
            else:
                category_300_2000 = "分歧不明显"
        indicator_payloads.append(
            {
                "indicator_key": DailyMarketIndicator.IndicatorKey.INDEX_300_VS_CSI_2000,
                "title": "沪深300/中证2000",
                "left_key": "INDEX_300",
                "right_key": "CSI_2000",
                "left_value": row_300.change_pct if row_300 else None,
                "right_value": row_2000.change_pct if row_2000 else None,
                "diff_value": diff_300_2000,
                "category": category_300_2000,
                "summary": cls._analyze_300_vs_2000(rows),
            }
        )

        diff_sh_cy = None
        category_sh_cy = "数据不足"
        if row_sh and row_cy and row_sh.change_pct is not None and row_cy.change_pct is not None:
            diff_sh_cy = (row_sh.change_pct - row_cy.change_pct).copy_abs().quantize(Decimal("0.01"))
            category_sh_cy = (
                "共振（单边行情更强）"
                if (row_sh.change_pct >= ZERO and row_cy.change_pct >= ZERO)
                or (row_sh.change_pct <= ZERO and row_cy.change_pct <= ZERO)
                else "分化（市场存在分歧）"
            )
        indicator_payloads.append(
            {
                "indicator_key": DailyMarketIndicator.IndicatorKey.INDEX_50_VS_CHINEXT,
                "title": "上证核心/创业板",
                "left_key": "INDEX_50",
                "right_key": "CHINEXT",
                "left_value": row_sh.change_pct if row_sh else None,
                "right_value": row_cy.change_pct if row_cy else None,
                "diff_value": diff_sh_cy,
                "category": category_sh_cy,
                "summary": cls._analyze_sh_vs_chinext(rows),
            }
        )

        spread_sh_hk = None
        category_sh_hk = "数据不足"
        if row_sh and row_hk and row_sh.change_pct is not None and row_hk.change_pct is not None:
            spread_sh_hk = (row_sh.change_pct - row_hk.change_pct).quantize(Decimal("0.01"))
            category_sh_hk = "同向" if row_sh.change_pct * row_hk.change_pct >= ZERO else "反向"
        indicator_payloads.append(
            {
                "indicator_key": DailyMarketIndicator.IndicatorKey.INDEX_50_VS_HSTECH,
                "title": "上证核心/恒科",
                "left_key": "INDEX_50",
                "right_key": "HSTECH",
                "left_value": row_sh.change_pct if row_sh else None,
                "right_value": row_hk.change_pct if row_hk else None,
                "diff_value": spread_sh_hk,
                "category": category_sh_hk,
                "summary": cls._analyze_sh_vs_hstech(rows),
            }
        )

        return indicator_payloads

    @classmethod
    def save_daily_snapshot(cls, *, report_date: datetime | None = None) -> DailyMarketSnapshot:
        now = report_date or timezone.localtime()
        rows = cls.collect_quotes()
        snapshot, _ = DailyMarketSnapshot.objects.update_or_create(
            report_date=now.date(),
            defaults={
                "reported_at": now,
                "quote_count": len(rows),
                "ok_count": sum(1 for row in rows if row.status == "ok"),
                "missing_instrument_count": sum(1 for row in rows if row.status == "missing_instrument"),
                "missing_price_count": sum(1 for row in rows if row.status == "missing_price"),
            },
        )

        snapshot.quotes.all().delete()
        snapshot.indicators.all().delete()

        for row in rows:
            instrument = cls._resolve_instrument(
                next(item for item in INDEX_WATCHLIST if item.key == row.key)
            )
            DailyMarketQuote.objects.create(
                snapshot=snapshot,
                instrument=instrument,
                key=row.key,
                name=row.name,
                symbol=row.symbol,
                market=row.market,
                last_price=row.last_price,
                prev_close=row.prev_close,
                change_pct=row.change_pct,
                priced_at=row.priced_at,
                source=row.source,
                status=row.status,
            )

        for payload in cls._build_indicator_payloads(rows):
            DailyMarketIndicator.objects.create(snapshot=snapshot, **payload)

        return snapshot

    @classmethod
    def _analyze_300_vs_2000(cls, rows: list[QuoteRow]) -> str:
        row_300 = cls._pick(rows, "INDEX_300")
        row_2000 = cls._pick(rows, "CSI_2000")
        if row_300 is None or row_2000 is None:
            return "沪深300/中证2000: 配置缺失。"
        if row_300.change_pct is None or row_2000.change_pct is None:
            return "沪深300/中证2000: 数据不足，无法判断机构与游资分歧。"

        diff = (row_300.change_pct - row_2000.change_pct).copy_abs()
        if diff >= Decimal("2"):
            level = "严重分歧"
        elif diff >= Decimal("1"):
            level = "较重分歧"
        elif diff >= Decimal("0.5"):
            level = "存在分歧"
        else:
            level = "分歧不明显"
        return (
            "沪深300/中证2000: "
            f"涨跌幅分别为 {row_300.change_pct:+.2f}% / {row_2000.change_pct:+.2f}%，"
            f"差值 {diff:.2f}% -> {level}。"
        )

    @classmethod
    def _analyze_sh_vs_chinext(cls, rows: list[QuoteRow]) -> str:
        row_sh = cls._pick(rows, "INDEX_50")
        row_cy = cls._pick(rows, "CHINEXT")
        if row_sh is None or row_cy is None:
            return "上证核心/创业板: 配置缺失。"
        if row_sh.change_pct is None or row_cy.change_pct is None:
            return "上证核心/创业板: 数据不足，无法判断分化或共振。"

        same_direction = (row_sh.change_pct >= ZERO and row_cy.change_pct >= ZERO) or (
            row_sh.change_pct <= ZERO and row_cy.change_pct <= ZERO
        )
        state = "共振（单边行情更强）" if same_direction else "分化（市场存在分歧）"
        return (
            "上证核心/创业板: "
            f"涨跌幅 {row_sh.change_pct:+.2f}% / {row_cy.change_pct:+.2f}% -> {state}。"
        )

    @classmethod
    def _analyze_sh_vs_hstech(cls, rows: list[QuoteRow]) -> str:
        row_sh = cls._pick(rows, "INDEX_50")
        row_hk = cls._pick(rows, "HSTECH")
        if row_sh is None or row_hk is None:
            return "上证核心/恒科: 配置缺失。"
        if row_sh.change_pct is None or row_hk.change_pct is None:
            return "上证核心/恒科: 数据不足，无法判断内外资风格差异。"

        spread = (row_sh.change_pct - row_hk.change_pct).quantize(Decimal("0.01"))
        relation = "同向" if row_sh.change_pct * row_hk.change_pct >= ZERO else "反向"
        return (
            "上证核心/恒科: "
            f"涨跌幅 {row_sh.change_pct:+.2f}% / {row_hk.change_pct:+.2f}%，"
            f"相对差 {spread:+.2f}%（{relation}）。"
        )

    @classmethod
    def render_markdown_report(cls, *, report_date: datetime | None = None) -> str:
        now = report_date or timezone.localtime()
        rows = cls.collect_quotes()

        header = [
            f"# 每日市场分析报告（{now.strftime('%Y-%m-%d')}）",
            "",
            "## 核心结论",
            '<div style="font-size: 20px; line-height: 1.7;">',
            f"<p>• {cls._analyze_300_vs_2000(rows)}</p>",
            f"<p>• {cls._analyze_sh_vs_chinext(rows)}</p>",
            f"<p>• {cls._analyze_sh_vs_hstech(rows)}</p>",
            "</div>",
            "",
            "## 标的行情明细",
            "| 名称 | 代码 | 市场 | 现价 | 涨跌幅 | 状态 |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]

        lines: list[str] = []
        for row in rows:
            lines.append(
                "| "
                f"{row.name} | {row.symbol} | {row.market} | "
                f"{cls._format_price(row.last_price)} | {cls._format_pct(row.change_pct)} | {row.status} |"
            )

        return "\n".join(header + lines) + "\n"

    @classmethod
    def write_daily_report(cls, *, output_dir: Path | None = None) -> Path:
        now = timezone.localtime()
        cls.save_daily_snapshot(report_date=now)
        target_dir = output_dir or (Path("trader") / "market" / "reports")
        target_dir.mkdir(parents=True, exist_ok=True)
        output = target_dir / f"daily_market_report_{now.strftime('%Y%m%d')}.md"
        output.write_text(cls.render_markdown_report(report_date=now), encoding="utf-8")
        return output
