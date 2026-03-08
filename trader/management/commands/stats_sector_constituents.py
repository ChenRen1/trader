"""统计板块成分股涨幅分布。"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from trader.market.services import SectorAnalyticsService


class Command(BaseCommand):
    help = "统计指定板块成分股涨幅分布（按 1/3/5% 分层）。"

    def add_arguments(self, parser):
        parser.add_argument("--sector-code", type=str, default="", help="板块代码，如 881157")
        parser.add_argument("--sector-name", type=str, default="", help="板块名称，如 证券")

    def handle(self, *args, **options):
        sector_code = str(options["sector_code"]).strip()
        sector_name = str(options["sector_name"]).strip()
        if not sector_code and not sector_name:
            raise CommandError("请提供 --sector-code 或 --sector-name")

        result = SectorAnalyticsService.summarize_sector_change_stats(
            sector_code=sector_code or None,
            sector_name=sector_name or None,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"板块 {result['sector_code']} {result['sector_name']} 成分股统计："
                f"total={result['total_constituents']}, "
                f"valid={result['valid_change_count']}, "
                f"up={result['up_count']}, down={result['down_count']}, flat={result['flat_count']}, "
                f"mean={result['mean_change_pct']}, median={result['median_change_pct']}"
            )
        )

        d = result["distribution"]
        self.stdout.write("按 1/3/5% 分层分布：")
        self.stdout.write(f"  上涨 >=5%: {d['up_ge_5']}")
        self.stdout.write(f"  上涨 [3%,5%): {d['up_3_to_5']}")
        self.stdout.write(f"  上涨 [1%,3%): {d['up_1_to_3']}")
        self.stdout.write(f"  上涨 (0,1%): {d['up_0_to_1']}")
        self.stdout.write(f"  平盘 =0%: {d['flat']}")
        self.stdout.write(f"  下跌 (0,-1%): {d['down_0_to_1']}")
        self.stdout.write(f"  下跌 [-1%,-3%): {d['down_1_to_3']}")
        self.stdout.write(f"  下跌 [-3%,-5%): {d['down_3_to_5']}")
        self.stdout.write(f"  下跌 <=-5%: {d['down_ge_5']}")
