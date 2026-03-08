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


class DashboardViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_home_dashboard_renders_account_and_position_summary(self) -> None:
        from django.utils import timezone

        from trader.database import Account, DailyMarketReport, Instrument, InstrumentPrice, Position

        account = Account.objects.create(
            account_code="ACC-DASH",
            account_name="总览账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            available_cash="10000",
            total_market_value="25000",
            total_unrealized_pnl="1200",
            total_equity="35000",
        )
        instrument = Instrument.objects.create(
            symbol="600000",
            name="浦发银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
        )
        Position.objects.create(
            account=account,
            instrument=instrument,
            side=Position.Side.LONG,
            quantity="200",
            available_quantity="200",
            average_price="10.50",
            cost_basis="2100",
            market_value="2400",
            unrealized_pnl="300",
            pricing_currency=Instrument.Currency.CNY,
            status=Position.Status.OPEN,
        )
        second_account = Account.objects.create(
            account_code="ACC-DASH-2",
            account_name="第二账户",
            account_type=Account.AccountType.CASH,
            base_currency=Account.Currency.CNY,
            available_cash="8000",
            total_market_value="12000",
            total_unrealized_pnl="500",
            total_equity="20000",
        )
        Position.objects.create(
            account=second_account,
            instrument=instrument,
            side=Position.Side.LONG,
            quantity="100",
            available_quantity="100",
            average_price="11.20",
            cost_basis="1120",
            market_value="1260",
            unrealized_pnl="140",
            pricing_currency=Instrument.Currency.CNY,
            status=Position.Status.OPEN,
        )
        macro = Instrument.objects.create(
            symbol="USDCNH",
            name="离岸人民币汇率",
            market=Instrument.Market.MACRO,
            exchange=Instrument.Exchange.OTC,
            instrument_type=Instrument.InstrumentType.FX,
            trading_currency=Instrument.Currency.CNH,
        )
        InstrumentPrice.objects.create(
            instrument=macro,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=timezone.now(),
            last_price="6.9000",
            prev_close="6.8800",
            source="test.seed",
        )
        DailyMarketReport.objects.create(
            report_date=timezone.localdate(),
            reported_at=timezone.now(),
            hs300_sector_summary="食品饮料：样本 12 / 12",
            markdown_content=(
                "## 核心结论\n"
                "<p>• 沪深300/中证2000: 涨跌幅分别为 +0.27% / +1.34%，差值 1.07% -> 较重分歧。</p>\n"
                "<p>• 上证核心/创业板: 涨跌幅 +0.14% / +0.38% -> 共振（单边行情更强）。</p>\n"
                "<p>• 上证核心/恒科: 涨跌幅 +0.14% / +3.15%，相对差 -3.01%（同向）。</p>\n"
                "\n"
                "## 证券板块涨跌幅分布（1% / 3% / 5%）\n"
                "- 板块：881157 证券，样本 49 / 50，均值 1.44%，中位数 1.27%\n"
                "- 上涨：>=5% 0，[3%,5%) 2，[1%,3%) 30，(0,1%) 17\n"
                "- 下跌：<=-5% 0，[-5%,-3%) 0，[-3%,-1%) 0，(-1%,0) 0\n"
                "- 平盘：0\n"
                "\n"
                "## 沪深300成分股行业涨跌幅统计\n"
                "- 样本范围：沪深300成分股，按行业汇总，展示前 10 个行业（按平均涨跌幅排序）\n"
                "- 食品饮料：样本 12 / 12，上涨 12，下跌 0，平盘 0，均值 1.76%，中位数 1.92%\n"
                "\n"
                "## 股指期货基差（期货-现货）\n"
                "- 计算时间：2026-03-08 15:52:48\n"
                "- IF/沪深300: 期货 4602.54，现货 4660.44，基差 -57.90 (-1.24%)，口径 open_interest_weighted\n"
            ),
        )

        response = self.client.get("/")
        content = response.content.decode("utf-8")

        assert response.status_code == 200
        assert "资金与持仓总览" in content
        assert "ACC-DASH" in content
        assert "浦发银行" in content
        assert "食品饮料" in content
        assert "样本 12 / 12" in content
        assert "核心结论" in content
        assert "股指期货基差" in content
        assert "离岸人民币汇率" in content
        assert "账户数 2" in content
        assert "标的数 1 / 持仓数 2" in content
        assert "仓位占比" in content

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
