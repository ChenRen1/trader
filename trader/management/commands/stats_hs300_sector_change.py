"""统计沪深300成分股按行业分组的涨跌幅。"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from trader.market.services import SectorAnalyticsService


class Command(BaseCommand):
    help = "统计沪深300成分股按行业分组的涨跌幅。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--top",
            type=int,
            default=20,
            help="输出前 N 个行业，默认 20。",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=8,
            help="现价并发查询线程数，默认 8。",
        )
        parser.add_argument(
            "--refresh-industry-cache",
            action="store_true",
            help="忽略本地行业缓存，重新拉取全部行业归属。",
        )

    def handle(self, *args, **options):
        rows = SectorAnalyticsService.summarize_hs300_sector_change_stats(
            max_workers=options["workers"],
            refresh_industry_cache=options["refresh_industry_cache"],
        )
        top = max(1, int(options["top"]))

        self.stdout.write(
            self.style.SUCCESS(
                f"沪深300行业统计完成: sectors={len(rows)}, output_top={min(top, len(rows))}"
            )
        )
        self.stdout.write("行业 | 样本数 | 有效数 | 上涨 | 下跌 | 平盘 | 均值% | 中位数%")
        for row in rows[:top]:
            self.stdout.write(
                f"{row['sector_name']} | "
                f"{row['constituent_count']} | "
                f"{row['valid_change_count']} | "
                f"{row['up_count']} | "
                f"{row['down_count']} | "
                f"{row['flat_count']} | "
                f"{row['mean_change_pct']} | "
                f"{row['median_change_pct']}"
            )
