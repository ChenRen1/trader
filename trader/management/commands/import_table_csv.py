"""从 CSV 导入业务表。"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from trader.database import Account, Fill, Instrument, InstrumentPrice, Position, TableImportService


class Command(BaseCommand):
    """将 CSV 数据导入指定表。"""

    help = "从 CSV 导入指定业务表，存在 id 时更新，不存在时创建。"

    MODEL_MAP = {
        "accounts": Account,
        "fills": Fill,
        "instruments": Instrument,
        "instrument_prices": InstrumentPrice,
        "positions": Position,
    }

    def add_arguments(self, parser):
        parser.add_argument("table_name", choices=sorted(self.MODEL_MAP.keys()))
        parser.add_argument("csv_path")

    def handle(self, *args, **options):
        table_name = options["table_name"]
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV 文件不存在: {csv_path}")

        result = TableImportService.import_from_csv(
            self.MODEL_MAP[table_name],
            csv_path,
            audit_actor="system",
            audit_source=f"command:import_table_csv:{table_name}",
            audit_remark=f"import from {csv_path}",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"导入完成：table={table_name}, created={result['created']}, updated={result['updated']}"
            )
        )
