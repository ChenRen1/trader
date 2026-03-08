"""交易限制计算。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from trader.risk_management.config import DEFAULT_RISK_LIMIT_CONFIG
from trader.risk_management.rule_engine import (
    RiskRuleContext,
    RiskRuleEngine,
    RiskRuleExecutionSummary,
)
from trader.risk_management.rule_templates import RiskTriggerScene, decimal_value


@dataclass(frozen=True)
class TradeLimitInput:
    """交易限制计算输入。"""

    account: Any
    planned_price: Decimal
    planned_quantity: Decimal
    planned_stop_loss_price: Decimal | None = None
    position: Any | None = None
    single_trade_risk_limit: Decimal | None = None
    single_symbol_position_ratio_limit: Decimal | None = None
    quantity_step: Decimal = Decimal("1")


@dataclass(frozen=True)
class TradeLimitResult:
    """交易限制计算结果。"""

    requested_quantity: Decimal
    max_allowed_quantity: Decimal
    allowed_quantity: Decimal
    allowed: bool
    summary: RiskRuleExecutionSummary


class TradeLimitCalculator:
    """基于风险规则计算开仓或加仓限制。"""

    def __init__(self, engine: RiskRuleEngine | None = None) -> None:
        self.engine = engine or RiskRuleEngine()

    def calculate(self, data: TradeLimitInput) -> TradeLimitResult:
        single_trade_risk_limit = self._resolve_single_trade_risk_limit(data)
        single_symbol_position_ratio_limit = self._resolve_symbol_position_ratio_limit(data)
        quantity_step = decimal_value(data.quantity_step or DEFAULT_RISK_LIMIT_CONFIG.quantity_step)

        max_quantities = [data.planned_quantity]

        risk_max_quantity = self._max_quantity_by_trade_risk(
            data,
            single_trade_risk_limit=single_trade_risk_limit,
            quantity_step=quantity_step,
        )
        if risk_max_quantity is not None:
            max_quantities.append(risk_max_quantity)

        position_ratio_max_quantity = self._max_quantity_by_position_ratio(
            data,
            single_symbol_position_ratio_limit=single_symbol_position_ratio_limit,
            quantity_step=quantity_step,
        )
        if position_ratio_max_quantity is not None:
            max_quantities.append(position_ratio_max_quantity)

        max_allowed_quantity = min(max_quantities)
        max_allowed_quantity = self._floor_to_step(max_allowed_quantity, quantity_step)
        allowed_quantity = min(data.planned_quantity, max_allowed_quantity)

        summary = self.engine.evaluate(
            RiskRuleContext(
                scene=RiskTriggerScene.BEFORE_OPEN,
                values={
                    "account": data.account,
                    "position": data.position,
                    "planned_price": data.planned_price,
                    "planned_quantity": data.planned_quantity,
                    "planned_stop_loss_price": data.planned_stop_loss_price,
                    "single_trade_risk_limit": single_trade_risk_limit,
                    "single_symbol_position_ratio_limit": single_symbol_position_ratio_limit,
                },
            )
        )

        return TradeLimitResult(
            requested_quantity=decimal_value(data.planned_quantity),
            max_allowed_quantity=max_allowed_quantity,
            allowed_quantity=allowed_quantity,
            allowed=not summary.blocked,
            summary=summary,
        )

    def _max_quantity_by_trade_risk(
        self,
        data: TradeLimitInput,
        *,
        single_trade_risk_limit: Decimal | None,
        quantity_step: Decimal,
    ) -> Decimal | None:
        if single_trade_risk_limit is None or data.planned_stop_loss_price is None:
            return None

        risk_per_unit = abs(decimal_value(data.planned_price) - decimal_value(data.planned_stop_loss_price))
        if risk_per_unit == Decimal("0"):
            return None

        raw_quantity = decimal_value(single_trade_risk_limit) / risk_per_unit
        return self._floor_to_step(raw_quantity, quantity_step)

    def _max_quantity_by_position_ratio(
        self,
        data: TradeLimitInput,
        *,
        single_symbol_position_ratio_limit: Decimal | None,
        quantity_step: Decimal,
    ) -> Decimal | None:
        if single_symbol_position_ratio_limit is None:
            return None

        total_equity = decimal_value(getattr(data.account, "total_equity", Decimal("0")))
        if total_equity <= Decimal("0"):
            return Decimal("0")

        current_market_value = Decimal("0")
        if data.position is not None:
            current_market_value = decimal_value(getattr(data.position, "market_value", Decimal("0")))

        max_position_value = total_equity * decimal_value(single_symbol_position_ratio_limit)
        remaining_value = max_position_value - current_market_value
        if remaining_value <= Decimal("0"):
            return Decimal("0")

        raw_quantity = remaining_value / decimal_value(data.planned_price)
        return self._floor_to_step(raw_quantity, quantity_step)

    def _resolve_single_trade_risk_limit(self, data: TradeLimitInput) -> Decimal | None:
        if data.single_trade_risk_limit is not None:
            return decimal_value(data.single_trade_risk_limit)

        total_equity = decimal_value(getattr(data.account, "total_equity", Decimal("0")))
        if total_equity <= Decimal("0"):
            return None
        return total_equity * DEFAULT_RISK_LIMIT_CONFIG.single_trade_risk_ratio

    def _resolve_symbol_position_ratio_limit(self, data: TradeLimitInput) -> Decimal:
        if data.single_symbol_position_ratio_limit is not None:
            return decimal_value(data.single_symbol_position_ratio_limit)
        return DEFAULT_RISK_LIMIT_CONFIG.single_symbol_position_ratio_limit

    def _floor_to_step(self, quantity: Decimal, step: Decimal) -> Decimal:
        normalized_quantity = decimal_value(quantity)
        normalized_step = decimal_value(step)
        if normalized_quantity <= Decimal("0"):
            return Decimal("0")
        return (normalized_quantity // normalized_step) * normalized_step
