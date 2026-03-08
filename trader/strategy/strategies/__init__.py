"""策略实现导出与注册。"""

from trader.strategy.core import register_strategy
from trader.strategy.strategies.dividend import DividendYieldEngine

dividend_yield_engine = DividendYieldEngine()
register_strategy(dividend_yield_engine)

__all__ = ["DividendYieldEngine", "dividend_yield_engine"]
