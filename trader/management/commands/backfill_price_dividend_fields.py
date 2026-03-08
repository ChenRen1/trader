"""回填价格表中的股息字段。"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from trader.database import Instrument, InstrumentPrice
from trader.strategy.services import AnnualReportDividendYieldService


class Command(BaseCommand):
    help = "为现有 spot 价格记录回填年报分红与股息率字段。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--all-cn",
            action="store_true",
            help="处理全部 A 股股票（默认仅高股息标记）。",
        )

    def handle(self, *args, **options):
        instruments = Instrument.objects.filter(
            market=Instrument.Market.CN,
            instrument_type=Instrument.InstrumentType.STOCK,
        ).order_by("symbol")
        if not options["all_cn"]:
            instruments = instruments.filter(is_high_dividend=True)

        updated = 0
        skipped = 0
        for instrument in instruments:
            prices = InstrumentPrice.objects.filter(
                instrument=instrument,
                bar_type=InstrumentPrice.BarType.SPOT,
            ).order_by("-priced_at", "-id")
            latest = prices.first()
            if latest is None or latest.last_price is None:
                skipped += 1
                continue

            result = AnnualReportDividendYieldService.compute_for_symbol_with_price(
                symbol=instrument.symbol,
                name=instrument.name,
                last_price=Decimal(str(latest.last_price)),
            )
            latest.annual_cash_dividend_per_10 = result.cash_dividend_per_10
            latest.annual_dividend_per_share = result.dividend_per_share
            latest.annual_dividend_yield_pct = (
                (result.dividend_yield * Decimal("100")).quantize(Decimal("0.0001"))
                if result.dividend_yield is not None
                else None
            )
            latest.annual_dividend_report = result.annual_report or ""
            latest.save(
                update_fields=[
                    "annual_cash_dividend_per_10",
                    "annual_dividend_per_share",
                    "annual_dividend_yield_pct",
                    "annual_dividend_report",
                    "updated_at",
                ]
            )
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"回填完成: updated={updated}, skipped={skipped}"))
