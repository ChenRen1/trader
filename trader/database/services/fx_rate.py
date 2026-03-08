"""账户与持仓使用的汇率换算服务。"""

from __future__ import annotations

from decimal import Decimal

from trader.database.models import Instrument, InstrumentPrice

FOUR_DP = Decimal("0.0001")


class FxRateService:
    """从数据库中的汇率标的读取最新汇率。"""

    @staticmethod
    def convert(amount: Decimal, source_currency: str, target_currency: str) -> Decimal:
        source = source_currency.strip().upper()
        target = target_currency.strip().upper()
        if source == target:
            return amount.quantize(FOUR_DP)

        for src_currency in FxRateService._currency_aliases(source):
            for dst_currency in FxRateService._currency_aliases(target):
                direct_symbol = f"{src_currency}{dst_currency}"
                direct_rate = FxRateService._latest_rate(direct_symbol)
                if direct_rate is not None:
                    return (amount * direct_rate).quantize(FOUR_DP)

                inverse_symbol = f"{dst_currency}{src_currency}"
                inverse_rate = FxRateService._latest_rate(inverse_symbol)
                if inverse_rate not in {None, Decimal('0')}:
                    return (amount / inverse_rate).quantize(FOUR_DP)

        raise ValueError(f"缺少汇率数据: {source}->{target}")

    @staticmethod
    def _currency_aliases(currency: str) -> tuple[str, ...]:
        if currency == "CNY":
            return ("CNY", "CNH")
        if currency == "CNH":
            return ("CNH", "CNY")
        return (currency,)

    @staticmethod
    def _latest_rate(symbol: str) -> Decimal | None:
        instrument = Instrument.objects.filter(
            symbol=symbol,
            market=Instrument.Market.MACRO,
            instrument_type=Instrument.InstrumentType.FX,
        ).first()
        if instrument is None:
            return None

        latest_price = (
            InstrumentPrice.objects.filter(
                instrument=instrument,
                bar_type=InstrumentPrice.BarType.SPOT,
            )
            .order_by("-priced_at", "-created_at")
            .values_list("last_price", flat=True)
            .first()
        )
        if latest_price is None:
            return None
        return Decimal(str(latest_price))
