"""持仓表服务。"""

from trader.database.models import Position
from trader.database.services.crud.base import CrudService


class PositionService(CrudService[Position]):
    """持仓表创建、更新、删除入口。"""

    model = Position

