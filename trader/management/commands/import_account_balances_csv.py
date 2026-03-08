"""从账户余额 CSV 导入账户现金数据。"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from trader.database import Account, AccountService


class Command(BaseCommand):
    """导入账户现金余额。"""

    help = "从 account_code/available_cash 等字段组成的 CSV 更新账户现金余额。"

    required_headers = {
        "account_code",
        "available_cash",
        "frozen_cash",
        "liability",
        "risk_limit",
        "notes",
    }

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV 文件不存在: {csv_path}")

        created_count = 0
        updated_count = 0

        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise CommandError("CSV 文件缺少表头")
            missing_headers = self.required_headers - set(reader.fieldnames)
            if missing_headers:
                raise CommandError(f"CSV 缺少字段: {sorted(missing_headers)}")

            for raw in reader:
                account_code = raw["account_code"].strip()
                available_cash = Decimal(raw["available_cash"].strip() or "0")
                frozen_cash = Decimal(raw["frozen_cash"].strip() or "0")
                liability = Decimal(raw["liability"].strip() or "0")
                risk_limit = Decimal(raw["risk_limit"].strip() or "0")
                notes = raw["notes"].strip()

                account = Account.objects.filter(account_code=account_code).first()
                payload = {
                    "available_cash": available_cash.quantize(Decimal("0.0001")),
                    "frozen_cash": frozen_cash.quantize(Decimal("0.0001")),
                    "liability": liability.quantize(Decimal("0.0001")),
                    "risk_limit": risk_limit.quantize(Decimal("0.0001")),
                    "total_equity": (
                        Decimal(str(account.total_market_value if account else Decimal("0")))
                        + available_cash
                        + frozen_cash
                        - liability
                    ).quantize(Decimal("0.0001")),
                    "notes": self._build_notes(
                        existing_notes=account.notes if account else "",
                        imported_notes=notes,
                    ),
                }

                if account is None:
                    account_type = (
                        Account.AccountType.MARGIN if liability > 0 else Account.AccountType.CASH
                    )
                    AccountService.create(
                        audit_actor="system",
                        audit_source="command:import_account_balances_csv",
                        audit_remark="create account from account balances csv",
                        account_code=account_code,
                        account_name=account_code,
                        account_type=account_type,
                        base_currency=Account.Currency.CNY,
                        broker_name="CSV导入",
                        initial_balance=Decimal("0"),
                        total_market_value=Decimal("0"),
                        total_unrealized_pnl=Decimal("0"),
                        status=Account.Status.ACTIVE,
                        **payload,
                    )
                    created_count += 1
                    continue

                AccountService.update(
                    account,
                    audit_actor="system",
                    audit_source="command:import_account_balances_csv",
                    audit_remark="update account cash balances from csv",
                    account_type=Account.AccountType.MARGIN if liability > 0 else account.account_type,
                    **payload,
                )
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"导入完成：created={created_count}, updated={updated_count}"
            )
        )

    def _build_notes(
        self,
        *,
        existing_notes: str,
        imported_notes: str,
    ) -> str:
        lines: list[str] = []
        if existing_notes:
            lines.append(existing_notes)
        if imported_notes:
            lines.append(imported_notes)

        # 去重但保留顺序
        unique_lines: list[str] = []
        seen: set[str] = set()
        for line in lines:
            if line not in seen:
                unique_lines.append(line)
                seen.add(line)
        return "\n".join(unique_lines)
