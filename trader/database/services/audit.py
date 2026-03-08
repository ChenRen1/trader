"""审计日志服务。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Model

from trader.database.models import AuditLog


class AuditLogService:
    """负责写入和回滚审计日志。"""

    @staticmethod
    def log(
        *,
        instance: Model,
        operation: str,
        before_data: dict[str, object] | None,
        after_data: dict[str, object] | None,
        actor: str = "",
        source: str = "",
        remark: str = "",
    ) -> AuditLog:
        return AuditLog.objects.create(
            table_name=instance._meta.db_table,
            record_pk=str(getattr(instance, "_audit_record_pk", instance.pk)),
            operation=operation,
            before_data=before_data,
            after_data=after_data,
            actor=actor,
            source=source,
            remark=remark,
        )

    @staticmethod
    @transaction.atomic
    def rollback(audit_log: AuditLog) -> Model:
        model = AuditLogService._resolve_model(audit_log.table_name)
        previous_instance = model.objects.filter(pk=audit_log.record_pk).first()

        if audit_log.operation == AuditLog.Operation.CREATE:
            instance = model.objects.filter(pk=audit_log.record_pk).first()
            if instance is not None:
                instance.delete()
            rollback_instance = instance or model()
        else:
            payload = audit_log.before_data
            if payload is None:
                raise ValueError("该日志没有可回滚的数据快照")
            rollback_instance = model.objects.filter(pk=audit_log.record_pk).first()
            if rollback_instance is None:
                rollback_instance = model(pk=audit_log.record_pk)
            AuditLogService._apply_snapshot(rollback_instance, payload)
            rollback_instance.full_clean()
            rollback_instance.save()

        AuditLogService.log(
            instance=rollback_instance,
            operation=AuditLog.Operation.ROLLBACK,
            before_data=audit_log.after_data,
            after_data=audit_log.before_data,
            actor="system",
            source="audit.rollback",
            remark=f"rollback from audit log {audit_log.id}",
        )
        AuditLogService._after_rollback(
            table_name=audit_log.table_name,
            previous_instance=previous_instance,
            current_instance=rollback_instance,
            operation=audit_log.operation,
        )
        return rollback_instance

    @staticmethod
    def serialize_instance(instance: Model) -> dict[str, object]:
        payload: dict[str, object] = {}
        for field in instance._meta.concrete_fields:
            payload[field.attname] = AuditLogService._normalize_value(getattr(instance, field.attname))
        return payload

    @staticmethod
    def _normalize_value(value: object) -> object:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return value

    @staticmethod
    def _resolve_model(table_name: str) -> type[Model]:
        from trader.database.models import Account, Fill, Instrument, InstrumentPrice, Position

        model_map = {
            "accounts": Account,
            "fills": Fill,
            "instruments": Instrument,
            "instrument_prices": InstrumentPrice,
            "positions": Position,
        }
        try:
            return model_map[table_name]
        except KeyError as exc:
            raise ValueError(f"不支持回滚的表: {table_name}") from exc

    @staticmethod
    def _apply_snapshot(instance: Model, payload: dict[str, object]) -> None:
        for field in instance._meta.concrete_fields:
            key = field.attname
            if key == "id" and payload.get(key) is None:
                continue
            if key not in payload:
                continue
            setattr(instance, field.attname, payload[key])

    @staticmethod
    def _after_rollback(
        *,
        table_name: str,
        previous_instance: Model | None,
        current_instance: Model,
        operation: str,
    ) -> None:
        from trader.database.models import Account, Fill, Instrument, InstrumentPrice, Position
        from trader.database.services.fill_sync import FillSyncService
        from trader.database.services.price_sync import PriceSyncService

        if table_name == "instrument_prices":
            previous_price = previous_instance if isinstance(previous_instance, InstrumentPrice) else None
            current_price = current_instance if isinstance(current_instance, InstrumentPrice) else None
            instrument_ids: set[int] = set()

            if previous_price is not None and previous_price.bar_type == InstrumentPrice.BarType.SPOT:
                instrument_ids.add(previous_price.instrument_id)
            if current_price is not None and current_price.bar_type == InstrumentPrice.BarType.SPOT:
                instrument_ids.add(current_price.instrument_id)

            for instrument_id in instrument_ids:
                instrument = Instrument.objects.filter(id=instrument_id).first()
                if instrument is not None:
                    PriceSyncService.sync_instrument(instrument)
            return

        if table_name != "fills":
            return

        previous_fill = previous_instance if isinstance(previous_instance, Fill) else None
        current_fill = current_instance if isinstance(current_instance, Fill) else None

        position_ids: set[int] = set()
        account_ids: set[int] = set()

        if previous_fill is not None and previous_fill.position_id is not None:
            position_ids.add(previous_fill.position_id)
        if current_fill is not None and current_fill.position_id is not None:
            position_ids.add(current_fill.position_id)
        if previous_fill is not None and previous_fill.account_id is not None:
            account_ids.add(previous_fill.account_id)
        if current_fill is not None and current_fill.account_id is not None:
            account_ids.add(current_fill.account_id)

        if operation == AuditLog.Operation.CREATE and previous_fill is not None:
            account_ids.add(previous_fill.account_id)

        for position_id in position_ids:
            position = Position.objects.filter(id=position_id).first()
            if position is not None:
                FillSyncService.sync_position(position)

        for account_id in account_ids:
            account = Account.objects.filter(id=account_id).first()
            if account is not None:
                FillSyncService.recalculate_account(account)
