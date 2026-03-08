"""每日市场快照模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class DailyMarketSnapshot(TimestampedModel):
    """每日市场情况主表。"""

    report_date = models.DateField("报告日期", unique=True)
    reported_at = models.DateTimeField("生成时间")
    quote_count = models.PositiveIntegerField("标的数量", default=0)
    ok_count = models.PositiveIntegerField("正常数量", default=0)
    missing_instrument_count = models.PositiveIntegerField("缺少标的数量", default=0)
    missing_price_count = models.PositiveIntegerField("缺少价格数量", default=0)

    class Meta:
        db_table = "daily_market_snapshots"
        verbose_name = "每日市场快照"
        verbose_name_plural = "每日市场快照"
        ordering = ["-report_date", "-reported_at"]

    def __str__(self) -> str:
        return str(self.report_date)
