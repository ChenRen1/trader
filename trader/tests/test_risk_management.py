"""风险管理模块测试。"""

from __future__ import annotations

import os
from decimal import Decimal
from types import SimpleNamespace

import django
from django.test import SimpleTestCase

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class RiskRuleTemplateTests(SimpleTestCase):
    def test_default_rule_templates_cover_first_stage_rules(self) -> None:
        from trader.risk_management import get_default_risk_rule_templates

        templates = get_default_risk_rule_templates()
        codes = {template.code for template in templates}

        assert {
            "single_trade_risk_limit",
            "single_symbol_position_ratio_limit",
            "stop_loss_breach",
        } <= codes

    def test_rule_template_requires_trigger_scene_and_limit_condition(self) -> None:
        from trader.risk_management import RiskRuleTemplate

        try:
            RiskRuleTemplate(
                code="invalid_rule",
                name="无效规则",
                description="",
                trigger_scenes=(),
                input_fields=("account",),
                limit_conditions=(),
            )
        except ValueError as exc:
            assert "触发场景" in str(exc)
        else:
            raise AssertionError("缺少触发场景时应抛出 ValueError。")

    def test_decimal_value_converts_common_number_types(self) -> None:
        from trader.risk_management.rule_templates import decimal_value

        assert decimal_value("1.25") == Decimal("1.25")
        assert decimal_value(2) == Decimal("2")
        assert decimal_value(1.5) == Decimal("1.5")


class RiskRuleEngineTests(SimpleTestCase):
    def test_before_open_blocks_when_single_trade_risk_exceeds_limit(self) -> None:
        from trader.risk_management import RiskRuleContext, RiskRuleEngine, RiskRuleResultLevel, RiskTriggerScene

        engine = RiskRuleEngine()
        context = RiskRuleContext(
            scene=RiskTriggerScene.BEFORE_OPEN,
            values={
                "account": SimpleNamespace(total_equity=Decimal("100000")),
                "planned_price": Decimal("10"),
                "planned_stop_loss_price": Decimal("9"),
                "planned_quantity": Decimal("2000"),
                "single_trade_risk_limit": Decimal("1000"),
                "single_symbol_position_ratio_limit": Decimal("0.30"),
            },
        )

        summary = engine.evaluate(context)

        assert summary.level == RiskRuleResultLevel.BLOCKED
        assert summary.blocked is True
        assert any(result.rule_code == "single_trade_risk_limit" and result.level == RiskRuleResultLevel.BLOCKED for result in summary.results)

    def test_before_open_passes_when_limits_are_within_range(self) -> None:
        from trader.risk_management import RiskRuleContext, RiskRuleEngine, RiskRuleResultLevel, RiskTriggerScene

        engine = RiskRuleEngine()
        context = RiskRuleContext(
            scene=RiskTriggerScene.BEFORE_OPEN,
            values={
                "account": SimpleNamespace(total_equity=Decimal("100000")),
                "position": SimpleNamespace(market_value=Decimal("5000")),
                "planned_price": Decimal("10"),
                "planned_stop_loss_price": Decimal("9.5"),
                "planned_quantity": Decimal("1000"),
                "single_trade_risk_limit": Decimal("1000"),
                "single_symbol_position_ratio_limit": Decimal("0.20"),
            },
        )

        summary = engine.evaluate(context)

        assert summary.level == RiskRuleResultLevel.PASSED
        assert summary.blocked is False
        assert any(result.rule_code == "single_trade_risk_limit" and result.level == RiskRuleResultLevel.PASSED for result in summary.results)
        assert any(result.rule_code == "single_symbol_position_ratio_limit" and result.level == RiskRuleResultLevel.PASSED for result in summary.results)

    def test_after_price_update_returns_warning_when_stop_loss_breached(self) -> None:
        from trader.risk_management import RiskRuleContext, RiskRuleEngine, RiskRuleResultLevel, RiskTriggerScene

        engine = RiskRuleEngine()
        context = RiskRuleContext(
            scene=RiskTriggerScene.AFTER_PRICE_UPDATE,
            values={
                "position": SimpleNamespace(market_value=Decimal("20000")),
                "latest_price": Decimal("8.8"),
                "stop_loss_price": Decimal("9"),
            },
        )

        summary = engine.evaluate(context)

        assert summary.level == RiskRuleResultLevel.WARNING
        assert summary.blocked is False
        assert any(result.rule_code == "stop_loss_breach" and result.level == RiskRuleResultLevel.WARNING for result in summary.results)


