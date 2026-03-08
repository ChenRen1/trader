"""Web 层测试。"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase


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


class MarketChartViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_market_chart_page_renders(self) -> None:
        response = self.client.get("/market/chart/CN/600000/")

        assert response.status_code == 200
        assert "600000 行情图" in response.content.decode("utf-8")

    def test_market_chart_data_returns_json(self) -> None:
        with (
            patch("trader.web.views.get_kline") as mocked_kline,
            patch("trader.web.views.get_spot_price") as mocked_spot,
        ):
            mocked_kline.return_value = [
                {
                    "date": "2026-03-06",
                    "open": Decimal("10.10"),
                    "high": Decimal("10.80"),
                    "low": Decimal("10.00"),
                    "close": Decimal("10.50"),
                    "volume": Decimal("120000"),
                }
            ]
            mocked_spot.return_value = {
                "last_price": Decimal("10.50"),
                "prev_close": Decimal("10.20"),
                "change_pct": Decimal("2.94"),
                "source": "test.source",
            }

            response = self.client.get("/market/chart-data/CN/600000/")

        assert response.status_code == 200
        payload = response.json()
        assert payload["symbol"] == "600000"
        assert payload["market"] == "CN"
        assert payload["spot"]["last_price"] == 10.5
        assert payload["bars"][0]["close"] == 10.5
        assert payload["basis"] is None

    def test_market_chart_data_includes_basis_for_index(self) -> None:
        with (
            patch("trader.web.views.get_kline") as mocked_kline,
            patch("trader.web.views.get_spot_price") as mocked_spot,
            patch("trader.web.views.IndexBasisService.calculate_for_spot_symbol") as mocked_basis,
        ):
            mocked_kline.return_value = [
                {
                    "date": "2026-03-06",
                    "open": Decimal("4650"),
                    "high": Decimal("4670"),
                    "low": Decimal("4630"),
                    "close": Decimal("4660"),
                    "volume": Decimal("120000"),
                }
            ]
            mocked_spot.return_value = {
                "last_price": Decimal("4660.4390"),
                "prev_close": Decimal("4651.2000"),
                "change_pct": Decimal("0.20"),
                "source": "test.source",
            }
            mocked_basis.return_value = SimpleNamespace(
                future_code="IF",
                future_close=Decimal("4602.54"),
                spot_price=Decimal("4660.4390"),
                basis=Decimal("-57.90"),
                basis_pct=Decimal("-1.24"),
                trade_date="2026-03-06",
                future_source="open_interest_weighted",
                status="ok",
                error="",
            )

            response = self.client.get("/market/chart-data/CN/000300/")

        assert response.status_code == 200
        payload = response.json()
        assert payload["basis"]["future_code"] == "IF"
        assert payload["basis"]["basis"] == -57.9
        assert payload["basis"]["basis_pct"] == -1.24
        assert payload["basis"]["status"] == "ok"
