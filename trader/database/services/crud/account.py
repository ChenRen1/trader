"""账户表服务。"""

from trader.database.models import Account
from trader.database.services.crud.base import CrudService


class AccountService(CrudService[Account]):
    """账户表创建、更新、删除入口。"""

    model = Account