class TradeLimitCalculatorTests(SimpleTestCase):
    def test_calculate_uses_default_config_when_limits_are_missing(self) -> None:
        from trader.risk_management import TradeLimitCalculator, TradeLimitInput

        calculator = TradeLimitCalculator()
        result = calculator.calculate(
            TradeLimitInput(
                account=SimpleNamespace(total_equity=Decimal("100000")),
                planned_price=Decimal("10"),
                planned_quantity=Decimal("1200"),
                planned_stop_loss_price=Decimal("9"),
            )
        )

        assert result.max_allowed_quantity == Decimal("1000")
        assert result.allowed_quantity == Decimal("1000")
        assert result.allowed is False

    def test_calculate_returns_max_allowed_quantity_by_risk_rule(self) -> None:
        from trader.risk_management import TradeLimitCalculator, TradeLimitInput

        calculator = TradeLimitCalculator()
        result = calculator.calculate(
            TradeLimitInput(
                account=SimpleNamespace(total_equity=Decimal("100000")),
                position=SimpleNamespace(market_value=Decimal("5000")),
                planned_price=Decimal("10"),
                planned_quantity=Decimal("1200"),
                planned_stop_loss_price=Decimal("9"),
                single_trade_risk_limit=Decimal("1000"),
                single_symbol_position_ratio_limit=Decimal("0.20"),
            )
        )

        assert result.max_allowed_quantity == Decimal("1000")
        assert result.allowed_quantity == Decimal("1000")
        assert result.allowed is False

    def test_calculate_passes_when_requested_quantity_is_within_limits(self) -> None:
        from trader.risk_management import TradeLimitCalculator, TradeLimitInput

        calculator = TradeLimitCalculator()
        result = calculator.calculate(
            TradeLimitInput(
                account=SimpleNamespace(total_equity=Decimal("100000")),
                position=SimpleNamespace(market_value=Decimal("5000")),
                planned_price=Decimal("10"),
                planned_quantity=Decimal("800"),
                planned_stop_loss_price=Decimal("9"),
                single_trade_risk_limit=Decimal("1000"),
                single_symbol_position_ratio_limit=Decimal("0.20"),
            )
        )

        assert result.max_allowed_quantity == Decimal("800")
        assert result.allowed_quantity == Decimal("800")
        assert result.allowed is True


class PositionRiskMonitorTests(SimpleTestCase):
    def test_evaluate_marks_stop_loss_breach_as_warning(self) -> None:
        from trader.risk_management import PositionRiskInput, PositionRiskMonitor, RiskRuleResultLevel

        monitor = PositionRiskMonitor()
        result = monitor.evaluate(
            PositionRiskInput(
                position=SimpleNamespace(
                    unrealized_pnl=Decimal("-1200"),
                    cost_basis=Decimal("10000"),
                    market_value=Decimal("18000"),
                    account=SimpleNamespace(total_equity=Decimal("100000")),
                ),
                latest_price=Decimal("8.8"),
                stop_loss_price=Decimal("9"),
            )
        )

        assert result.level == RiskRuleResultLevel.WARNING
        assert result.breached_stop_loss is True
        assert result.breached_position_ratio_limit is False
        assert result.unrealized_pnl == Decimal("-1200")
        assert result.unrealized_pnl_ratio == Decimal("-0.12")
        assert result.position_ratio == Decimal("0.18")

    def test_evaluate_without_stop_loss_returns_passed(self) -> None:
        from trader.risk_management import PositionRiskInput, PositionRiskMonitor, RiskRuleResultLevel

        monitor = PositionRiskMonitor()
        result = monitor.evaluate(
            PositionRiskInput(
                position=SimpleNamespace(
                    unrealized_pnl=Decimal("300"),
                    cost_basis=Decimal("10000"),
                    market_value=Decimal("12000"),
                    account=SimpleNamespace(total_equity=Decimal("100000")),
                ),
                latest_price=Decimal("10.8"),
            )
        )

        assert result.level == RiskRuleResultLevel.PASSED
        assert result.breached_stop_loss is False
        assert result.breached_position_ratio_limit is False
        assert result.unrealized_pnl_ratio == Decimal("0.03")
        assert result.position_ratio == Decimal("0.12")

    def test_evaluate_marks_warning_when_position_ratio_exceeds_limit(self) -> None:
        from trader.risk_management import PositionRiskInput, PositionRiskMonitor, RiskRuleResultLevel

        monitor = PositionRiskMonitor()
        result = monitor.evaluate(
            PositionRiskInput(
                position=SimpleNamespace(
                    unrealized_pnl=Decimal("5000"),
                    cost_basis=Decimal("20000"),
                    market_value=Decimal("25000"),
                    account=SimpleNamespace(total_equity=Decimal("100000")),
                ),
                latest_price=Decimal("12.5"),
            )
        )

        assert result.level == RiskRuleResultLevel.WARNING
        assert result.breached_stop_loss is False
        assert result.breached_position_ratio_limit is True
        assert result.position_ratio == Decimal("0.25")
