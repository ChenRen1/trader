"""策略注册与发现。"""

from __future__ import annotations

from typing import Dict

from trader.strategy.core.base import StrategyEngine

_REGISTRY: Dict[str, StrategyEngine] = {}


def register_strategy(engine: StrategyEngine) -> None:
    key = engine.strategy_key.strip().lower()
    _REGISTRY[key] = engine


def get_strategy(strategy_key: str) -> StrategyEngine:
    key = strategy_key.strip().lower()
    if key not in _REGISTRY:
        raise KeyError(f"strategy not found: {strategy_key}")
    return _REGISTRY[key]


def list_strategies() -> list[str]:
    return sorted(_REGISTRY.keys())
