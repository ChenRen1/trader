"""数据库模型基类。"""

from django.db import models


class TimestampedModel(models.Model):
    """通用时间戳基类。"""

    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True

