"""高股息策略统一引擎入口。"""

from __future__ import annotations

from decimal import Decimal

from trader.database import Instrument, InstrumentPrice
from trader.strategy.core import StrategySignal
from trader.strategy.services import DividendYieldStrategyConfig


class DividendYieldEngine:
    """基于已落库股息率字段生成买入信号。"""

    strategy_key = "dividend_yield"

    def __init__(self, config: DividendYieldStrategyConfig | None = None) -> None:
        self.config = config or DividendYieldStrategyConfig()

    def generate_signals(self) -> list[StrategySignal]:
        threshold_pct = (self.config.buy_threshold * Decimal("100")).quantize(Decimal("0.01"))
        signals: list[StrategySignal] = []

        instruments = Instrument.objects.filter(
            market=Instrument.Market.CN,
            instrument_type=Instrument.InstrumentType.STOCK,
            is_high_dividend=True,
        ).order_by("symbol")

        for instrument in instruments:
            latest = (
                InstrumentPrice.objects.filter(
                    instrument=instrument,
                    bar_type=InstrumentPrice.BarType.SPOT,
                )
                .order_by("-priced_at", "-id")
                .first()
            )
            if latest is None or latest.annual_dividend_yield_pct is None:
                continue
            yield_pct = Decimal(str(latest.annual_dividend_yield_pct))
            if yield_pct < threshold_pct:
                continue
            signals.append(
                StrategySignal(
                    symbol=instrument.symbol,
                    action="BUY",
                    score=yield_pct,
                    reason=f"annual_dividend_yield_pct({yield_pct}%) >= threshold({threshold_pct}%)",
                )
            )

        signals.sort(key=lambda item: (item.score or Decimal("0"), item.symbol), reverse=True)
        return signals
