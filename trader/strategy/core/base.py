"""策略核心抽象定义。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class StrategyContext:
    """策略运行上下文。"""

    strategy_key: str
    as_of: str


@dataclass(frozen=True)
class StrategySignal:
    """统一策略信号结构。"""

    symbol: str
    action: str
    score: Decimal | None
    reason: str


class StrategyEngine(Protocol):
    """策略引擎协议。"""

    strategy_key: str

    def generate_signals(self) -> list[StrategySignal]:
        """生成交易信号。"""
