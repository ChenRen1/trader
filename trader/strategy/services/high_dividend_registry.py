"""高股息标的登记服务。"""

from __future__ import annotations

from dataclasses import dataclass

from trader.database import Instrument
from trader.strategy.services.universe import DividendUniverseConfig, DividendUniverseService, IndexConstituent


@dataclass(frozen=True)
class HighDividendSyncResult:
    universe_size: int
    created: int
    marked: int
    cleared: int


class HighDividendRegistryService:
    """将红利指数成分同步到 Instrument.is_high_dividend。"""

    @staticmethod
    def _infer_exchange(symbol: str) -> str:
        if symbol.startswith(("6",)):
            return Instrument.Exchange.SSE
        if symbol.startswith(("0", "3")):
            return Instrument.Exchange.SZSE
        if symbol.startswith(("4", "8")):
            return Instrument.Exchange.BSE
        return Instrument.Exchange.SSE

    @classmethod
    def _ensure_instrument(cls, item: IndexConstituent) -> tuple[Instrument, bool]:
        instrument, created = Instrument.objects.get_or_create(
            symbol=item.symbol,
            market=Instrument.Market.CN,
            defaults={
                "name": item.name or item.symbol,
                "exchange": cls._infer_exchange(item.symbol),
                "instrument_type": Instrument.InstrumentType.STOCK,
                "trading_currency": Instrument.Currency.CNY,
                "tradable": True,
                "is_high_dividend": False,
                "data_source": f"dividend-universe:{item.index_code}",
            },
        )
        return instrument, created

    @classmethod
    def sync_from_dividend_indices(
        cls,
        *,
        config: DividendUniverseConfig | None = None,
        create_missing: bool = True,
    ) -> HighDividendSyncResult:
        universe = DividendUniverseService.build_universe(config=config)
        target_symbols = {item.symbol for item in universe}

        created = 0
        marked = 0
        if create_missing:
            for item in universe:
                _, is_created = cls._ensure_instrument(item)
                if is_created:
                    created += 1

        cleared = Instrument.objects.filter(
            market=Instrument.Market.CN,
            instrument_type=Instrument.InstrumentType.STOCK,
            is_high_dividend=True,
        ).exclude(symbol__in=target_symbols).update(is_high_dividend=False)

        marked = Instrument.objects.filter(
            market=Instrument.Market.CN,
            symbol__in=target_symbols,
        ).exclude(is_high_dividend=True).update(is_high_dividend=True)

        return HighDividendSyncResult(
            universe_size=len(target_symbols),
            created=created,
            marked=marked,
            cleared=cleared,
        )
