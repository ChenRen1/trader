"""每日报告快照模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class DailyMarketReport(TimestampedModel):
    """每日市场报告表。"""

    report_date = models.DateField("报告日期", unique=True)
    reported_at = models.DateTimeField("生成时间")
    hs300_sector_summary = models.TextField("沪深300行业统计摘要", blank=True)
    markdown_content = models.TextField("报告正文", blank=True)

    class Meta:
        db_table = "daily_market_reports"
        verbose_name = "每日市场报告"
        verbose_name_plural = "每日市场报告"
        ordering = ["-report_date", "-id"]

    def __str__(self) -> str:
        return f"每日市场报告 {self.report_date}"
