"""成交表服务。"""

from __future__ import annotations

from trader.database.models import Fill
from trader.database.services.crud.base import CrudService
from trader.database.services.fill_sync import FillSyncService


class FillService(CrudService[Fill]):
    """成交表创建、更新、删除入口。"""

    model = Fill

    @classmethod
    def after_save(cls, instance: Fill, *, created: bool) -> None:
        FillSyncService.sync_fill(instance)

    @classmethod
    def before_delete(cls, instance: Fill) -> None:
        if instance.position_id is not None:
            instance._sync_position_id = instance.position_id
        instance._sync_account_id = instance.account_id

    @classmethod
    def after_delete(cls, instance: Fill) -> None:
        from trader.database.models import Account, Position

        position_id = getattr(instance, "_sync_position_id", None)
        account_id = getattr(instance, "_sync_account_id", None)

        if position_id is not None:
            position = Position.objects.filter(id=position_id).first()
            if position is not None:
                FillSyncService.sync_position(position)

        if account_id is not None:
            account = Account.objects.filter(id=account_id).first()
            if account is not None:
                FillSyncService.recalculate_account(account)

