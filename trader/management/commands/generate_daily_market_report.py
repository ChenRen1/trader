"""生成每日市场分析报告。"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from trader.market.services import MarketDailyReportService, MarketQuoteSyncService


class Command(BaseCommand):
    help = "根据 config 标的行情生成每日市场分析报告（Markdown）。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync",
            action="store_true",
            help="先同步一次 config 标的现价，再生成报告。",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default="",
            help="报告输出目录，默认写入 trader/market/reports。",
        )

    def handle(self, *args, **options):
        if options["sync"]:
            sync_result = MarketQuoteSyncService.sync_config_spot_prices()
            sync = sync_result["sync"]
            self.stdout.write(
                f"[sync] matched={sync_result['matched']} updated={sync['updated']} failed={sync['failed']}"
            )

        output_dir = Path(options["output_dir"]) if options["output_dir"] else None
        report_path = MarketDailyReportService.write_daily_report(output_dir=output_dir)
        self.stdout.write(self.style.SUCCESS(f"报告已生成: {report_path}"))

