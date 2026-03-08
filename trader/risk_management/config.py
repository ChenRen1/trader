"""风险管理默认配置。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskLimitConfig:
    """基础风险限制配置。"""

    # 单笔风险默认按账户总资产的固定比例计算，例如 0.01 表示 1%。
    single_trade_risk_ratio: Decimal = Decimal("0.01")
    # 单一标的在账户总资产中的最大占比，例如 0.20 表示不超过 20%。
    single_symbol_position_ratio_limit: Decimal = Decimal("0.20")
    # 默认下单数量步长，股票场景下通常按 1 股或后续扩展为 100 股。
    quantity_step: Decimal = Decimal("100")


DEFAULT_RISK_LIMIT_CONFIG = RiskLimitConfig()
