"""Admin 注册入口。"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import Model

from trader.database import (
    Account,
    AccountService,
    AuditLog,
    Fill,
    FillService,
    Instrument,
    InstrumentPrice,
    InstrumentService,
    InstrumentPriceService,
    Position,
    PositionService,
)


class ServiceBackedAdmin(admin.ModelAdmin):
    """通过服务层执行保存和删除。"""

    service = None

    def save_model(self, request, obj, form, change):
        payload = self._build_payload(obj)
        actor = request.user.get_username() if request.user.is_authenticated else ""
        source = f"admin:{obj._meta.model_name}"

        if change:
            saved = self.service.update(
                obj,
                audit_actor=actor,
                audit_source=source,
                audit_remark="admin update",
                **payload,
            )
        else:
            saved = self.service.create(
                audit_actor=actor,
                audit_source=source,
                audit_remark="admin create",
                **payload,
            )

        self._copy_instance_state(obj, saved)

    def delete_model(self, request, obj):
        actor = request.user.get_username() if request.user.is_authenticated else ""
        source = f"admin:{obj._meta.model_name}"
        self.service.delete(
            obj,
            audit_actor=actor,
            audit_source=source,
            audit_remark="admin delete",
        )

    def _build_payload(self, obj: Model) -> dict[str, object]:
        payload: dict[str, object] = {}
        for field in obj._meta.concrete_fields:
            if field.primary_key or field.auto_created:
                continue
            if field.name in {"created_at", "updated_at"}:
                continue
            payload[field.name] = getattr(obj, field.name)
        return payload

    def _copy_instance_state(self, target: Model, source: Model) -> None:
        for field in source._meta.concrete_fields:
            setattr(target, field.attname, getattr(source, field.attname))
        target._state.adding = False


@admin.register(Account)
class AccountAdmin(ServiceBackedAdmin):
    service = AccountService
    list_display = ("account_code", "account_name", "account_type", "base_currency", "available_cash", "status")
    search_fields = ("account_code", "account_name", "broker_name")


@admin.register(Instrument)
class InstrumentAdmin(ServiceBackedAdmin):
    service = InstrumentService
    list_display = ("symbol", "name", "market", "exchange", "instrument_type", "trading_currency", "status")
    search_fields = ("symbol", "name")
    list_filter = ("market", "exchange", "instrument_type", "status")


@admin.register(Position)
class PositionAdmin(ServiceBackedAdmin):
    service = PositionService
    list_display = ("account", "instrument", "side", "quantity", "average_price", "status")
    list_filter = ("side", "status", "pricing_currency")


@admin.register(Fill)
class FillAdmin(ServiceBackedAdmin):
    service = FillService
    list_display = ("account", "instrument", "side", "quantity", "price", "fill_time")
    list_filter = ("side", "pricing_currency")


@admin.register(InstrumentPrice)
class InstrumentPriceAdmin(ServiceBackedAdmin):
    service = InstrumentPriceService
    list_display = ("instrument", "bar_type", "last_price", "priced_at", "source")
    list_filter = ("bar_type", "source")
    search_fields = ("instrument__symbol", "instrument__name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("table_name", "record_pk", "operation", "actor", "source", "created_at")
    list_filter = ("operation", "table_name", "actor")
    search_fields = ("table_name", "record_pk", "actor", "source")
    readonly_fields = (
        "table_name",
        "record_pk",
        "operation",
        "before_data",
        "after_data",
        "actor",
        "source",
        "remark",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
