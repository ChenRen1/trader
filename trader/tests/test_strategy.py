"""策略模块测试。"""

from __future__ import annotations

from datetime import date
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase


class DividendUniverseTests(TestCase):
    def test_build_universe_dedup_by_symbol(self) -> None:
        from trader.strategy.services.universe import (
            DividendUniverseConfig,
            DividendUniverseService,
            IndexConstituent,
        )

        rows_15 = [
            IndexConstituent("000015", "上证红利", "600000", "浦发银行", datetime.now()),
            IndexConstituent("000015", "上证红利", "600036", "招商银行", datetime.now()),
        ]
        rows_922 = [
            IndexConstituent("000922", "中证红利", "600036", "招商银行", datetime.now()),
            IndexConstituent("000922", "中证红利", "601088", "中国神华", datetime.now()),
        ]

        with patch.object(DividendUniverseService, "fetch_index_constituents", side_effect=[rows_15, rows_922]):
            universe = DividendUniverseService.build_universe(
                DividendUniverseConfig(index_codes=("000015", "000922"))
            )

        symbols = [item.symbol for item in universe]
        assert symbols == ["600000", "600036", "601088"]


class HighDividendRegistryTests(TestCase):
    def test_sync_marks_and_clears_flags(self) -> None:
        from trader.database import Instrument
        from trader.strategy.services import HighDividendRegistryService, IndexConstituent

        Instrument.objects.create(
            symbol="600000",
            name="浦发银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
            is_high_dividend=True,
        )
        Instrument.objects.create(
            symbol="600036",
            name="招商银行",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.STOCK,
            trading_currency=Instrument.Currency.CNY,
            is_high_dividend=False,
        )

        pool = [
            IndexConstituent("000922", "中证红利", "600036", "招商银行", datetime.now()),
            IndexConstituent("000922", "中证红利", "601088", "中国神华", datetime.now()),
        ]
        with patch("trader.strategy.services.high_dividend_registry.DividendUniverseService.build_universe", return_value=pool):
            result = HighDividendRegistryService.sync_from_dividend_indices(create_missing=True)

        assert result.universe_size == 2
        assert result.created == 1
        assert result.marked >= 1
        assert result.cleared >= 1
        assert Instrument.objects.get(symbol="600036", market=Instrument.Market.CN).is_high_dividend is True
        assert Instrument.objects.get(symbol="601088", market=Instrument.Market.CN).is_high_dividend is True
        assert Instrument.objects.get(symbol="600000", market=Instrument.Market.CN).is_high_dividend is False


class DividendYieldStrategyTests(TestCase):
    def test_build_inputs_from_index_pool(self) -> None:
        from trader.strategy.services import DividendYieldStrategyService, IndexConstituent

        pool = [
            IndexConstituent("000922", "中证红利", "600036", "招商银行", datetime.now()),
            IndexConstituent("000922", "中证红利", "601088", "中国神华", datetime.now()),
        ]
        inputs = DividendYieldStrategyService.build_inputs_from_index_pool(
            pool=pool,
            dividend_yield_map={"600036": Decimal("0.055"), "601088": Decimal("0.062")},
            price_map={"600036": Decimal("39.2"), "601088": Decimal("45.83")},
        )
        assert len(inputs) == 2
        assert inputs[0].symbol == "600036"

    def test_create_rebalance_plan_buy_and_sell(self) -> None:
        from trader.strategy.services import (
            DividendStockInput,
            DividendYieldStrategyConfig,
            DividendYieldStrategyService,
        )

        universe = [
            DividendStockInput("600036", "招商银行", Decimal("0.055"), Decimal("39.20")),
            DividendStockInput("601088", "中国神华", Decimal("0.062"), Decimal("45.83")),
            DividendStockInput("600000", "浦发银行", Decimal("0.028"), Decimal("9.80")),
        ]
        current = {
            "600000": Decimal("0.2000"),
            "600036": Decimal("0.2000"),
        }
        config = DividendYieldStrategyConfig(
            buy_threshold=Decimal("0.05"),
            sell_threshold=Decimal("0.03"),
            max_positions=2,
            cash_buffer=Decimal("0.00"),
            min_rebalance_delta=Decimal("0.0001"),
        )

        plan = DividendYieldStrategyService.create_rebalance_plan(
            universe=universe,
            current_weights=current,
            config=config,
        )
        actions = {item.symbol: item.action for item in plan}
        assert actions["600000"] == "SELL"
        assert actions["601088"] == "BUY"


class DividendBacktestTests(TestCase):
    def test_backtest_runs(self) -> None:
        from trader.strategy.backtest import (
            DividendBacktestConfig,
            DividendObservation,
            DividendYieldBacktestService,
        )

        observations = [
            DividendObservation(trade_date=date(2026, 3, 3), symbol="A", close=Decimal("10"), dividend_yield=Decimal("0.06")),
            DividendObservation(trade_date=date(2026, 3, 3), symbol="B", close=Decimal("10"), dividend_yield=Decimal("0.02")),
            DividendObservation(trade_date=date(2026, 3, 4), symbol="A", close=Decimal("10.2"), dividend_yield=Decimal("0.06")),
            DividendObservation(trade_date=date(2026, 3, 4), symbol="B", close=Decimal("9.7"), dividend_yield=Decimal("0.02")),
        ]
        result = DividendYieldBacktestService.run(
            observations=observations,
            config=DividendBacktestConfig(),
        )
        assert result.total_days == 2
        assert len(result.net_value_series) == 2


class AnnualDividendYieldTests(TestCase):
    def test_pick_latest_annual_excludes_half_year(self) -> None:
        import pandas as pd
        from trader.strategy.services.dividend_data import AnnualReportDividendYieldService

        frame = pd.DataFrame(
            [
                {"报告时间": "2025半年报", "派息比例": 10.13, "除权日": "2026-01-16", "实施方案公告日期": "2026-01-10"},
                {"报告时间": "2024年报", "派息比例": 20.00, "除权日": "2025-07-11", "实施方案公告日期": "2025-07-01"},
            ]
        )

        class _Ak:
            @staticmethod
            def stock_dividend_cninfo(symbol: str):
                return frame

        with patch("trader.strategy.services.dividend_data._load_akshare", return_value=_Ak()):
            report, cash = AnnualReportDividendYieldService._pick_latest_annual_cash_dividend("600036")

        assert report == "2024年报"
        assert cash == Decimal("20")

    def test_compute_for_symbol_uses_annual_report_dividend(self) -> None:
        from trader.strategy.services.dividend_data import AnnualReportDividendYieldService

        with (
            patch.object(
                AnnualReportDividendYieldService,
                "_pick_latest_annual_cash_dividend",
                return_value=("2024年报", Decimal("20.0")),
            ),
            patch.object(
                AnnualReportDividendYieldService,
                "_fetch_spot_price_sina",
                return_value=Decimal("39.2"),
            ),
        ):
            result = AnnualReportDividendYieldService.compute_for_symbol(symbol="600036", name="招商银行")

        assert result.status == "ok"
        assert result.annual_report == "2024年报"
        assert result.cash_dividend_per_10 == Decimal("20.0")
        assert result.dividend_per_share == Decimal("2.0000")
        assert result.dividend_yield == Decimal("0.0510")


class StrategyRegistryTests(TestCase):
    def test_dividend_strategy_registered(self) -> None:
        from trader.strategy import get_strategy, list_strategies

        assert "dividend_yield" in list_strategies()
        engine = get_strategy("dividend_yield")
        assert engine.strategy_key == "dividend_yield"
