"""成交模型。"""

from django.core.validators import MinValueValidator
from django.db import models

from trader.database.models.base import TimestampedModel
from trader.database.models.instrument import Instrument


class Fill(TimestampedModel):
    """成交表。"""

    class Side(models.TextChoices):
        BUY = "买入", "买入"
        SELL = "卖出", "卖出"

    account = models.ForeignKey(
        "trader.Account",
        verbose_name="账户",
        related_name="fills",
        on_delete=models.CASCADE,
    )
    instrument = models.ForeignKey(
        "trader.Instrument",
        verbose_name="标的",
        related_name="fills",
        on_delete=models.CASCADE,
    )
    position = models.ForeignKey(
        "trader.Position",
        verbose_name="关联持仓",
        related_name="fills",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    fill_time = models.DateTimeField("成交时间")
    side = models.CharField("买卖方向", max_length=8, choices=Side.choices)
    quantity = models.DecimalField(
        "成交数量",
        max_digits=20,
        decimal_places=8,
        validators=[MinValueValidator(0.00000001)],
    )
    price = models.DecimalField(
        "成交价格",
        max_digits=20,
        decimal_places=4,
        validators=[MinValueValidator(0.0001)],
    )
    amount = models.DecimalField("成交金额", max_digits=20, decimal_places=4, default=0)
    commission = models.DecimalField("手续费", max_digits=20, decimal_places=4, default=0)
    tax = models.DecimalField("税费", max_digits=20, decimal_places=4, default=0)
    pricing_currency = models.CharField("计价币种", max_length=8, choices=Instrument.Currency.choices)
    external_id = models.CharField("外部成交编号", max_length=128, blank=True)
    notes = models.TextField("备注", blank=True)

    class Meta:
        db_table = "fills"
        verbose_name = "成交"
        verbose_name_plural = "成交"
        ordering = ["-fill_time", "-created_at"]

    def __str__(self) -> str:
        return f"{self.instrument.symbol} {self.side} {self.quantity}@{self.price}"
