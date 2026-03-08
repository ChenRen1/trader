"""生成高股息策略买入候选报告。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from trader.database import Instrument, InstrumentPrice
from trader.strategy.services import DividendYieldStrategyConfig


class Command(BaseCommand):
    help = "基于 instrument_prices 年报股息率字段，生成高股息买入候选报告。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--threshold-pct",
            type=str,
            default="",
            help="买入阈值(%)，默认读取策略配置 buy_threshold。",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="",
            help="报告输出目录，默认 trader/strategy/reports。",
        )

    def handle(self, *args, **options):
        config = DividendYieldStrategyConfig()
        threshold_pct = (
            Decimal(options["threshold_pct"])
            if str(options["threshold_pct"]).strip()
            else (config.buy_threshold * Decimal("100")).quantize(Decimal("0.01"))
        )

        target_dir = Path(options["output_dir"]) if options["output_dir"] else (Path("trader") / "strategy" / "reports")
        target_dir.mkdir(parents=True, exist_ok=True)

        now = timezone.localtime()
        rows: list[dict[str, object]] = []

        instruments = Instrument.objects.filter(
            market=Instrument.Market.CN,
            instrument_type=Instrument.InstrumentType.STOCK,
            is_high_dividend=True,
        ).order_by("symbol")
        for instrument in instruments:
            latest = (
                InstrumentPrice.objects.filter(
                    instrument=instrument,
                    bar_type=InstrumentPrice.BarType.SPOT,
                )
                .order_by("-priced_at", "-id")
                .first()
            )
            if latest is None:
                continue
            y = latest.annual_dividend_yield_pct
            if y is None:
                continue
            if y < threshold_pct:
                continue
            rows.append(
                {
                    "symbol": instrument.symbol,
                    "name": instrument.name,
                    "last_price": latest.last_price,
                    "annual_report": latest.annual_dividend_report,
                    "cash_per_10": latest.annual_cash_dividend_per_10,
                    "dps": latest.annual_dividend_per_share,
                    "yield_pct": y,
                    "priced_at": latest.priced_at,
                }
            )

        rows.sort(key=lambda item: (Decimal(str(item["yield_pct"])), str(item["symbol"])), reverse=True)
        report_path = target_dir / f"dividend_buy_candidates_{now.strftime('%Y%m%d_%H%M%S')}.md"
        report_path.write_text(self._render_markdown(now, threshold_pct, rows), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"报告已生成: {report_path}"))
        self.stdout.write(
            self.style.SUCCESS(f"阈值(%)={threshold_pct}，候选数量={len(rows)}")
        )

    @staticmethod
    def _render_markdown(
        now: datetime,
        threshold_pct: Decimal,
        rows: list[dict[str, object]],
    ) -> str:
        lines = [
            f"# 高股息策略买入候选报告（{now.strftime('%Y-%m-%d %H:%M:%S')}）",
            "",
            f"- 口径：最近完整年报分红 / 当前价",
            f"- 买入阈值：{threshold_pct}%",
            f"- 候选数：{len(rows)}",
            "",
            "| 代码 | 名称 | 现价 | 年报 | 每10股分红 | 每股分红 | 股息率(%) | 价格时间 |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | --- |",
        ]
        for item in rows:
            lines.append(
                "| "
                f"{item['symbol']} | {item['name']} | "
                f"{Decimal(str(item['last_price'])):.4f} | "
                f"{item['annual_report'] or '-'} | "
                f"{Decimal(str(item['cash_per_10'])):.4f} | "
                f"{Decimal(str(item['dps'])):.4f} | "
                f"{Decimal(str(item['yield_pct'])):.4f} | "
                f"{item['priced_at']} |"
            )
        return "\n".join(lines) + "\n"
