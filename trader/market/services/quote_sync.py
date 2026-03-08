"""按配置标的同步现价到数据库。"""

from __future__ import annotations

from trader.database.models import Instrument
from trader.database.services.price_sync import PriceSyncService
from trader.market.config import INDEX_WATCHLIST, MarketInstrument


class MarketQuoteSyncService:
    """市场层现价同步服务。"""

    _MARKET_MAP = {
        "CN": Instrument.Market.CN,
        "HK": Instrument.Market.HK,
        "FX": Instrument.Market.MACRO,
        "BOND": Instrument.Market.MACRO,
    }

    @classmethod
    def _resolve_instrument(cls, item: MarketInstrument) -> Instrument | None:
        model_market = cls._MARKET_MAP.get(item.market.strip().upper())
        if model_market is None:
            return None
        return Instrument.objects.filter(symbol=item.symbol, market=model_market).first()

    @classmethod
    def sync_config_spot_prices(cls) -> dict[str, object]:
        """根据 config 标的列表同步现价到 instrument_prices。"""
        instruments: list[Instrument] = []
        missing: list[dict[str, str]] = []
        for item in INDEX_WATCHLIST:
            instrument = cls._resolve_instrument(item)
            if instrument is None:
                missing.append(
                    {
                        "key": item.key,
                        "symbol": item.symbol,
                        "market": item.market,
                        "reason": "instrument not found in database",
                    }
                )
                continue
            instruments.append(instrument)

        sync_result = PriceSyncService.update_spot_prices(instruments=instruments)
        return {
            "total": len(INDEX_WATCHLIST),
            "matched": len(instruments),
            "missing": missing,
            "sync": sync_result,
        }

