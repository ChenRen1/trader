"""账户模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class Account(TimestampedModel):
    """账户表。"""

    class AccountType(models.TextChoices):
        CASH = "普通账户", "普通账户"
        MARGIN = "融资账户", "融资账户"
        OPTION = "期权账户", "期权账户"

    class Currency(models.TextChoices):
        CNY = "CNY", "CNY"
        HKD = "HKD", "HKD"
        USD = "USD", "USD"

    class Status(models.TextChoices):
        ACTIVE = "启用", "启用"
        INACTIVE = "停用", "停用"

    account_code = models.CharField("账户编号", max_length=64, unique=True)
    account_name = models.CharField("账户名称", max_length=128)
    account_type = models.CharField("账户类型", max_length=16, choices=AccountType.choices)
    base_currency = models.CharField("基础币种", max_length=8, choices=Currency.choices)
    broker_name = models.CharField("券商名称", max_length=128, blank=True)
    initial_balance = models.DecimalField("初始资金", max_digits=20, decimal_places=4, default=0)
    available_cash = models.DecimalField("可用资金", max_digits=20, decimal_places=4, default=0)
    frozen_cash = models.DecimalField("冻结资金", max_digits=20, decimal_places=4, default=0)
    liability = models.DecimalField("负债", max_digits=20, decimal_places=4, default=0)
    risk_limit = models.DecimalField("风险限额", max_digits=20, decimal_places=4, default=0)
    total_market_value = models.DecimalField("持仓市值", max_digits=20, decimal_places=4, default=0)
    total_unrealized_pnl = models.DecimalField("未实现盈亏", max_digits=20, decimal_places=4, default=0)
    total_equity = models.DecimalField("账户总资产", max_digits=20, decimal_places=4, default=0)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField("备注", blank=True)

    class Meta:
        db_table = "accounts"
        verbose_name = "账户"
        verbose_name_plural = "账户"
        ordering = ["account_code"]

    def __str__(self) -> str:
        return f"{self.account_code} - {self.account_name}"
