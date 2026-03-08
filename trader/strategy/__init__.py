"""交易策略模块。"""

from trader.strategy import strategies as _strategies  # noqa: F401
from trader.strategy.backtest import (
    DividendBacktestConfig,
    DividendBacktestResult,
    DividendObservation,
    DividendYieldBacktestService,
)
from trader.strategy.core import (
    StrategyContext,
    StrategyEngine,
    StrategySignal,
    get_strategy,
    list_strategies,
    register_strategy,
)
from trader.strategy.services import (
    AnnualDividendYieldResult,
    AnnualReportDividendYieldService,
    DividendUniverseConfig,
    DividendUniverseService,
    DividendStockInput,
    DividendYieldStrategyConfig,
    DividendYieldStrategyService,
    HighDividendRegistryService,
    HighDividendSyncResult,
    IndexConstituent,
    RebalanceInstruction,
)

__all__ = [
    "DividendStockInput",
    "AnnualDividendYieldResult",
    "AnnualReportDividendYieldService",
    "StrategyContext",
    "StrategyEngine",
    "StrategySignal",
    "register_strategy",
    "get_strategy",
    "list_strategies",
    "IndexConstituent",
    "DividendUniverseConfig",
    "DividendUniverseService",
    "DividendYieldStrategyConfig",
    "DividendYieldStrategyService",
    "RebalanceInstruction",
    "HighDividendSyncResult",
    "HighDividendRegistryService",
    "DividendObservation",
    "DividendBacktestConfig",
    "DividendBacktestResult",
    "DividendYieldBacktestService",
]
