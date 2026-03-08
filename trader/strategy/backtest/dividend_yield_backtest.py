"""高股息策略简化回测服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import mean

from trader.strategy.services import (
    DividendStockInput,
    DividendYieldStrategyConfig,
    DividendYieldStrategyService,
)

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True)
class DividendObservation:
    trade_date: date
    symbol: str
    close: Decimal
    dividend_yield: Decimal
    name: str = ""
    market: str = "CN"


@dataclass(frozen=True)
class DividendBacktestConfig:
    strategy: DividendYieldStrategyConfig = DividendYieldStrategyConfig()
    fee_rate: Decimal = Decimal("0.001")
    slippage: Decimal = Decimal("0.0005")


@dataclass(frozen=True)
class DividendBacktestResult:
    start_date: date
    end_date: date
    total_days: int
    cumulative_return: Decimal
    annualized_return: Decimal | None
    max_drawdown: Decimal
    avg_daily_return: Decimal
    turnover: Decimal
    net_value_series: list[tuple[date, Decimal]]


class DividendYieldBacktestService:
    """按日收盘简化回测。"""

    @classmethod
    def run(
        cls,
        *,
        observations: list[DividendObservation],
        config: DividendBacktestConfig | None = None,
    ) -> DividendBacktestResult:
        if not observations:
            raise ValueError("observations is empty")

        cfg = config or DividendBacktestConfig()
        by_date: dict[date, list[DividendObservation]] = {}
        for row in observations:
            by_date.setdefault(row.trade_date, []).append(row)

        dates = sorted(by_date.keys())
        current_weights: dict[str, Decimal] = {}
        last_close: dict[str, Decimal] = {}
        nav = ONE
        peak = nav
        max_drawdown = ZERO
        turnover = ZERO
        daily_returns: list[Decimal] = []
        series: list[tuple[date, Decimal]] = []

        for dt in dates:
            rows = by_date[dt]
            close_map = {row.symbol: row.close for row in rows}

            # 先按上一期持仓计算当日收益。
            gross_return = ZERO
            for symbol, weight in current_weights.items():
                prev = last_close.get(symbol)
                cur = close_map.get(symbol)
                if prev in {None, ZERO} or cur is None:
                    continue
                gross_return += weight * ((cur - prev) / prev)

            nav = nav * (ONE + gross_return)
            daily_returns.append(gross_return)

            # 再根据当日股息率生成下一期目标权重。
            universe = [
                DividendStockInput(
                    symbol=row.symbol,
                    name=row.name or row.symbol,
                    dividend_yield=row.dividend_yield,
                    price=row.close,
                    market=row.market,
                )
                for row in rows
            ]
            target_weights = DividendYieldStrategyService.build_target_weights(
                universe=universe,
                current_weights=current_weights,
                config=cfg.strategy,
            )
            symbols = set(current_weights.keys()) | set(target_weights.keys())
            day_turnover = sum((target_weights.get(s, ZERO) - current_weights.get(s, ZERO)).copy_abs() for s in symbols)

            if day_turnover > ZERO:
                cost = day_turnover * (cfg.fee_rate + cfg.slippage)
                nav = nav * (ONE - cost)
                turnover += day_turnover

            current_weights = target_weights
            last_close = close_map

            if nav > peak:
                peak = nav
            drawdown = (peak - nav) / peak if peak > ZERO else ZERO
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            series.append((dt, nav))

        total_days = len(dates)
        cumulative_return = nav - ONE
        annualized_return = None
        if total_days > 1:
            annualized_return = (nav ** (Decimal("252") / Decimal(total_days))) - ONE

        avg_daily = Decimal(str(mean(daily_returns))) if daily_returns else ZERO
        return DividendBacktestResult(
            start_date=dates[0],
            end_date=dates[-1],
            total_days=total_days,
            cumulative_return=cumulative_return.quantize(Decimal("0.0001")),
            annualized_return=annualized_return.quantize(Decimal("0.0001")) if annualized_return is not None else None,
            max_drawdown=max_drawdown.quantize(Decimal("0.0001")),
            avg_daily_return=avg_daily.quantize(Decimal("0.0001")),
            turnover=turnover.quantize(Decimal("0.0001")),
            net_value_series=series,
        )
