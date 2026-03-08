"""Web 层测试。"""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase


class ServiceBackedAdminTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password",
        )

    def test_account_admin_save_uses_service(self) -> None:
        from trader.database import Account
        from trader.web.admin import AccountAdmin

        request = self.factory.post("/admin/trader/account/add/")
        request.user = self.user
        account = Account(
            account_code="ACC100",
            account_name="管理后台账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
        )

        called: dict[str, object] = {}

        class _Service:
            @staticmethod
            def create(**payload):
                called.update(payload)
                return Account.objects.create(
                    account_code=payload["account_code"],
                    account_name=payload["account_name"],
                    account_type=payload["account_type"],
                    base_currency=payload["base_currency"],
                )

        model_admin = AccountAdmin(Account, admin.site)
        model_admin.service = _Service

        model_admin.save_model(request, account, form=None, change=False)

        assert called["audit_actor"] == "admin"
        assert called["audit_source"] == "admin:account"
        assert account.pk is not None

    def test_account_admin_delete_uses_service(self) -> None:
        from trader.database import Account
        from trader.web.admin import AccountAdmin

        request = self.factory.post("/admin/trader/account/1/delete/")
        request.user = self.user
        account = Account.objects.create(
            account_code="ACC101",
            account_name="待删除账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
        )

        called: dict[str, object] = {}

        class _Service:
            @staticmethod
            def delete(instance, **payload):
                called["instance_id"] = instance.id
                called.update(payload)

        model_admin = AccountAdmin(Account, admin.site)
        model_admin.service = _Service

        model_admin.delete_model(request, account)

        assert called["instance_id"] == account.id
        assert called["audit_actor"] == "admin"
        assert called["audit_source"] == "admin:account"

    def test_instrument_price_admin_save_uses_service(self) -> None:
        from trader.database import Instrument, InstrumentPrice
        from trader.web.admin import InstrumentPriceAdmin

        request = self.factory.post("/admin/trader/instrumentprice/add/")
        request.user = self.user
        instrument = Instrument.objects.create(
            symbol="600010",
            name="包钢股份",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        price = InstrumentPrice(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at="2026-03-08T10:00:00+08:00",
            last_price="2.5000",
            source="admin.test",
        )

        called: dict[str, object] = {}

        class _Service:
            @staticmethod
            def create(**payload):
                called.update(payload)
                return InstrumentPrice.objects.create(
                    instrument=payload["instrument"],
                    bar_type=payload["bar_type"],
                    priced_at=payload["priced_at"],
                    last_price=payload["last_price"],
                    source=payload["source"],
                )

        model_admin = InstrumentPriceAdmin(InstrumentPrice, admin.site)
        model_admin.service = _Service

        model_admin.save_model(request, price, form=None, change=False)

        assert called["audit_actor"] == "admin"
        assert called["audit_source"] == "admin:instrumentprice"
        assert price.pk is not None
