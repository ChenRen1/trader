"""数据库导出服务。"""

from __future__ import annotations

import csv
from pathlib import Path

from django.db.models import Model, QuerySet


class TableExportService:
    """通用表导出服务。"""

    @staticmethod
    def export_to_csv(
        model: type[Model],
        file_path: str | Path,
        *,
        queryset: QuerySet[Model] | None = None,
        fields: list[str] | None = None,
    ) -> Path:
        """将指定模型数据导出为 CSV。"""
        export_path = Path(file_path)
        export_path.parent.mkdir(parents=True, exist_ok=True)

        selected_fields = fields or [
            field.name
            for field in model._meta.concrete_fields
        ]
        data = queryset if queryset is not None else model.objects.all()

        with export_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(selected_fields)
            for row in data.values_list(*selected_fields):
                writer.writerow(row)

        return export_path
