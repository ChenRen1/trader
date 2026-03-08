"""按年报口径计算高股息标的股息率。"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from trader.strategy.services import AnnualReportDividendYieldService


class Command(BaseCommand):
    help = "使用最近完整年报分红 / 当前价，计算高股息标的股息率。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbol",
            type=str,
            default="",
            help="单标的计算，如 600036",
        )

    def handle(self, *args, **options):
        symbol = str(options["symbol"] or "").strip()
        if symbol:
            rows = [AnnualReportDividendYieldService.compute_for_symbol(symbol=symbol)]
        else:
            rows = AnnualReportDividendYieldService.compute_for_high_dividend_instruments()

        self.stdout.write(
            "symbol  name      annual_report  cash/10  dps     price    yield    status"
        )
        self.stdout.write("-" * 90)
        for item in rows:
            yield_pct = (
                f"{(item.dividend_yield * 100):.2f}%"
                if item.dividend_yield is not None
                else "-"
            )
            self.stdout.write(
                f"{item.symbol:<8}"
                f"{item.name[:8]:<10}"
                f"{str(item.annual_report or '-'):<14}"
                f"{str(item.cash_dividend_per_10 or '-'):>8}  "
                f"{str(item.dividend_per_share or '-'):>6}  "
                f"{str(item.last_price or '-'):>7}  "
                f"{yield_pct:>7}  "
                f"{item.status}"
            )
            if item.error:
                self.stdout.write(f"  error: {item.error}")
