"""写入可重复执行的演示测试数据。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from trader.database import (
    Account,
    AccountService,
    Fill,
    FillService,
    Instrument,
    InstrumentPrice,
    InstrumentPriceService,
    InstrumentService,
)

DEMO_TAG = "DEMO"


class Command(BaseCommand):
    """初始化一批账户、标的、价格和成交测试数据。"""

    help = "写入演示测试数据，并触发持仓/账户联动。"

    @transaction.atomic
    def handle(self, *args, **options):
        self._clear_existing_demo_data()

        now = timezone.now()

        cash_account = AccountService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed cash account",
            account_code="DEMO-CN-001",
            account_name="演示普通账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            broker_name="测试券商A",
            initial_balance=Decimal("200000.0000"),
            available_cash=Decimal("200000.0000"),
            notes=DEMO_TAG,
        )
        hk_account = AccountService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed hk account",
            account_code="DEMO-HK-001",
            account_name="演示港股账户",
            account_type=Account.AccountType.MARGIN,
            base_currency=Account.Currency.HKD,
            broker_name="测试券商B",
            initial_balance=Decimal("50000.0000"),
            available_cash=Decimal("50000.0000"),
            notes=DEMO_TAG,
        )

        cmb = InstrumentService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed instrument",
            symbol="600036",
            name="招商银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
            tick_size=Decimal("0.0100"),
            data_source="demo.seed",
            notes=DEMO_TAG,
        )
        maotai = InstrumentService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed instrument",
            symbol="600519",
            name="贵州茅台",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
            tick_size=Decimal("0.0100"),
            data_source="demo.seed",
            notes=DEMO_TAG,
        )
        tencent = InstrumentService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed instrument",
            symbol="00700",
            name="腾讯控股",
            market=Instrument.Market.HK,
            exchange=Instrument.Exchange.HKEX,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.HKD,
            tick_size=Decimal("0.1000"),
            data_source="demo.seed",
            notes=DEMO_TAG,
        )

        InstrumentPriceService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed spot",
            instrument=cmb,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=now - timedelta(minutes=5),
            last_price=Decimal("43.2000"),
            prev_close=Decimal("42.8500"),
            source="demo.seed",
        )
        InstrumentPriceService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed spot",
            instrument=maotai,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=now - timedelta(minutes=4),
            last_price=Decimal("1688.0000"),
            prev_close=Decimal("1679.5000"),
            source="demo.seed",
        )
        InstrumentPriceService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed spot",
            instrument=tencent,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=now - timedelta(minutes=3),
            last_price=Decimal("486.2000"),
            prev_close=Decimal("480.0000"),
            source="demo.seed",
        )

        FillService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed fill",
            account=cash_account,
            instrument=cmb,
            fill_time=now - timedelta(days=2),
            side=Fill.Side.BUY,
            quantity=Decimal("200.00000000"),
            price=Decimal("42.0000"),
            amount=Decimal("8400.0000"),
            commission=Decimal("5.0000"),
            tax=Decimal("0.0000"),
            pricing_currency=Instrument.Currency.CNY,
            external_id="DEMO-FILL-001",
            notes=DEMO_TAG,
        )
        FillService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed fill",
            account=cash_account,
            instrument=maotai,
            fill_time=now - timedelta(days=1, hours=2),
            side=Fill.Side.BUY,
            quantity=Decimal("10.00000000"),
            price=Decimal("1650.0000"),
            amount=Decimal("16500.0000"),
            commission=Decimal("10.0000"),
            tax=Decimal("0.0000"),
            pricing_currency=Instrument.Currency.CNY,
            external_id="DEMO-FILL-002",
            notes=DEMO_TAG,
        )
        FillService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed fill",
            account=cash_account,
            instrument=maotai,
            fill_time=now - timedelta(hours=12),
            side=Fill.Side.SELL,
            quantity=Decimal("3.00000000"),
            price=Decimal("1690.0000"),
            amount=Decimal("5070.0000"),
            commission=Decimal("8.0000"),
            tax=Decimal("5.0700"),
            pricing_currency=Instrument.Currency.CNY,
            external_id="DEMO-FILL-003",
            notes=DEMO_TAG,
        )
        FillService.create(
            audit_actor="system",
            audit_source="seed.demo",
            audit_remark="seed fill",
            account=hk_account,
            instrument=tencent,
            fill_time=now - timedelta(days=1),
            side=Fill.Side.BUY,
            quantity=Decimal("100.00000000"),
            price=Decimal("478.0000"),
            amount=Decimal("47800.0000"),
            commission=Decimal("30.0000"),
            tax=Decimal("0.0000"),
            pricing_currency=Instrument.Currency.HKD,
            external_id="DEMO-FILL-004",
            notes=DEMO_TAG,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "演示数据写入完成：accounts=2, instruments=3, prices=3, fills=4"
            )
        )

    def _clear_existing_demo_data(self) -> None:
        demo_accounts = list(Account.objects.filter(notes=DEMO_TAG).values_list("id", flat=True))
        demo_instruments = list(Instrument.objects.filter(notes=DEMO_TAG).values_list("id", flat=True))

        Fill.objects.filter(external_id__startswith="DEMO-FILL-").delete()
        if demo_instruments:
            InstrumentPrice.objects.filter(instrument_id__in=demo_instruments).delete()
        if demo_accounts:
            Account.objects.filter(id__in=demo_accounts).delete()
        if demo_instruments:
            Instrument.objects.filter(id__in=demo_instruments).delete()
