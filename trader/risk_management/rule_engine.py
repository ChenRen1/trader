"""最小可用的风险规则执行器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import SimpleNamespace
from typing import Any

from trader.risk_management.rule_templates import (
    RiskConditionOperator,
    RiskRuleConditionTemplate,
    RiskRuleTemplate,
    RiskTriggerScene,
    decimal_value,
    get_default_risk_rule_templates,
)


class RiskRuleResultLevel(StrEnum):
    """单条规则执行结果等级。"""

    PASSED = "通过"
    WARNING = "预警"
    BLOCKED = "阻断"
    SKIPPED = "跳过"


@dataclass(frozen=True)
class RiskRuleContext:
    """规则执行上下文。"""

    scene: RiskTriggerScene
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


@dataclass(frozen=True)
class RiskRuleExecutionResult:
    """单条规则执行结果。"""

    rule_code: str
    rule_name: str
    level: RiskRuleResultLevel
    executed: bool
    blocked: bool
    passed: bool
    message: str = ""


@dataclass(frozen=True)
class RiskRuleExecutionSummary:
    """规则执行汇总结果。"""

    scene: RiskTriggerScene
    level: RiskRuleResultLevel
    blocked: bool
    results: tuple[RiskRuleExecutionResult, ...]


class RiskRuleEngine:
    """基于规则模板执行最小风险检查。"""

    def __init__(self, templates: tuple[RiskRuleTemplate, ...] | None = None) -> None:
        self.templates = templates or get_default_risk_rule_templates()

    def evaluate(self, context: RiskRuleContext) -> RiskRuleExecutionSummary:
        enriched_context = RiskRuleContext(
            scene=context.scene,
            values=self._build_enriched_values(context.values),
        )
        results = tuple(self._evaluate_template(template, enriched_context) for template in self.templates)

        if any(result.level == RiskRuleResultLevel.BLOCKED for result in results):
            level = RiskRuleResultLevel.BLOCKED
        elif any(result.level == RiskRuleResultLevel.WARNING for result in results):
            level = RiskRuleResultLevel.WARNING
        else:
            level = RiskRuleResultLevel.PASSED

        return RiskRuleExecutionSummary(
            scene=context.scene,
            level=level,
            blocked=level == RiskRuleResultLevel.BLOCKED,
            results=results,
        )

    def _evaluate_template(
        self,
        template: RiskRuleTemplate,
        context: RiskRuleContext,
    ) -> RiskRuleExecutionResult:
        if context.scene not in template.trigger_scenes:
            return RiskRuleExecutionResult(
                rule_code=template.code,
                rule_name=template.name,
                level=RiskRuleResultLevel.SKIPPED,
                executed=False,
                blocked=False,
                passed=True,
                message="当前场景不触发该规则。",
            )

        if not self._all_conditions_match(template.trigger_conditions, context):
            return RiskRuleExecutionResult(
                rule_code=template.code,
                rule_name=template.name,
                level=RiskRuleResultLevel.SKIPPED,
                executed=False,
                blocked=False,
                passed=True,
                message="未满足规则触发条件。",
            )

        if self._all_conditions_match(template.limit_conditions, context):
            return RiskRuleExecutionResult(
                rule_code=template.code,
                rule_name=template.name,
                level=RiskRuleResultLevel.PASSED,
                executed=True,
                blocked=False,
                passed=True,
                message="规则检查通过。",
            )

        level = RiskRuleResultLevel.BLOCKED if template.block_on_failure else RiskRuleResultLevel.WARNING
        message = template.block_message if template.block_on_failure else template.warning_message or template.block_message
        return RiskRuleExecutionResult(
            rule_code=template.code,
            rule_name=template.name,
            level=level,
            executed=True,
            blocked=template.block_on_failure,
            passed=False,
            message=message,
        )

    def _all_conditions_match(
        self,
        conditions: tuple[RiskRuleConditionTemplate, ...],
        context: RiskRuleContext,
    ) -> bool:
        return all(self._condition_matches(condition, context) for condition in conditions)

    def _condition_matches(
        self,
        condition: RiskRuleConditionTemplate,
        context: RiskRuleContext,
    ) -> bool:
        left_value = self._resolve_value(condition.field_key, context)
        expected_value = self._resolve_value(condition.expected_value, context)

        if condition.operator == RiskConditionOperator.EXISTS:
            exists = left_value is not None and left_value != ""
            return exists is bool(expected_value)

        if condition.operator == RiskConditionOperator.IN:
            return left_value in expected_value
        if condition.operator == RiskConditionOperator.NOT_IN:
            return left_value not in expected_value

        left_value, expected_value = self._normalize_pair(left_value, expected_value)

        if condition.operator == RiskConditionOperator.GT:
            return left_value > expected_value
        if condition.operator == RiskConditionOperator.GTE:
            return left_value >= expected_value
        if condition.operator == RiskConditionOperator.LT:
            return left_value < expected_value
        if condition.operator == RiskConditionOperator.LTE:
            return left_value <= expected_value
        if condition.operator == RiskConditionOperator.EQ:
            return left_value == expected_value
        if condition.operator == RiskConditionOperator.NE:
            return left_value != expected_value

        raise ValueError(f"不支持的规则操作符: {condition.operator}")

    def _resolve_value(self, value: Any, context: RiskRuleContext) -> Any:
        if isinstance(value, str) and value in context.values:
            return context.values[value]
        return value

    def _normalize_pair(self, left_value: Any, right_value: Any) -> tuple[Any, Any]:
        if self._looks_like_number(left_value) and self._looks_like_number(right_value):
            return decimal_value(left_value), decimal_value(right_value)
        return left_value, right_value

    def _looks_like_number(self, value: Any) -> bool:
        return isinstance(value, (Decimal, int, float)) or (
            isinstance(value, str) and value.replace(".", "", 1).replace("-", "", 1).isdigit()
        )

    def _build_enriched_values(self, raw_values: dict[str, Any]) -> dict[str, Any]:
        values = dict(raw_values)

        account = values.get("account")
        position = values.get("position")

        if "account_total_equity" not in values and account is not None:
            values["account_total_equity"] = self._read_attr(account, "total_equity", Decimal("0"))

        if "estimated_trade_risk_amount" not in values:
            planned_price = values.get("planned_price")
            planned_stop_loss_price = values.get("planned_stop_loss_price")
            planned_quantity = values.get("planned_quantity")
            if planned_price is not None and planned_stop_loss_price is not None and planned_quantity is not None:
                values["estimated_trade_risk_amount"] = (
                    abs(decimal_value(planned_price) - decimal_value(planned_stop_loss_price))
                    * decimal_value(planned_quantity)
                )

        if "estimated_symbol_position_ratio" not in values:
            account_total_equity = values.get("account_total_equity")
            planned_price = values.get("planned_price")
            planned_quantity = values.get("planned_quantity")
            if account_total_equity not in (None, Decimal("0"), 0, "0") and planned_price is not None and planned_quantity is not None:
                current_market_value = Decimal("0")
                if position is not None:
                    current_market_value = decimal_value(self._read_attr(position, "market_value", Decimal("0")))
                estimated_position_value = current_market_value + (
                    decimal_value(planned_price) * decimal_value(planned_quantity)
                )
                total_equity = decimal_value(account_total_equity)
                if total_equity != Decimal("0"):
                    values["estimated_symbol_position_ratio"] = estimated_position_value / total_equity

        if "stop_loss_price" not in values:
            values["stop_loss_price"] = values.get("planned_stop_loss_price")

        return values

    def _read_attr(self, obj: Any, field_name: str, default: Any = None) -> Any:
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(field_name, default)
        if isinstance(obj, SimpleNamespace):
            return getattr(obj, field_name, default)
        return getattr(obj, field_name, default)
