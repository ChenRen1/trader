"""标的模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class Instrument(TimestampedModel):
    """标的表。"""

    class Market(models.TextChoices):
        CN = "CN", "CN"
        HK = "HK", "HK"
        US = "US", "US"
        MACRO = "MACRO", "MACRO"

    class Exchange(models.TextChoices):
        SSE = "SSE", "SSE"
        SZSE = "SZSE", "SZSE"
        BSE = "BSE", "BSE"
        HKEX = "HKEX", "HKEX"
        NASDAQ = "NASDAQ", "NASDAQ"
        NYSE = "NYSE", "NYSE"
        OTC = "OTC", "OTC"

    class InstrumentType(models.TextChoices):
        STOCK = "股票", "股票"
        ETF = "ETF", "ETF"
        INDEX = "指数", "指数"
        FX = "外汇", "外汇"
        RATE = "利率", "利率"

    class Currency(models.TextChoices):
        CNY = "CNY", "CNY"
        HKD = "HKD", "HKD"
        USD = "USD", "USD"
        CNH = "CNH", "CNH"

    class Status(models.TextChoices):
        ACTIVE = "启用", "启用"
        INACTIVE = "停用", "停用"

    symbol = models.CharField("标的代码", max_length=32)
    name = models.CharField("标的名称", max_length=128)
    market = models.CharField("市场", max_length=16, choices=Market.choices)
    exchange = models.CharField("交易所", max_length=16, choices=Exchange.choices)
    instrument_type = models.CharField("标的类型", max_length=16, choices=InstrumentType.choices)
    trading_currency = models.CharField("交易币种", max_length=8, choices=Currency.choices)
    lot_size = models.PositiveIntegerField("最小交易单位", default=1)
    tick_size = models.DecimalField("最小变动价位", max_digits=20, decimal_places=4, null=True, blank=True)
    tradable = models.BooleanField("可交易", default=True)
    is_high_dividend = models.BooleanField("高股息标的", default=False)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.ACTIVE)
    data_source = models.CharField("数据源", max_length=64, blank=True)
    notes = models.TextField("备注", blank=True)

    class Meta:
        db_table = "instruments"
        verbose_name = "标的"
        verbose_name_plural = "标的"
        ordering = ["market", "symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "market"],
                name="uniq_instrument_symbol_market",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.symbol}.{self.market}"
