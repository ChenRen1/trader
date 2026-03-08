"""行情服务测试。"""

from __future__ import annotations

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
        from trader.database import Instrument, InstrumentPrice
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

        markdown = MarketDailyReportService.render_markdown_report(report_date=quoted_at)

        assert "每日市场分析报告" in markdown
        assert "沪深300/中证2000" in markdown
        assert "上证核心/创业板" in markdown
        assert "上证核心/恒科" in markdown
        assert 'style="font-size: 20px;' in markdown
        assert "| 名称 | 代码 | 市场 | 现价 | 涨跌幅 | 状态 |" in markdown
        assert "| 沪深300 | 000300 | CN |" in markdown
        assert "| 中证2000 | 932000 | CN |" in markdown
        assert "| 离岸人民币汇率 | USDCNH | FX |" in markdown

    def test_save_daily_snapshot_persists_snapshot_quotes_and_indicators(self) -> None:
        from trader.database import DailyMarketIndicator, DailyMarketQuote, DailyMarketSnapshot, Instrument, InstrumentPrice
        from trader.market.services import MarketDailyReportService

        quoted_at = timezone.now()

        def create_spot(symbol: str, name: str, market: str, exchange: str, last: str, prev: str) -> None:
            trading_currency = Instrument.Currency.CNY
            instrument_type = Instrument.InstrumentType.INDEX
            if market == Instrument.Market.HK:
                trading_currency = Instrument.Currency.HKD
            if market == Instrument.Market.MACRO and symbol == "USDCNH":
                trading_currency = Instrument.Currency.CNH
                instrument_type = Instrument.InstrumentType.FX
            instrument = Instrument.objects.create(
                symbol=symbol,
                name=name,
                market=market,
                exchange=exchange,
                instrument_type=instrument_type,
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

        snapshot = MarketDailyReportService.save_daily_snapshot(report_date=quoted_at)

        assert DailyMarketSnapshot.objects.filter(id=snapshot.id).exists()
        assert DailyMarketQuote.objects.filter(snapshot=snapshot).count() > 0
        assert DailyMarketIndicator.objects.filter(snapshot=snapshot).count() == 3
        indicator = DailyMarketIndicator.objects.get(
            snapshot=snapshot,
            indicator_key=DailyMarketIndicator.IndicatorKey.INDEX_300_VS_CSI_2000,
        )
        assert indicator.title == "沪深300/中证2000"
        assert indicator.left_key == "INDEX_300"
