"""持仓模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel
from trader.database.models.instrument import Instrument


class Position(TimestampedModel):
    """持仓表。"""

    class Side(models.TextChoices):
        LONG = "做多", "做多"
        SHORT = "做空", "做空"

    class Status(models.TextChoices):
        OPEN = "持有中", "持有中"
        CLOSED = "已平仓", "已平仓"

    account = models.ForeignKey(
        "trader.Account",
        verbose_name="账户",
        related_name="positions",
        on_delete=models.CASCADE,
    )
    instrument = models.ForeignKey(
        "trader.Instrument",
        verbose_name="标的",
        related_name="positions",
        on_delete=models.CASCADE,
    )
    side = models.CharField("方向", max_length=8, choices=Side.choices, default=Side.LONG)
    quantity = models.DecimalField("持仓数量", max_digits=20, decimal_places=8, default=0)
    available_quantity = models.DecimalField("可用数量", max_digits=20, decimal_places=8, default=0)
    average_price = models.DecimalField("持仓均价", max_digits=20, decimal_places=4, default=0)
    cost_basis = models.DecimalField("持仓成本", max_digits=20, decimal_places=4, default=0)
    market_value = models.DecimalField("持仓市值", max_digits=20, decimal_places=4, default=0)
    unrealized_pnl = models.DecimalField("未实现盈亏", max_digits=20, decimal_places=4, default=0)
    position_ratio = models.DecimalField("持仓占比", max_digits=12, decimal_places=8, default=0)
    pricing_currency = models.CharField("计价币种", max_length=8, choices=Instrument.Currency.choices)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.OPEN)
    opened_at = models.DateTimeField("建仓时间", null=True, blank=True)
    closed_at = models.DateTimeField("平仓时间", null=True, blank=True)
    notes = models.TextField("备注", blank=True)

    class Meta:
        db_table = "positions"
        verbose_name = "持仓"
        verbose_name_plural = "持仓"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.account.account_code} - {self.instrument.symbol}"
