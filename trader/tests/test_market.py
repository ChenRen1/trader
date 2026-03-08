"""行情服务测试。"""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone


class MarketQuoteSyncServiceTests(TestCase):
    def test_sync_config_spot_prices_calls_database_service(self) -> None:
        from trader.database import Instrument
        from trader.market.config import INDEX_WATCHLIST
        from trader.market.services import MarketQuoteSyncService

        Instrument.objects.create(
            symbol="000300",
            name="沪深300",
            market=Instrument.Market.CN,
            exchange=Instrument.Exchange.SSE,
            instrument_type=Instrument.InstrumentType.INDEX,
            trading_currency=Instrument.Currency.CNY,
        )
        Instrument.objects.create(
            symbol="HSTECH",
            name="恒生科技指数",
            market=Instrument.Market.HK,
            exchange=Instrument.Exchange.HKEX,
            instrument_type=Instrument.InstrumentType.INDEX,
            trading_currency=Instrument.Currency.HKD,
        )
        Instrument.objects.create(
            symbol="USDCNH",
            name="离岸人民币汇率",
            market=Instrument.Market.MACRO,
            exchange=Instrument.Exchange.OTC,
            instrument_type=Instrument.InstrumentType.FX,
            trading_currency=Instrument.Currency.CNH,
        )

        with patch(
            "trader.market.services.quote_sync.PriceSyncService.update_spot_prices",
            return_value={"updated": 3, "failed": 0, "errors": []},
        ) as mocked_update:
            result = MarketQuoteSyncService.sync_config_spot_prices()

        mocked_update.assert_called_once()
        called_instruments = mocked_update.call_args.kwargs["instruments"]
        symbols = sorted(f"{item.symbol}.{item.market}" for item in called_instruments)
        assert symbols == ["000300.CN", "HSTECH.HK", "USDCNH.MACRO"]
        assert result["total"] == len(INDEX_WATCHLIST)
        assert result["matched"] == 3
        assert len(result["missing"]) == len(INDEX_WATCHLIST) - 3
        assert result["sync"]["updated"] == 3


