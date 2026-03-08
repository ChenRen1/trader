"""Provider 层：对外接口与按市场路由。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

from trader.market.source.sources import AkshareSource, YfinanceSource


class MarketDataSource(Protocol):
    """数据源协议：由各 source 模块具体实现。"""

    def get_spot_price(self, symbol: str, market: str) -> dict[str, object]: ...

    def get_kline(
        self,
        symbol: str,
        market: str,
        *,
        limit: int = 120,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, object]]: ...


class MarketDataProvider(ABC):
    """对外统一 Provider 接口。"""

    @abstractmethod
    def get_spot_price(self, symbol: str, market: str) -> dict[str, object]:
        """根据市场路由并返回现价。"""

    @abstractmethod
    def get_kline(
        self,
        symbol: str,
        market: str,
        *,
        limit: int = 120,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, object]]:
        """根据市场路由并返回 K 线。"""


class DefaultMarketProvider(MarketDataProvider):
    """默认 Provider：market 路由 + 多数据源兜底。"""

    def __init__(self) -> None:
        self._sources_by_market: dict[str, list[MarketDataSource]] = {
            "CN": [AkshareSource()],
            "HK": [AkshareSource(), YfinanceSource()],
            "FX": [YfinanceSource()],
            "MACRO": [AkshareSource(), YfinanceSource()],
        }

    def get_spot_price(self, symbol: str, market: str) -> dict[str, object]:
        market_key = market.strip().upper()
        last_error: Exception | None = None
        for source in self._sources_by_market.get(market_key, []):
            try:
                return source.get_spot_price(symbol, market_key)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise RuntimeError(f"spot price unavailable for {market_key}:{symbol}: {last_error}") from last_error
        raise ValueError(f"unsupported market: {market}")

    def get_kline(
        self,
        symbol: str,
        market: str,
        *,
        limit: int = 120,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, object]]:
        market_key = market.strip().upper()
        last_error: Exception | None = None
        for source in self._sources_by_market.get(market_key, []):
            try:
                return source.get_kline(
                    symbol,
                    market_key,
                    limit=limit,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise RuntimeError(f"kline unavailable for {market_key}:{symbol}: {last_error}") from last_error
        raise ValueError(f"unsupported market: {market}")


DEFAULT_PROVIDER = DefaultMarketProvider()


def get_spot_price(symbol: str, market: str) -> dict[str, object]:
    """通用现价接口（通过 Provider 路由）。"""
    return DEFAULT_PROVIDER.get_spot_price(symbol, market)


def get_kline(
    symbol: str,
    market: str,
    *,
    limit: int = 120,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, object]]:
    """通用 K 线接口（通过 Provider 路由）。"""
    return DEFAULT_PROVIDER.get_kline(
        symbol,
        market,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
