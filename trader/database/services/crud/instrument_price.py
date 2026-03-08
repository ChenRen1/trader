"""标的价格表服务。"""

from trader.database.models import InstrumentPrice
from trader.database.services.crud.base import CrudService
from trader.database.services.price_sync import PriceSyncService


class InstrumentPriceService(CrudService[InstrumentPrice]):
    """标的价格表创建、更新、删除入口。"""

    model = InstrumentPrice

    @classmethod
    def after_save(cls, instance: InstrumentPrice, *, created: bool) -> None:
        PriceSyncService.sync_price(instance)

    @classmethod
    def before_delete(cls, instance: InstrumentPrice) -> None:
        instance._sync_instrument_id = instance.instrument_id
        instance._sync_bar_type = instance.bar_type

    @classmethod
    def after_delete(cls, instance: InstrumentPrice) -> None:
        if getattr(instance, "_sync_bar_type", "") != InstrumentPrice.BarType.SPOT:
            return

        instrument_id = getattr(instance, "_sync_instrument_id", None)
        if instrument_id is None:
            return

        from trader.database.models import Instrument

        instrument = Instrument.objects.filter(id=instrument_id).first()
        if instrument is not None:
            PriceSyncService.sync_instrument(instrument)
