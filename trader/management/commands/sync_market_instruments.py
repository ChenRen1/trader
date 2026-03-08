"""将行情配置标的同步到 instruments 表。"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from trader.database import Instrument
from trader.market.config import INDEX_WATCHLIST, MarketInstrument


def _build_payload(item: MarketInstrument) -> tuple[str, dict[str, object]]:
    market_key = item.market.strip().upper()

    if market_key == "CN":
        exchange = Instrument.Exchange.SSE
        if item.key == "CHINEXT":
            exchange = Instrument.Exchange.SZSE
        elif item.key == "BSE_50":
            exchange = Instrument.Exchange.BSE
        elif item.key == "SECURITIES_881157":
            exchange = Instrument.Exchange.SZSE
        return (
            Instrument.Market.CN,
            {
                "name": item.name,
                "exchange": exchange,
                "instrument_type": Instrument.InstrumentType.INDEX,
                "trading_currency": Instrument.Currency.CNY,
                "lot_size": 1,
                "tradable": True,
                "status": Instrument.Status.ACTIVE,
                "data_source": "market-config",
                "notes": item.key,
            },
        )

    if market_key == "HK":
        return (
            Instrument.Market.HK,
            {
                "name": item.name,
                "exchange": Instrument.Exchange.HKEX,
                "instrument_type": Instrument.InstrumentType.INDEX,
                "trading_currency": Instrument.Currency.HKD,
                "lot_size": 1,
                "tradable": True,
                "status": Instrument.Status.ACTIVE,
                "data_source": "market-config",
                "notes": item.key,
            },
        )

    if market_key == "FX":
        trading_currency = Instrument.Currency.CNH
        if item.key == "HKDCNH":
            trading_currency = Instrument.Currency.CNY
        return (
            Instrument.Market.MACRO,
            {
                "name": item.name,
                "exchange": Instrument.Exchange.OTC,
                "instrument_type": Instrument.InstrumentType.FX,
                "trading_currency": trading_currency,
                "lot_size": 1,
                "tradable": False,
                "status": Instrument.Status.ACTIVE,
                "data_source": "market-config",
                "notes": item.key,
            },
        )

    if market_key == "BOND":
        return (
            Instrument.Market.MACRO,
            {
                "name": item.name,
                "exchange": Instrument.Exchange.OTC,
                "instrument_type": Instrument.InstrumentType.RATE,
                "trading_currency": Instrument.Currency.CNY,
                "lot_size": 1,
                "tradable": False,
                "status": Instrument.Status.ACTIVE,
                "data_source": "market-config",
                "notes": item.key,
            },
        )

    raise ValueError(f"unsupported config market: {item.market}")


class Command(BaseCommand):
    help = "将 trader.market.config 中定义的标的同步到 instruments 表。"

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        for item in INDEX_WATCHLIST:
            model_market, defaults = _build_payload(item)
            _, created = Instrument.objects.update_or_create(
                symbol=item.symbol,
                market=model_market,
                defaults=defaults,
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"同步完成：created={created_count}, updated={updated_count}, total={len(INDEX_WATCHLIST)}"
            )
        )
