"""标的价格模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class InstrumentPrice(TimestampedModel):
    """标的价格表。"""

    class BarType(models.TextChoices):
        SPOT = "spot", "现价"
        MINUTE_1 = "1m", "1分钟"
        DAY_1 = "1d", "日线"

    instrument = models.ForeignKey(
        "trader.Instrument",
        verbose_name="标的",
        related_name="prices",
        on_delete=models.CASCADE,
    )
    bar_type = models.CharField("价格类型", max_length=8, choices=BarType.choices, default=BarType.SPOT)
    priced_at = models.DateTimeField("价格时间")
    open_price = models.DecimalField("开盘价", max_digits=20, decimal_places=4, null=True, blank=True)
    high_price = models.DecimalField("最高价", max_digits=20, decimal_places=4, null=True, blank=True)
    low_price = models.DecimalField("最低价", max_digits=20, decimal_places=4, null=True, blank=True)
    close_price = models.DecimalField("收盘价", max_digits=20, decimal_places=4, null=True, blank=True)
    last_price = models.DecimalField("最新价", max_digits=20, decimal_places=4, null=True, blank=True)
    prev_close = models.DecimalField("昨收价", max_digits=20, decimal_places=4, null=True, blank=True)
    annual_cash_dividend_per_10 = models.DecimalField(
        "年报分红(每10股)",
        max_digits=20,
        decimal_places=4,
        null=True,
        blank=True,
    )
    annual_dividend_per_share = models.DecimalField(
        "年报每股分红",
        max_digits=20,
        decimal_places=4,
        null=True,
        blank=True,
    )
    annual_dividend_yield_pct = models.DecimalField(
        "年报股息率(%)",
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
    )
    annual_dividend_report = models.CharField("年报报告期", max_length=32, blank=True)
    volume = models.DecimalField("成交量", max_digits=24, decimal_places=8, default=0)
    turnover = models.DecimalField("成交额", max_digits=24, decimal_places=4, default=0)
    source = models.CharField("数据来源", max_length=64, blank=True)

    class Meta:
        db_table = "instrument_prices"
        verbose_name = "标的价格"
        verbose_name_plural = "标的价格"
        ordering = ["-priced_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "bar_type", "priced_at"],
                name="uniq_instrument_price_bar_time",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.instrument.symbol} {self.bar_type} {self.priced_at}"
