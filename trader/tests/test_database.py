"""数据库层测试。"""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class TableExportServiceTests(TestCase):
    def test_export_to_csv_exports_selected_model_rows(self) -> None:
        from trader.database import Account, TableExportService

        Account.objects.create(
            account_code="ACC001",
            account_name="测试账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
        )

        output_path = Path("tmp") / "accounts.csv"
        exported = TableExportService.export_to_csv(
            Account,
            output_path,
            fields=["account_code", "account_name", "account_type"],
        )

        assert exported.exists()
        with exported.open("r", encoding="utf-8", newline="") as csv_file:
            rows = list(csv.reader(csv_file))

        assert rows[0] == ["account_code", "account_name", "account_type"]
        assert rows[1] == ["ACC001", "测试账户", "普通账户"]

        exported.unlink()
        exported.parent.rmdir()

    def test_import_from_csv_creates_and_updates_accounts(self) -> None:
        from trader.database import Account, TableImportService

        output_path = Path("tmp") / "accounts_import.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "id",
                    "account_code",
                    "account_name",
                    "account_type",
                    "base_currency",
                    "broker_name",
                    "initial_balance",
                    "available_cash",
                    "total_market_value",
                    "total_unrealized_pnl",
                    "total_equity",
                    "status",
                    "notes",
                ]
            )
            writer.writerow(
                [
                    "",
                    "ACC-CSV-001",
                    "CSV账户",
                    "普通账户",
                    "CNY",
                    "CSV券商",
                    "10000.0000",
                    "10000.0000",
                    "0.0000",
                    "0.0000",
                    "10000.0000",
                    "启用",
                    "csv-import",
                ]
            )

        result = TableImportService.import_from_csv(
            Account,
            output_path,
            audit_actor="tester",
            audit_source="test.import",
            audit_remark="import accounts",
        )

        account = Account.objects.get(account_code="ACC-CSV-001")
        assert result == {"created": 1, "updated": 0}
        assert account.account_name == "CSV账户"

        with output_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "id",
                    "account_code",
                    "account_name",
                    "account_type",
                    "base_currency",
                    "broker_name",
                    "initial_balance",
                    "available_cash",
                    "total_market_value",
                    "total_unrealized_pnl",
                    "total_equity",
                    "status",
                    "notes",
                ]
            )
            writer.writerow(
                [
                    str(account.id),
                    "ACC-CSV-001",
                    "CSV账户-更新",
                    "普通账户",
                    "CNY",
                    "CSV券商",
                    "10000.0000",
                    "9800.0000",
                    "200.0000",
                    "50.0000",
                    "10000.0000",
                    "启用",
                    "csv-import",
                ]
            )

        result = TableImportService.import_from_csv(Account, output_path)
        account.refresh_from_db()

        assert result == {"created": 0, "updated": 1}
        assert account.account_name == "CSV账户-更新"
        assert account.available_cash == account.available_cash.__class__("9800.0000")

        output_path.unlink()
        output_path.parent.rmdir()

    def test_import_from_csv_uses_price_service_sync(self) -> None:
        from trader.database import Account, Fill, FillService, Instrument, InstrumentPrice, Position, TableImportService

        account = Account.objects.create(
            account_code="ACC-CSV-002",
            account_name="CSV价格联动账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="10000.0000",
            available_cash="10000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="601166",
            name="兴业银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        FillService.create(
            account=account,
            instrument=instrument,
            fill_time=timezone.now(),
            side=Fill.Side.BUY,
            quantity="100.00000000",
            price="20.0000",
            amount="2000.0000",
            commission="0.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )

        output_path = Path("tmp") / "instrument_prices_import.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "id",
                    "instrument",
                    "bar_type",
                    "priced_at",
                    "open_price",
                    "high_price",
                    "low_price",
                    "close_price",
                    "last_price",
                    "prev_close",
                    "volume",
                    "turnover",
                    "source",
                ]
            )
            writer.writerow(
                [
                    "",
                    str(instrument.id),
                    "spot",
                    timezone.now().isoformat(),
                    "",
                    "",
                    "",
                    "",
                    "21.5000",
                    "20.8000",
                    "0",
                    "0",
                    "csv.import",
                ]
            )

        result = TableImportService.import_from_csv(InstrumentPrice, output_path)

        account.refresh_from_db()
        position = Position.objects.get(account=account, instrument=instrument)

        assert result == {"created": 1, "updated": 0}
        assert position.market_value == position.market_value.__class__("2150.0000")
        assert position.unrealized_pnl == position.unrealized_pnl.__class__("150.0000")
        assert account.total_market_value == account.total_market_value.__class__("2150.0000")
        assert account.total_equity == account.total_equity.__class__("10150.0000")

        output_path.unlink()
        output_path.parent.rmdir()


