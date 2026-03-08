"""标的表服务。"""

from trader.database.models import Instrument
from trader.database.services.crud.base import CrudService


class InstrumentService(CrudService[Instrument]):
    """标的表创建、更新、删除入口。"""

    model = Instrument

