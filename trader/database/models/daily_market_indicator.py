"""每日市场指标模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class DailyMarketIndicator(TimestampedModel):
    """每日市场快照中的结构化指标。"""

    class IndicatorKey(models.TextChoices):
        INDEX_300_VS_CSI_2000 = "300_vs_2000", "沪深300对中证2000"
        INDEX_50_VS_CHINEXT = "sh_vs_chinext", "上证核心对创业板"
        INDEX_50_VS_HSTECH = "sh_vs_hstech", "上证核心对恒科"

    snapshot = models.ForeignKey(
        "trader.DailyMarketSnapshot",
        verbose_name="市场快照",
        related_name="indicators",
        on_delete=models.CASCADE,
    )
    indicator_key = models.CharField("指标键", max_length=32, choices=IndicatorKey.choices)
    title = models.CharField("指标标题", max_length=64)
    left_key = models.CharField("左侧配置键", max_length=64, blank=True)
    right_key = models.CharField("右侧配置键", max_length=64, blank=True)
    left_value = models.DecimalField("左侧值", max_digits=10, decimal_places=2, null=True, blank=True)
    right_value = models.DecimalField("右侧值", max_digits=10, decimal_places=2, null=True, blank=True)
    diff_value = models.DecimalField("差值", max_digits=10, decimal_places=2, null=True, blank=True)
    category = models.CharField("分类结果", max_length=64, blank=True)
    summary = models.TextField("摘要", blank=True)

    class Meta:
        db_table = "daily_market_indicators"
        verbose_name = "每日市场指标"
        verbose_name_plural = "每日市场指标"
        ordering = ["snapshot_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "indicator_key"],
                name="uniq_daily_market_indicator_snapshot_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.snapshot.report_date} {self.indicator_key}"
