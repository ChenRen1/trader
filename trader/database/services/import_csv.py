"""数据库 CSV 导入服务。"""

from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.db.models import BooleanField, DateField, DateTimeField, Field, Model

from trader.database.models import Account, Fill, Instrument, InstrumentPrice, Position
from trader.database.services.crud import (
    AccountService,
    CrudService,
    FillService,
    InstrumentPriceService,
    InstrumentService,
    PositionService,
)


class TableImportService:
    """将导出的 CSV 回导到指定业务表。"""

    SERVICE_MAP: dict[type[Model], type[CrudService[Any]]] = {
        Account: AccountService,
        Fill: FillService,
        Instrument: InstrumentService,
        InstrumentPrice: InstrumentPriceService,
        Position: PositionService,
    }

    @classmethod
    def import_from_csv(
        cls,
        model: type[Model],
        file_path: str | Path,
        *,
        audit_actor: str = "",
        audit_source: str = "",
        audit_remark: str = "",
    ) -> dict[str, int]:
        """按 CSV 内容创建或更新数据。"""
        import_path = Path(file_path)
        service = cls.SERVICE_MAP[model]
        created_count = 0
        updated_count = 0

        with import_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                return {"created": 0, "updated": 0}

            for row in reader:
                payload = cls._build_payload(model, row)
                object_id = payload.pop("id", None)

                if object_id:
                    instance = model.objects.filter(pk=object_id).first()
                    if instance is not None:
                        service.update(
                            instance,
                            audit_actor=audit_actor,
                            audit_source=audit_source,
                            audit_remark=audit_remark,
                            **payload,
                        )
                        updated_count += 1
                        continue

                    payload["id"] = object_id

                service.create(
                    audit_actor=audit_actor,
                    audit_source=audit_source,
                    audit_remark=audit_remark,
                    **payload,
                )
                created_count += 1

        return {"created": created_count, "updated": updated_count}

    @staticmethod
    def _build_payload(model: type[Model], row: dict[str, str]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for field in model._meta.concrete_fields:
            csv_key = field.name
            if csv_key not in row:
                continue
            raw_value = row[csv_key]
            payload[field.attname] = TableImportService._parse_value(field, raw_value)
        return payload

    @staticmethod
    def _parse_value(field: Field, raw_value: str) -> Any:
        if raw_value == "":
            if field.null:
                return None
            if isinstance(field, BooleanField):
                return False
            return raw_value

        if isinstance(field, BooleanField):
            return raw_value.lower() in {"1", "true", "yes", "y", "on"}
        if isinstance(field, DateTimeField):
            return datetime.fromisoformat(raw_value)
        if isinstance(field, DateField):
            return date.fromisoformat(raw_value)
        if field.get_internal_type() in {"DecimalField"}:
            return Decimal(raw_value)
        if field.get_internal_type() in {"IntegerField", "BigIntegerField", "PositiveIntegerField", "PositiveSmallIntegerField", "SmallIntegerField", "AutoField", "BigAutoField"}:
            return int(raw_value)
        return raw_value
