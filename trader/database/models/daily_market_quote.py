"""每日市场行情明细模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class DailyMarketQuote(TimestampedModel):
    """每日市场快照中的标的行情明细。"""

    class QuoteStatus(models.TextChoices):
        OK = "ok", "正常"
        MISSING_INSTRUMENT = "missing_instrument", "缺少标的"
        MISSING_PRICE = "missing_price", "缺少价格"

    snapshot = models.ForeignKey(
        "trader.DailyMarketSnapshot",
        verbose_name="市场快照",
        related_name="quotes",
        on_delete=models.CASCADE,
    )
    instrument = models.ForeignKey(
        "trader.Instrument",
        verbose_name="标的",
        related_name="daily_market_quotes",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    key = models.CharField("配置键", max_length=64)
    name = models.CharField("名称", max_length=128)
    symbol = models.CharField("代码", max_length=32)
    market = models.CharField("市场", max_length=16)
    last_price = models.DecimalField("现价", max_digits=20, decimal_places=4, null=True, blank=True)
    prev_close = models.DecimalField("昨收", max_digits=20, decimal_places=4, null=True, blank=True)
    change_pct = models.DecimalField("涨跌幅", max_digits=10, decimal_places=2, null=True, blank=True)
    priced_at = models.DateTimeField("价格时间", null=True, blank=True)
    source = models.CharField("来源", max_length=64, blank=True)
    status = models.CharField("状态", max_length=32, choices=QuoteStatus.choices)

    class Meta:
        db_table = "daily_market_quotes"
        verbose_name = "每日市场行情明细"
        verbose_name_plural = "每日市场行情明细"
        ordering = ["snapshot_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "key"],
                name="uniq_daily_market_quote_snapshot_key",
            )
        ]

    def __str__(self) -> str:
        return f"{self.snapshot.report_date} {self.key}"
