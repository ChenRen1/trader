"""高股息策略服务。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from trader.strategy.services.universe import IndexConstituent

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class DividendStockInput:
    symbol: str
    name: str
    dividend_yield: Decimal
    price: Decimal
    market: str = "CN"


@dataclass(frozen=True)
class DividendYieldStrategyConfig:
    """高股息策略参数。"""

    buy_threshold: Decimal = Decimal("0.055")
    sell_threshold: Decimal = Decimal("0.04")
    max_positions: int = 20
    cash_buffer: Decimal = Decimal("0.02")
    min_rebalance_delta: Decimal = Decimal("0.005")


@dataclass(frozen=True)
class RebalanceInstruction:
    symbol: str
    action: str
    current_weight: Decimal
    target_weight: Decimal
    dividend_yield: Decimal | None
    reason: str


class DividendYieldStrategyService:
    """高股息买卖与调仓计划。"""

    @staticmethod
    def _sanitize_weight(value: Decimal) -> Decimal:
        if value < ZERO:
            return ZERO
        if value > ONE:
            return ONE
        return value

    @classmethod
    def _pick_buy_candidates(
        cls,
        universe: list[DividendStockInput],
        config: DividendYieldStrategyConfig,
    ) -> list[DividendStockInput]:
        picked = [item for item in universe if item.dividend_yield >= config.buy_threshold]
        picked.sort(key=lambda item: (item.dividend_yield, item.symbol), reverse=True)
        return picked[: max(config.max_positions, 0)]

    @classmethod
    def build_inputs_from_index_pool(
        cls,
        *,
        pool: list[IndexConstituent],
        dividend_yield_map: dict[str, Decimal],
        price_map: dict[str, Decimal],
    ) -> list[DividendStockInput]:
        """先按指数成分股构建池，再补齐股息率与价格作为策略输入。"""
        rows: list[DividendStockInput] = []
        for item in pool:
            y = dividend_yield_map.get(item.symbol)
            px = price_map.get(item.symbol)
            if y is None or px in {None, ZERO}:
                continue
            rows.append(
                DividendStockInput(
                    symbol=item.symbol,
                    name=item.name or item.symbol,
                    dividend_yield=y,
                    price=px,
                    market="CN",
                )
            )
        return rows

    @classmethod
    def build_target_weights(
        cls,
        *,
        universe: list[DividendStockInput],
        current_weights: dict[str, Decimal] | None = None,
        config: DividendYieldStrategyConfig | None = None,
    ) -> dict[str, Decimal]:
        cfg = config or DividendYieldStrategyConfig()
        current = current_weights or {}
        candidates = cls._pick_buy_candidates(universe, cfg)
        target: dict[str, Decimal] = {}
        if not candidates:
            return target

        investable = cls._sanitize_weight(ONE - cfg.cash_buffer)
        equal_weight = (investable / Decimal(len(candidates))).quantize(Decimal("0.0001"))
        for item in candidates:
            target[item.symbol] = equal_weight

        # 对已持仓但触发卖出阈值的标的，明确归零。
        yield_map = {item.symbol: item.dividend_yield for item in universe}
        for symbol, weight in current.items():
            if weight <= ZERO:
                continue
            y = yield_map.get(symbol)
            if y is None or y <= cfg.sell_threshold:
                target[symbol] = ZERO
        return target

    @classmethod
    def create_rebalance_plan(
        cls,
        *,
        universe: list[DividendStockInput],
        current_weights: dict[str, Decimal] | None = None,
        config: DividendYieldStrategyConfig | None = None,
    ) -> list[RebalanceInstruction]:
        cfg = config or DividendYieldStrategyConfig()
        current = current_weights or {}
        target = cls.build_target_weights(universe=universe, current_weights=current, config=cfg)
        yield_map = {item.symbol: item.dividend_yield for item in universe}
        symbols = sorted(set(current.keys()) | set(target.keys()))
        instructions: list[RebalanceInstruction] = []

        for symbol in symbols:
            current_weight = cls._sanitize_weight(current.get(symbol, ZERO))
            target_weight = cls._sanitize_weight(target.get(symbol, ZERO))
            delta = (target_weight - current_weight).copy_abs()
            if delta < cfg.min_rebalance_delta:
                continue

            if target_weight == ZERO and current_weight > ZERO:
                action = "SELL"
                reason = "dividend_yield_below_sell_threshold_or_not_in_universe"
            elif target_weight > current_weight:
                action = "BUY"
                reason = "dividend_yield_above_buy_threshold"
            else:
                action = "REDUCE"
                reason = "rebalance_to_target_weight"

            instructions.append(
                RebalanceInstruction(
                    symbol=symbol,
                    action=action,
                    current_weight=current_weight,
                    target_weight=target_weight,
                    dividend_yield=yield_map.get(symbol),
                    reason=reason,
                )
            )
        return instructions
