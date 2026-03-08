"""持仓风险监控。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from trader.database.models import InstrumentPrice, Position
from trader.risk_management.config import DEFAULT_RISK_LIMIT_CONFIG
from trader.risk_management.rule_engine import (
    RiskRuleContext,
    RiskRuleEngine,
    RiskRuleExecutionSummary,
    RiskRuleResultLevel,
)
from trader.risk_management.rule_templates import RiskTriggerScene, decimal_value


@dataclass(frozen=True)
class PositionRiskInput:
    """持仓风险检查输入。"""

    position: Any
    latest_price: Decimal
    stop_loss_price: Decimal | None = None


@dataclass(frozen=True)
class PositionRiskResult:
    """持仓风险检查结果。"""

    position: Any
    latest_price: Decimal
    stop_loss_price: Decimal | None
    unrealized_pnl: Decimal
    unrealized_pnl_ratio: Decimal | None
    position_ratio: Decimal | None
    level: RiskRuleResultLevel
    breached_stop_loss: bool
    breached_position_ratio_limit: bool
    summary: RiskRuleExecutionSummary


class PositionRiskMonitor:
    """基于持仓和最新价格生成风险状态。"""

    def __init__(self, engine: RiskRuleEngine | None = None) -> None:
        self.engine = engine or RiskRuleEngine()

    def evaluate(self, data: PositionRiskInput) -> PositionRiskResult:
        summary = self.engine.evaluate(
            RiskRuleContext(
                scene=RiskTriggerScene.AFTER_PRICE_UPDATE,
                values={
                    "position": data.position,
                    "latest_price": data.latest_price,
                    "stop_loss_price": data.stop_loss_price,
                },
            )
        )

        unrealized_pnl = decimal_value(getattr(data.position, "unrealized_pnl", Decimal("0")))
        cost_basis = decimal_value(getattr(data.position, "cost_basis", Decimal("0")))
        market_value = decimal_value(getattr(data.position, "market_value", Decimal("0")))
        account = getattr(data.position, "account", None)
        total_equity = decimal_value(getattr(account, "total_equity", Decimal("0"))) if account is not None else Decimal("0")
        unrealized_pnl_ratio = None
        position_ratio = None
        if cost_basis != Decimal("0"):
            unrealized_pnl_ratio = unrealized_pnl / cost_basis
        if total_equity != Decimal("0"):
            position_ratio = market_value / total_equity

        breached_position_ratio_limit = False
        if position_ratio is not None:
            breached_position_ratio_limit = (
                position_ratio > DEFAULT_RISK_LIMIT_CONFIG.single_symbol_position_ratio_limit
            )

        level = summary.level
        if breached_position_ratio_limit:
            level = RiskRuleResultLevel.WARNING

        return PositionRiskResult(
            position=data.position,
            latest_price=decimal_value(data.latest_price),
            stop_loss_price=None if data.stop_loss_price is None else decimal_value(data.stop_loss_price),
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_ratio=unrealized_pnl_ratio,
            position_ratio=position_ratio,
            level=level,
            breached_stop_loss=any(
                result.rule_code == "stop_loss_breach" and result.level == RiskRuleResultLevel.WARNING
                for result in summary.results
            ),
            breached_position_ratio_limit=breached_position_ratio_limit,
            summary=summary,
        )

    def evaluate_many(self, positions: list[PositionRiskInput]) -> list[PositionRiskResult]:
        return [self.evaluate(item) for item in positions]

    def evaluate_open_positions(self) -> list[PositionRiskResult]:
        """扫描当前全部持有中的持仓风险。"""
        positions = list(
            Position.objects.filter(status=Position.Status.OPEN)
            .select_related("account", "instrument")
            .order_by("account_id", "instrument_id")
        )
        return self.evaluate_model_positions(positions)

    def evaluate_model_positions(self, positions: list[Position]) -> list[PositionRiskResult]:
        """扫描给定持仓列表的风险。"""
        if not positions:
            return []

        results: list[PositionRiskResult] = []
        for position in positions:
            latest_price = (
                InstrumentPrice.objects.filter(
                    instrument=position.instrument,
                    bar_type=InstrumentPrice.BarType.SPOT,
                )
                .order_by("-priced_at", "-created_at")
                .values_list("last_price", flat=True)
                .first()
            )
            if latest_price is None:
                continue
            results.append(
                self.evaluate(
                    PositionRiskInput(
                        position=position,
                        latest_price=decimal_value(latest_price),
                    )
                )
            )
        return results
