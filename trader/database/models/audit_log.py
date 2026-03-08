"""审计日志模型。"""

from django.db import models

from trader.database.models.base import TimestampedModel


class AuditLog(TimestampedModel):
    """记录业务表的创建、更新、删除与回滚。"""

    class Operation(models.TextChoices):
        CREATE = "create", "创建"
        UPDATE = "update", "更新"
        DELETE = "delete", "删除"
        ROLLBACK = "rollback", "回滚"

    table_name = models.CharField("表名", max_length=128)
    record_pk = models.CharField("记录主键", max_length=64)
    operation = models.CharField("操作类型", max_length=16, choices=Operation.choices)
    before_data = models.JSONField("变更前数据", null=True, blank=True)
    after_data = models.JSONField("变更后数据", null=True, blank=True)
    actor = models.CharField("操作人", max_length=64, blank=True)
    source = models.CharField("来源", max_length=128, blank=True)
    remark = models.TextField("备注", blank=True)

    class Meta:
        db_table = "audit_logs"
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.table_name}:{self.record_pk}:{self.operation}"
