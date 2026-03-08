"""每日市场分析报告服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.utils import timezone

from trader.database.models import (
    DailyMarketReport,
    Instrument,
    InstrumentPrice,
)
from trader.market.config import INDEX_WATCHLIST, MarketInstrument
from trader.market.services.index_basis import IndexBasisService
from trader.market.services.sector_analytics import SectorAnalyticsService

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
    def render_markdown_report(
        cls,
        *,
        report_date: datetime | None = None,
        hs300_sector_lines: list[str] | None = None,
    ) -> str:
        now = report_date or timezone.localtime()
        rows = cls.collect_quotes()
        sector_distribution_lines = cls._render_sector_distribution_lines()
        resolved_hs300_sector_lines = hs300_sector_lines or cls._render_hs300_sector_lines()
        basis_lines = cls._render_index_basis_lines()

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
            "## 证券板块涨跌幅分布（1% / 3% / 5%）",
            *sector_distribution_lines,
            "",
            "## 沪深300成分股行业涨跌幅统计",
            *resolved_hs300_sector_lines,
            "",
            "## 股指期货基差（期货-现货）",
            *basis_lines,
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
    def _render_sector_distribution_lines(cls) -> list[str]:
        try:
            stats = SectorAnalyticsService.summarize_sector_change_stats(sector_name="证券")
            d = stats["distribution"]
            return [
                f"- 板块：{stats['sector_code']} 证券，样本 {stats['valid_change_count']} / {stats['total_constituents']}，均值 {stats['mean_change_pct']}%，中位数 {stats['median_change_pct']}%",
                f"- 上涨：>=5% {d['up_ge_5']}，[3%,5%) {d['up_3_to_5']}，[1%,3%) {d['up_1_to_3']}，(0,1%) {d['up_0_to_1']}",
                f"- 下跌：<=-5% {d['down_ge_5']}，[-5%,-3%) {d['down_3_to_5']}，[-3%,-1%) {d['down_1_to_3']}，(-1%,0) {d['down_0_to_1']}",
                f"- 平盘：{d['flat']}",
            ]
        except Exception as exc:
            return [f"- 数据不可用：{exc}"]

    @classmethod
    def _render_hs300_sector_lines(cls, *, top: int = 10) -> list[str]:
        try:
            rows = SectorAnalyticsService.summarize_hs300_sector_change_stats()
            if not rows:
                return ["- 数据不可用：无行业统计结果"]
            lines = [
                f"- 样本范围：沪深300成分股，按行业汇总，展示前 {min(top, len(rows))} 个行业（按平均涨跌幅排序）",
            ]
            for row in rows[:top]:
                lines.append(
                    f"- {row['sector_name']}：样本 {row['valid_change_count']} / {row['constituent_count']}，"
                    f"上涨 {row['up_count']}，下跌 {row['down_count']}，平盘 {row['flat_count']}，"
                    f"均值 {row['mean_change_pct']}%，中位数 {row['median_change_pct']}%"
                )
            return lines
        except Exception as exc:
            return [f"- 数据不可用：{exc}"]

    @classmethod
    def _render_index_basis_lines(cls) -> list[str]:
        try:
            snapshot = IndexBasisService.calculate_snapshot()
            if not snapshot.rows:
                return ["- 数据不可用：无基差结果"]
            lines = [f"- 计算时间：{snapshot.calculated_at:%Y-%m-%d %H:%M:%S}"]
            for row in snapshot.rows:
                if row.status != "ok":
                    lines.append(f"- {row.future_code}/{row.name}: 状态 {row.status}，原因 {row.error or '-'}")
                    continue
                basis_text = f"{row.basis:+.2f}" if row.basis is not None else "-"
                basis_pct_text = f"{row.basis_pct:+.2f}%" if row.basis_pct is not None else "-"
                future_text = f"{row.future_close:.2f}" if row.future_close is not None else "-"
                spot_text = f"{row.spot_price:.2f}" if row.spot_price is not None else "-"
                lines.append(
                    f"- {row.future_code}/{row.name}: 期货 {future_text}，现货 {spot_text}，基差 {basis_text} ({basis_pct_text})，口径 {row.future_source}"
                )
            return lines
        except Exception as exc:
            return [f"- 数据不可用：{exc}"]

    @classmethod
    def _build_hs300_sector_summary(cls, *, top: int = 10) -> str:
        lines = cls._render_hs300_sector_lines(top=top)
        return "\n".join(lines)

    @classmethod
    def save_daily_report(
        cls,
        *,
        report_date: datetime | None = None,
        markdown_content: str | None = None,
        hs300_sector_summary: str | None = None,
    ) -> DailyMarketReport:
        now = report_date or timezone.localtime()
        markdown = markdown_content or cls.render_markdown_report(report_date=now)
        hs300_summary = hs300_sector_summary or cls._build_hs300_sector_summary()
        report, _ = DailyMarketReport.objects.update_or_create(
            report_date=now.date(),
            defaults={
                "reported_at": now,
                "hs300_sector_summary": hs300_summary,
                "markdown_content": markdown,
            },
        )
        return report

    @classmethod
    def write_daily_report(cls, *, output_dir: Path | None = None) -> Path:
        now = timezone.localtime()
        target_dir = output_dir or (Path("trader") / "market" / "reports")
        target_dir.mkdir(parents=True, exist_ok=True)
        output = target_dir / f"daily_market_report_{now.strftime('%Y%m%d')}.md"
        hs300_lines = cls._render_hs300_sector_lines()
        hs300_summary = "\n".join(hs300_lines)
        markdown = cls.render_markdown_report(report_date=now, hs300_sector_lines=hs300_lines)
        cls.save_daily_report(
            report_date=now,
            markdown_content=markdown,
            hs300_sector_summary=hs300_summary,
        )
        output.write_text(markdown, encoding="utf-8")
        return output
