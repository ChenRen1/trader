"""通用数据库 CRUD 服务。"""

from __future__ import annotations

from typing import Generic, TypeVar

from django.db import transaction
from django.db.models import Model

from trader.database.services.audit import AuditLogService

ModelType = TypeVar("ModelType", bound=Model)


class CrudService(Generic[ModelType]):
    """通用创建、更新、删除服务。"""

    model: type[ModelType]

    @classmethod
    @transaction.atomic
    def create(
        cls,
        *,
        audit_actor: str = "",
        audit_source: str = "",
        audit_remark: str = "",
        **payload: object,
    ) -> ModelType:
        instance = cls.model(**payload)
        instance.full_clean()
        instance.save()
        cls.after_save(instance, created=True)
        AuditLogService.log(
            instance=instance,
            operation="create",
            before_data=None,
            after_data=AuditLogService.serialize_instance(instance),
            actor=audit_actor,
            source=audit_source,
            remark=audit_remark,
        )
        return instance

    @classmethod
    @transaction.atomic
    def update(
        cls,
        instance: ModelType,
        *,
        audit_actor: str = "",
        audit_source: str = "",
        audit_remark: str = "",
        **changes: object,
    ) -> ModelType:
        before_data = AuditLogService.serialize_instance(instance)
        for field_name, value in changes.items():
            setattr(instance, field_name, value)
        instance.full_clean()
        instance.save()
        cls.after_save(instance, created=False)
        AuditLogService.log(
            instance=instance,
            operation="update",
            before_data=before_data,
            after_data=AuditLogService.serialize_instance(instance),
            actor=audit_actor,
            source=audit_source,
            remark=audit_remark,
        )
        return instance

    @classmethod
    @transaction.atomic
    def delete(
        cls,
        instance: ModelType,
        *,
        audit_actor: str = "",
        audit_source: str = "",
        audit_remark: str = "",
    ) -> None:
        before_data = AuditLogService.serialize_instance(instance)
        instance._audit_record_pk = str(instance.pk)
        cls.before_delete(instance)
        instance.delete()
        cls.after_delete(instance)
        AuditLogService.log(
            instance=instance,
            operation="delete",
            before_data=before_data,
            after_data=None,
            actor=audit_actor,
            source=audit_source,
            remark=audit_remark,
        )

    @classmethod
    def after_save(cls, instance: ModelType, *, created: bool) -> None:
        """保存后的扩展点。"""

    @classmethod
    def before_delete(cls, instance: ModelType) -> None:
        """删除前的扩展点。"""

    @classmethod
    def after_delete(cls, instance: ModelType) -> None:
        """删除后的扩展点。"""
