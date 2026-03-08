"""同步高股息标的标记。"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from trader.strategy.services import DividendUniverseConfig, HighDividendRegistryService


class Command(BaseCommand):
    help = "按红利指数成分同步 instruments.is_high_dividend。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--indexes",
            type=str,
            default="000015,000922",
            help="红利指数代码列表，逗号分隔，如 000015,000922",
        )
        parser.add_argument(
            "--no-create-missing",
            action="store_true",
            help="不自动创建缺失标的，仅更新已有标记。",
        )

    def handle(self, *args, **options):
        index_codes = tuple(code.strip() for code in options["indexes"].split(",") if code.strip())
        result = HighDividendRegistryService.sync_from_dividend_indices(
            config=DividendUniverseConfig(index_codes=index_codes),
            create_missing=not options["no_create_missing"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"同步完成: universe={result.universe_size}, created={result.created}, "
                f"marked={result.marked}, cleared={result.cleared}"
            )
        )