class FillSyncServiceTests(TestCase):
    def test_sync_fill_updates_position_and_account(self) -> None:
        from trader.database import (
            Account,
            Fill,
            FillSyncService,
            Instrument,
            InstrumentPrice,
            InstrumentPriceService,
            Position,
        )

        account = Account.objects.create(
            account_code="ACC002",
            account_name="同步测试账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="100000.0000",
            available_cash="100000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="600000",
            name="浦发银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        InstrumentPriceService.create(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=timezone.now(),
            last_price="10.5000",
        )
        fill = Fill.objects.create(
            account=account,
            instrument=instrument,
            fill_time=timezone.now(),
            side=Fill.Side.BUY,
            quantity="100.00000000",
            price="10.0000",
            amount="1000.0000",
            commission="1.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )

        position = FillSyncService.sync_fill(fill)

        fill.refresh_from_db()
        position.refresh_from_db()
        account.refresh_from_db()

        assert fill.position_id == position.id
        assert position.status == Position.Status.OPEN
        assert position.side == Position.Side.LONG
        assert position.quantity == position.available_quantity == position.quantity.__class__("100.00000000")
        assert position.average_price == position.average_price.__class__("10.0000")
        assert position.cost_basis == position.cost_basis.__class__("1000.0000")
        assert position.market_value == position.market_value.__class__("1050.0000")
        assert position.unrealized_pnl == position.unrealized_pnl.__class__("50.0000")
        assert account.available_cash == account.available_cash.__class__("98999.0000")

    def test_sync_fill_recalculates_after_sell(self) -> None:
        from trader.database import Account, Fill, FillSyncService, Instrument, Position

        account = Account.objects.create(
            account_code="ACC003",
            account_name="减仓测试账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="10000.0000",
            available_cash="10000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="600519",
            name="贵州茅台",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        position = Position.objects.create(
            account=account,
            instrument=instrument,
            pricing_currency=Instrument.Currency.CNY,
        )
        buy_fill = Fill.objects.create(
            account=account,
            instrument=instrument,
            position=position,
            fill_time=timezone.now(),
            side=Fill.Side.BUY,
            quantity="10.00000000",
            price="100.0000",
            amount="1000.0000",
            commission="0.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )
        sell_fill = Fill.objects.create(
            account=account,
            instrument=instrument,
            position=position,
            fill_time=timezone.now(),
            side=Fill.Side.SELL,
            quantity="4.00000000",
            price="110.0000",
            amount="440.0000",
            commission="1.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )

        FillSyncService.sync_fill(buy_fill)
        FillSyncService.sync_fill(sell_fill)

        position.refresh_from_db()
        account.refresh_from_db()

        assert position.status == Position.Status.OPEN
        assert position.quantity == position.quantity.__class__("6.00000000")
        assert position.average_price == position.average_price.__class__("100.0000")
        assert position.cost_basis == position.cost_basis.__class__("600.0000")
        assert account.available_cash == account.available_cash.__class__("9439.0000")
        assert account.total_market_value == account.total_market_value.__class__("600.0000")
        assert account.total_unrealized_pnl == account.total_unrealized_pnl.__class__("0.0000")
        assert account.total_equity == account.total_equity.__class__("10039.0000")

    def test_account_totals_convert_hkd_positions_to_cny(self) -> None:
        from trader.database import Account, FillSyncService, Instrument, InstrumentPrice, Position

        account = Account.objects.create(
            account_code="ACC-HKD-001",
            account_name="港币折算账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            available_cash="1000.0000",
        )
        fx_instrument = Instrument.objects.create(
            symbol="HKDCNH",
            name="港币兑人民币",
            market=Instrument.Market.MACRO,
            exchange=Instrument.Exchange.OTC,
            instrument_type=Instrument.InstrumentType.FX,
            trading_currency=Instrument.Currency.CNY,
        )
        InstrumentPrice.objects.create(
            instrument=fx_instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=timezone.now(),
            last_price="0.8826",
            source="test.fx",
        )
        hk_instrument = Instrument.objects.create(
            symbol="00700",
            name="腾讯控股",
            market=Instrument.Market.HK,
            exchange=Instrument.Exchange.HKEX,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.HKD,
        )
        Position.objects.create(
            account=account,
            instrument=hk_instrument,
            side=Position.Side.LONG,
            quantity="100.00000000",
            available_quantity="100.00000000",
            average_price="450.0000",
            cost_basis="45000.0000",
            market_value="48000.0000",
            unrealized_pnl="3000.0000",
            pricing_currency=Instrument.Currency.HKD,
            status=Position.Status.OPEN,
        )

        FillSyncService.recalculate_account(account)
        account.refresh_from_db()

        assert account.total_market_value == account.total_market_value.__class__("42364.8000")
        assert account.total_unrealized_pnl == account.total_unrealized_pnl.__class__("2647.8000")
        assert account.total_equity == account.total_equity.__class__("43364.8000")


class PriceSyncServiceTests(TestCase):
    def test_update_instrument_spot_price_creates_spot_record(self) -> None:
        from trader.database import Instrument, InstrumentPrice, PriceSyncService

        instrument = Instrument.objects.create(
            symbol="000300",
            name="沪深300",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.INDEX,
            trading_currency=Instrument.Currency.CNY,
        )
        quoted_at = timezone.now()
        with patch(
            "trader.database.services.price_sync.get_spot_price",
            return_value={
                "symbol": "000300",
                "market": "CN",
                "last_price": "3900.1200",
                "prev_close": "3890.0000",
                "quoted_at": quoted_at,
                "source": "test.provider",
            },
        ):
            price = PriceSyncService.update_instrument_spot_price(instrument)

        assert price.bar_type == InstrumentPrice.BarType.SPOT
        assert price.last_price == price.last_price.__class__("3900.1200")
        assert price.prev_close == price.prev_close.__class__("3890.0000")
        assert price.source == "test.provider"
        assert InstrumentPrice.objects.filter(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=quoted_at,
        ).count() == 1

    def test_update_instrument_spot_price_updates_existing_record_with_same_timestamp(self) -> None:
        from trader.database import Instrument, InstrumentPrice, PriceSyncService

        instrument = Instrument.objects.create(
            symbol="9988",
            name="阿里巴巴",
            market=Instrument.Market.HK,
            exchange=Instrument.Exchange.HKEX,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.HKD,
        )
        quoted_at = timezone.now()
        InstrumentPrice.objects.create(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=quoted_at,
            last_price="100.0000",
            source="seed",
        )

        with patch(
            "trader.database.services.price_sync.get_spot_price",
            return_value={
                "symbol": "9988",
                "market": "HK",
                "last_price": "101.8800",
                "prev_close": "99.9000",
                "quoted_at": quoted_at,
                "source": "test.provider",
            },
        ):
            price = PriceSyncService.update_instrument_spot_price(instrument)

        assert InstrumentPrice.objects.filter(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=quoted_at,
        ).count() == 1
        assert price.last_price == price.last_price.__class__("101.8800")
        assert price.prev_close == price.prev_close.__class__("99.9000")
        assert price.source == "test.provider"

    def test_sync_price_keeps_manual_position_quantity(self) -> None:
        from trader.database import Account, Instrument, InstrumentPriceService, Position, PositionService

        account = Account.objects.create(
            account_code="ACC-PRICE-001",
            account_name="手工持仓账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
        )
        instrument = Instrument.objects.create(
            symbol="159919",
            name="沪深300ETF",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SZSE,
            instrument_type=Instrument.InstrumentType.ETF,
            trading_currency=Instrument.Currency.CNY,
        )
        position = PositionService.create(
            account=account,
            instrument=instrument,
            side=Position.Side.LONG,
            quantity="20000.00000000",
            available_quantity="20000.00000000",
            average_price="4.7210",
            cost_basis="94420.0000",
            market_value="94420.0000",
            unrealized_pnl="0.0000",
            pricing_currency=Instrument.Currency.CNY,
            status=Position.Status.OPEN,
        )

        InstrumentPriceService.create(
            instrument=instrument,
            bar_type="spot",
            priced_at=timezone.now(),
            last_price="4.8650",
            source="test.spot",
        )

        position.refresh_from_db()
        account.refresh_from_db()

        assert position.quantity == position.quantity.__class__("20000.00000000")
        assert position.available_quantity == position.available_quantity.__class__("20000.00000000")
        assert position.market_value == position.market_value.__class__("97300.0000")
        assert position.unrealized_pnl == position.unrealized_pnl.__class__("2880.0000")
        assert account.total_market_value == account.total_market_value.__class__("97300.0000")


class CrudServiceTests(TestCase):
    def test_specialized_services_are_available(self) -> None:
        from trader.database import AccountService, InstrumentPriceService, InstrumentService, PositionService
        from trader.database.services.crud.base import CrudService

        assert issubclass(AccountService, CrudService)
        assert issubclass(InstrumentService, CrudService)
        assert issubclass(InstrumentPriceService, CrudService)
        assert issubclass(PositionService, CrudService)

    def test_fill_service_create_triggers_position_and_account_sync(self) -> None:
        from trader.database import Account, FillService, Instrument, Position

        account = Account.objects.create(
            account_code="ACC004",
            account_name="服务创建账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="5000.0000",
            available_cash="5000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="300750",
            name="宁德时代",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SZSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )

        fill = FillService.create(
            account=account,
            instrument=instrument,
            fill_time=timezone.now(),
            side="买入",
            quantity="5.00000000",
            price="200.0000",
            amount="1000.0000",
            commission="2.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )

        account.refresh_from_db()
        fill.refresh_from_db()
        position = Position.objects.get(id=fill.position_id)

        assert position.quantity == position.quantity.__class__("5.00000000")
        assert account.available_cash == account.available_cash.__class__("3998.0000")

    def test_fill_service_delete_triggers_resync(self) -> None:
        from trader.database import Account, Fill, FillService, Instrument, Position

        account = Account.objects.create(
            account_code="ACC005",
            account_name="服务删除账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="5000.0000",
            available_cash="5000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="000001",
            name="平安银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SZSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        position = Position.objects.create(
            account=account,
            instrument=instrument,
            pricing_currency=Instrument.Currency.CNY,
        )
        fill = Fill.objects.create(
            account=account,
            instrument=instrument,
            position=position,
            fill_time=timezone.now(),
            side=Fill.Side.BUY,
            quantity="10.00000000",
            price="10.0000",
            amount="100.0000",
            commission="1.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )

        FillService.delete(fill)

        account.refresh_from_db()
        position.refresh_from_db()

        assert position.quantity == position.quantity.__class__("0")
        assert position.status == Position.Status.CLOSED
        assert account.available_cash == account.available_cash.__class__("5000.0000")

    def test_instrument_price_service_update_triggers_position_and_account_resync(self) -> None:
        from trader.database import Account, FillService, Instrument, InstrumentPrice, InstrumentPriceService, Position

        account = Account.objects.create(
            account_code="ACC005A",
            account_name="价格联动账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="10000.0000",
            available_cash="10000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="600036",
            name="招商银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        FillService.create(
            account=account,
            instrument=instrument,
            fill_time=timezone.now(),
            side="买入",
            quantity="100.00000000",
            price="10.0000",
            amount="1000.0000",
            commission="0.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )
        price = InstrumentPriceService.create(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=timezone.now(),
            last_price="10.5000",
            source="test.spot",
        )

        account.refresh_from_db()
        position = Position.objects.get(account=account, instrument=instrument)

        assert position.market_value == position.market_value.__class__("1050.0000")
        assert position.unrealized_pnl == position.unrealized_pnl.__class__("50.0000")
        assert account.total_market_value == account.total_market_value.__class__("1050.0000")
        assert account.total_unrealized_pnl == account.total_unrealized_pnl.__class__("50.0000")
        assert account.total_equity == account.total_equity.__class__("10050.0000")

        InstrumentPriceService.update(
            price,
            last_price="11.0000",
        )

        account.refresh_from_db()
        position.refresh_from_db()

        assert position.market_value == position.market_value.__class__("1100.0000")
        assert position.unrealized_pnl == position.unrealized_pnl.__class__("100.0000")
        assert account.total_market_value == account.total_market_value.__class__("1100.0000")
        assert account.total_unrealized_pnl == account.total_unrealized_pnl.__class__("100.0000")
        assert account.total_equity == account.total_equity.__class__("10100.0000")

    def test_crud_service_writes_audit_logs_for_create_update_delete(self) -> None:
        from trader.database import Account, AuditLog
        from trader.database.services.crud import CrudService

        class AccountService(CrudService[Account]):
            model = Account

        account = AccountService.create(
            audit_actor="tester",
            audit_source="test.create",
            audit_remark="create account",
            account_code="ACC006",
            account_name="审计账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
        )
        AccountService.update(
            account,
            audit_actor="tester",
            audit_source="test.update",
            audit_remark="update account",
            account_name="审计账户-更新",
        )
        AccountService.delete(
            account,
            audit_actor="tester",
            audit_source="test.delete",
            audit_remark="delete account",
        )

        logs = list(AuditLog.objects.filter(table_name="accounts").order_by("id"))

        assert [log.operation for log in logs] == ["create", "update", "delete"]
        assert logs[0].after_data["account_name"] == "审计账户"
        assert logs[1].before_data["account_name"] == "审计账户"
        assert logs[1].after_data["account_name"] == "审计账户-更新"
        assert logs[2].before_data["account_name"] == "审计账户-更新"

    def test_audit_log_service_can_rollback_updated_record(self) -> None:
        from trader.database import Account, AuditLog, AuditLogService
        from trader.database.services.crud.base import CrudService

        class AccountService(CrudService[Account]):
            model = Account

        account = AccountService.create(
            account_code="ACC007",
            account_name="回滚账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
        )
        AccountService.update(
            account,
            account_name="回滚账户-修改后",
        )

        update_log = AuditLog.objects.filter(
            table_name="accounts",
            operation="update",
        ).latest("id")

        AuditLogService.rollback(update_log)
        account.refresh_from_db()

        assert account.account_name == "回滚账户"

    def test_audit_log_service_rollback_deleted_fill_resyncs_position_and_account(self) -> None:
        from trader.database import Account, AuditLog, AuditLogService, FillService, Instrument, Position

        account = Account.objects.create(
            account_code="ACC008",
            account_name="回滚成交账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="5000.0000",
            available_cash="5000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="601318",
            name="中国平安",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        fill = FillService.create(
            account=account,
            instrument=instrument,
            fill_time=timezone.now(),
            side="买入",
            quantity="10.00000000",
            price="10.0000",
            amount="100.0000",
            commission="1.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )

        position_id = fill.position_id
        FillService.delete(fill)

        delete_log = AuditLog.objects.filter(
            table_name="fills",
            operation="delete",
        ).latest("id")

        AuditLogService.rollback(delete_log)

        account.refresh_from_db()
        position = Position.objects.get(id=position_id)

        assert position.quantity == position.quantity.__class__("10.00000000")
        assert position.status == Position.Status.OPEN
        assert account.available_cash == account.available_cash.__class__("4899.0000")

    def test_audit_log_service_rollback_instrument_price_resyncs_position_and_account(self) -> None:
        from trader.database import Account, AuditLog, AuditLogService, FillService, Instrument, InstrumentPrice, InstrumentPriceService, Position

        account = Account.objects.create(
            account_code="ACC009",
            account_name="价格回滚账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            initial_balance="10000.0000",
            available_cash="10000.0000",
        )
        instrument = Instrument.objects.create(
            symbol="600276",
            name="恒瑞医药",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        FillService.create(
            account=account,
            instrument=instrument,
            fill_time=timezone.now(),
            side="买入",
            quantity="100.00000000",
            price="10.0000",
            amount="1000.0000",
            commission="0.0000",
            tax="0.0000",
            pricing_currency=Instrument.Currency.CNY,
        )
        price = InstrumentPriceService.create(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=timezone.now(),
            last_price="10.5000",
            source="test.spot",
        )
        InstrumentPriceService.update(price, last_price="11.0000")

        update_log = AuditLog.objects.filter(
            table_name="instrument_prices",
            operation="update",
        ).latest("id")

        AuditLogService.rollback(update_log)

        account.refresh_from_db()
        position = Position.objects.get(account=account, instrument=instrument)

        assert position.market_value == position.market_value.__class__("1050.0000")
        assert position.unrealized_pnl == position.unrealized_pnl.__class__("50.0000")
        assert account.total_market_value == account.total_market_value.__class__("1050.0000")
        assert account.total_unrealized_pnl == account.total_unrealized_pnl.__class__("50.0000")
        assert account.total_equity == account.total_equity.__class__("10050.0000")