class MarketDailyReportServiceTests(TestCase):
    def test_render_markdown_report_contains_analysis_and_table(self) -> None:
        from trader.database import DailyMarketReport, Instrument, InstrumentPrice
        from trader.market.services import MarketDailyReportService

        quoted_at = timezone.now()

        def create_spot(symbol: str, name: str, market: str, exchange: str, last: str, prev: str) -> None:
            trading_currency = Instrument.Currency.CNY
            if market == Instrument.Market.HK:
                trading_currency = Instrument.Currency.HKD
            if market == Instrument.Market.MACRO and symbol == "USDCNH":
                trading_currency = Instrument.Currency.CNH
            instrument = Instrument.objects.create(
                symbol=symbol,
                name=name,
                market=market,
                exchange=exchange,
                instrument_type=Instrument.InstrumentType.INDEX,
                trading_currency=trading_currency,
            )
            InstrumentPrice.objects.create(
                instrument=instrument,
                bar_type=InstrumentPrice.BarType.SPOT,
                priced_at=quoted_at,
                last_price=last,
                prev_close=prev,
                source="test.seed",
            )

        create_spot("000016", "上证50", Instrument.Market.CN, Instrument.Exchange.SSE, "2500.00", "2480.00")
        create_spot("000300", "沪深300", Instrument.Market.CN, Instrument.Exchange.SSE, "3900.00", "3880.00")
        create_spot("932000", "中证2000", Instrument.Market.CN, Instrument.Exchange.SSE, "2100.00", "2080.00")
        create_spot("399006", "创业板指", Instrument.Market.CN, Instrument.Exchange.SZSE, "1800.00", "1790.00")
        create_spot("HSTECH", "恒生科技指数", Instrument.Market.HK, Instrument.Exchange.HKEX, "3500.00", "3550.00")
        create_spot("USDCNH", "离岸人民币汇率", Instrument.Market.MACRO, Instrument.Exchange.OTC, "7.2200", "7.2100")

        with patch(
            "trader.market.services.daily_report.SectorAnalyticsService.summarize_sector_change_stats",
            return_value={
                "sector_code": "881157",
                "sector_name": "证券",
                "total_constituents": 50,
                "valid_change_count": 49,
                "up_count": 49,
                "down_count": 0,
                "flat_count": 0,
                "mean_change_pct": Decimal("1.44"),
                "median_change_pct": Decimal("1.27"),
                "distribution": {
                    "up_ge_5": 0,
                    "up_3_to_5": 2,
                    "up_1_to_3": 30,
                    "up_0_to_1": 17,
                    "flat": 0,
                    "down_0_to_1": 0,
                    "down_1_to_3": 0,
                    "down_3_to_5": 0,
                    "down_ge_5": 0,
                },
            },
        ), patch(
            "trader.market.services.daily_report.SectorAnalyticsService.summarize_hs300_sector_change_stats",
            return_value=[
                {
                    "sector_name": "电子",
                    "constituent_count": 12,
                    "valid_change_count": 12,
                    "up_count": 10,
                    "down_count": 2,
                    "flat_count": 0,
                    "mean_change_pct": Decimal("2.31"),
                    "median_change_pct": Decimal("2.05"),
                },
                {
                    "sector_name": "银行",
                    "constituent_count": 8,
                    "valid_change_count": 8,
                    "up_count": 6,
                    "down_count": 2,
                    "flat_count": 0,
                    "mean_change_pct": Decimal("0.88"),
                    "median_change_pct": Decimal("0.74"),
                },
            ],
        ), patch(
            "trader.market.services.daily_report.IndexBasisService.calculate_snapshot",
            return_value=SimpleNamespace(
                calculated_at=quoted_at,
                rows=[
                    SimpleNamespace(
                        future_code="IF",
                        name="沪深300",
                        status="ok",
                        error="",
                        basis=Decimal("-57.90"),
                        basis_pct=Decimal("-1.24"),
                        future_close=Decimal("4602.54"),
                        spot_price=Decimal("4660.44"),
                        future_source="open_interest_weighted",
                    ),
                    SimpleNamespace(
                        future_code="IH",
                        name="上证50",
                        status="ok",
                        error="",
                        basis=Decimal("-14.47"),
                        basis_pct=Decimal("-0.48"),
                        future_close=Decimal("2978.23"),
                        spot_price=Decimal("2992.70"),
                        future_source="open_interest_weighted",
                    ),
                ],
            ),
        ):
            markdown = MarketDailyReportService.render_markdown_report(report_date=quoted_at)

        assert "每日市场分析报告" in markdown
        assert "沪深300/中证2000" in markdown
        assert "上证核心/创业板" in markdown
        assert "上证核心/恒科" in markdown
        assert "证券板块涨跌幅分布（1% / 3% / 5%）" in markdown
        assert "沪深300成分股行业涨跌幅统计" in markdown
        assert "股指期货基差（期货-现货）" in markdown
        assert "板块：881157 证券" in markdown
        assert "电子：样本 12 / 12，上涨 10，下跌 2，平盘 0，均值 2.31%，中位数 2.05%" in markdown
        assert "IF/沪深300: 期货 4602.54，现货 4660.44，基差 -57.90 (-1.24%)，口径 open_interest_weighted" in markdown
        assert "上涨：>=5% 0，[3%,5%) 2，[1%,3%) 30，(0,1%) 17" in markdown
        assert 'style="font-size: 20px;' in markdown
        assert "| 名称 | 代码 | 市场 | 现价 | 涨跌幅 | 状态 |" in markdown
        assert "| 沪深300 | 000300 | CN |" in markdown
        assert "| 中证2000 | 932000 | CN |" in markdown
        assert "| 离岸人民币汇率 | USDCNH | FX |" in markdown

        report = MarketDailyReportService.save_daily_report(
            report_date=quoted_at,
            markdown_content=markdown,
            hs300_sector_summary="电子：样本 12 / 12",
        )
        saved = DailyMarketReport.objects.get(id=report.id)
        assert saved.report_date == quoted_at.date()
        assert "每日市场分析报告" in saved.markdown_content
        assert "电子：样本 12 / 12" in saved.hs300_sector_summary


