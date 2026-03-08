"""导出所有业务表到 CSV。"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from trader.database import (
    Account,
    DailyMarketReport,
    Fill,
    Instrument,
    InstrumentPrice,
    Position,
    TableExportService,
)


class Command(BaseCommand):
    """导出账户、标的、持仓、价格、成交表。"""

    help = "导出所有业务表为 CSV 文件"

    def handle(self, *args, **options):
        output_dir = Path("trader/database/data")
        output_dir.mkdir(parents=True, exist_ok=True)

        export_targets = {
            "accounts.csv": Account,
            "daily_market_reports.csv": DailyMarketReport,
            "instruments.csv": Instrument,
            "positions.csv": Position,
            "instrument_prices.csv": InstrumentPrice,
            "fills.csv": Fill,
        }

        for file_name, model in export_targets.items():
            export_path = TableExportService.export_to_csv(
                model,
                output_dir / file_name,
            )
            self.stdout.write(self.style.SUCCESS(f"已导出 {model.__name__} -> {export_path}"))
