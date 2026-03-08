"""风险规则模板定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class RiskTriggerScene(StrEnum):
    """规则触发场景。"""

    BEFORE_OPEN = "开仓前"
    BEFORE_ADD = "加仓前"
    AFTER_PRICE_UPDATE = "行情更新后"


class RiskConditionOperator(StrEnum):
    """规则条件操作符。"""

    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NE = "!="
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"


@dataclass(frozen=True)
class RiskRuleConditionTemplate:
    """风险规则中的单条条件模板。"""

    field_key: str
    operator: RiskConditionOperator
    expected_value: Any
    description: str = ""


@dataclass(frozen=True)
class RiskRuleTemplate:
    """单条风险规则模板。"""

    code: str
    name: str
    description: str
    trigger_scenes: tuple[RiskTriggerScene, ...]
    input_fields: tuple[str, ...]
    trigger_conditions: tuple[RiskRuleConditionTemplate, ...] = field(default_factory=tuple)
    limit_conditions: tuple[RiskRuleConditionTemplate, ...] = field(default_factory=tuple)
    block_on_failure: bool = True
    warning_message: str = ""
    block_message: str = ""

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("规则编码不能为空。")
        if not self.name.strip():
            raise ValueError("规则名称不能为空。")
        if not self.trigger_scenes:
            raise ValueError("规则至少需要一个触发场景。")
        if not self.input_fields:
            raise ValueError("规则至少需要一个输入字段。")
        if not self.limit_conditions:
            raise ValueError("规则至少需要一个限制条件。")


def get_default_risk_rule_templates() -> tuple[RiskRuleTemplate, ...]:
    """返回第一阶段默认启用的风险规则模板。"""

    return (
        RiskRuleTemplate(
            code="single_trade_risk_limit",
            name="单笔最大风险",
            description="根据计划入场价、计划止损价和计划成交数量，限制单笔交易预估风险金额。",
            trigger_scenes=(RiskTriggerScene.BEFORE_OPEN, RiskTriggerScene.BEFORE_ADD),
            input_fields=(
                "account",
                "planned_price",
                "planned_stop_loss_price",
                "planned_quantity",
                "single_trade_risk_limit",
            ),
            trigger_conditions=(
                RiskRuleConditionTemplate(
                    field_key="planned_stop_loss_price",
                    operator=RiskConditionOperator.EXISTS,
                    expected_value=True,
                    description="只有存在计划止损价时，才执行单笔风险检查。",
                ),
            ),
            limit_conditions=(
                RiskRuleConditionTemplate(
                    field_key="estimated_trade_risk_amount",
                    operator=RiskConditionOperator.LTE,
                    expected_value="single_trade_risk_limit",
                    description="预估单笔风险金额不得超过单笔风险上限。",
                ),
            ),
            block_message="单笔风险超过上限，禁止开仓或加仓。",
        ),
        RiskRuleTemplate(
            code="single_symbol_position_ratio_limit",
            name="单标的最大仓位占比",
            description="限制单一标的在账户总权益中的占比，避免仓位过度集中。",
            trigger_scenes=(RiskTriggerScene.BEFORE_OPEN, RiskTriggerScene.BEFORE_ADD),
            input_fields=(
                "account",
                "instrument",
                "position",
                "planned_price",
                "planned_quantity",
                "account_total_equity",
                "single_symbol_position_ratio_limit",
            ),
            limit_conditions=(
                RiskRuleConditionTemplate(
                    field_key="estimated_symbol_position_ratio",
                    operator=RiskConditionOperator.LTE,
                    expected_value="single_symbol_position_ratio_limit",
                    description="预计单标的仓位占比不得超过上限。",
                ),
            ),
            block_message="单标的仓位占比超过上限，禁止继续开仓或加仓。",
        ),
        RiskRuleTemplate(
            code="stop_loss_breach",
            name="跌破止损线",
            description="在行情更新后检查持仓是否已跌破止损线，用于提示止损失效。",
            trigger_scenes=(RiskTriggerScene.AFTER_PRICE_UPDATE,),
            input_fields=(
                "position",
                "latest_price",
                "stop_loss_price",
            ),
            trigger_conditions=(
                RiskRuleConditionTemplate(
                    field_key="stop_loss_price",
                    operator=RiskConditionOperator.EXISTS,
                    expected_value=True,
                    description="只有设置了止损价，才执行止损检查。",
                ),
            ),
            limit_conditions=(
                RiskRuleConditionTemplate(
                    field_key="latest_price",
                    operator=RiskConditionOperator.GTE,
                    expected_value="stop_loss_price",
                    description="最新价应保持在止损价之上。",
                ),
            ),
            block_on_failure=False,
            warning_message="持仓已跌破止损线，需要尽快处理。",
            block_message="持仓已跌破止损线。",
        ),
    )


def decimal_value(value: str | int | float | Decimal) -> Decimal:
    """将模板中的数值统一转换为 Decimal。"""

    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