class SectorAnalyticsServiceTests(TestCase):
    def test_summarize_sector_change_stats(self) -> None:
        from trader.market.services.sector_analytics import SectorAnalyticsService, SectorConstituent

        rows = [
            SectorConstituent("600000", "A", Decimal("10"), Decimal("5.20")),
            SectorConstituent("600001", "B", Decimal("10"), Decimal("3.10")),
            SectorConstituent("600002", "C", Decimal("10"), Decimal("1.20")),
            SectorConstituent("600003", "D", Decimal("10"), Decimal("0.30")),
            SectorConstituent("600004", "E", Decimal("10"), Decimal("0.00")),
            SectorConstituent("600005", "F", Decimal("10"), Decimal("-0.50")),
            SectorConstituent("600006", "G", Decimal("10"), Decimal("-1.20")),
            SectorConstituent("600007", "H", Decimal("10"), Decimal("-3.20")),
            SectorConstituent("600008", "I", Decimal("10"), Decimal("-5.60")),
        ]
        with patch.object(SectorAnalyticsService, "fetch_sector_constituents", return_value=rows):
            result = SectorAnalyticsService.summarize_sector_change_stats(sector_code="881157")

        assert result["sector_code"] == "881157"
        assert result["total_constituents"] == 9
        assert result["up_count"] == 4
        assert result["down_count"] == 4
        assert result["flat_count"] == 1
        assert result["mean_change_pct"] == Decimal("-0.08")
        assert result["median_change_pct"] == Decimal("0.00")
        assert result["distribution"] == {
            "up_ge_5": 1,
            "up_3_to_5": 1,
            "up_1_to_3": 1,
            "up_0_to_1": 1,
            "flat": 1,
            "down_0_to_1": 1,
            "down_1_to_3": 1,
            "down_3_to_5": 1,
            "down_ge_5": 1,
        }

    def test_summarize_hs300_sector_change_stats(self) -> None:
        from trader.market.services.sector_analytics import (
            Hs300ConstituentQuote,
            SectorAnalyticsService,
        )

        rows = [
            Hs300ConstituentQuote("600000", "A", "银行", Decimal("10"), Decimal("2.50")),
            Hs300ConstituentQuote("600001", "B", "银行", Decimal("11"), Decimal("-0.50")),
            Hs300ConstituentQuote("600002", "C", "电子", Decimal("12"), Decimal("5.00")),
            Hs300ConstituentQuote("600003", "D", "电子", Decimal("13"), Decimal("1.00")),
            Hs300ConstituentQuote("600004", "E", "电子", Decimal("14"), None),
        ]

        with patch.object(SectorAnalyticsService, "fetch_hs300_sector_quotes", return_value=rows):
            result = SectorAnalyticsService.summarize_hs300_sector_change_stats()

        assert len(result) == 2
        assert result[0] == {
            "sector_name": "电子",
            "constituent_count": 3,
            "valid_change_count": 2,
            "up_count": 2,
            "down_count": 0,
            "flat_count": 0,
            "mean_change_pct": Decimal("3.00"),
            "median_change_pct": Decimal("3.00"),
        }
        assert result[1] == {
            "sector_name": "银行",
            "constituent_count": 2,
            "valid_change_count": 2,
            "up_count": 1,
            "down_count": 1,
            "flat_count": 0,
            "mean_change_pct": Decimal("1.00"),
            "median_change_pct": Decimal("1.00"),
        }

    def test_resolve_latest_industry_name_uses_cache(self) -> None:
        from trader.market.services.sector_analytics import SectorAnalyticsService

        cache = {
            "600000": ("银行", datetime.now() - timedelta(days=1)),
        }

        with patch.object(
            SectorAnalyticsService,
            "_load_latest_sw_industry_by_symbol",
            side_effect=AssertionError("should not call uncached lookup"),
        ):
            result = SectorAnalyticsService.resolve_latest_industry_name("600000", cache=cache)

        assert result == "银行"
