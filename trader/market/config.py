"""行情标的配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketInstrument:
    """统一标的配置结构。"""

    key: str
    name: str
    symbol: str
    market: str


INDEX_50 = MarketInstrument("INDEX_50", "上证50", "000016", "CN")
INDEX_300 = MarketInstrument("INDEX_300", "沪深300", "000300", "CN")
INDEX_1000 = MarketInstrument("INDEX_1000", "中证1000", "000852", "CN")
CHINEXT = MarketInstrument("CHINEXT", "创业板指", "399006", "CN")
STAR_50 = MarketInstrument("STAR_50", "科创50", "000688", "CN")
HSTECH = MarketInstrument("HSTECH", "恒生科技指数", "HSTECH", "HK")
BSE_50 = MarketInstrument("BSE_50", "北证50", "899050", "CN")
CSI_2000 = MarketInstrument("CSI_2000", "中证2000", "932000", "CN")

USDCNH = MarketInstrument("USDCNH", "离岸人民币汇率", "USDCNH", "FX")
HKDCNH = MarketInstrument("HKDCNH", "港币兑人民币", "HKDCNH", "FX")
CN10Y = MarketInstrument("CN10Y", "中国国债十年期", "CN10Y", "BOND")
SECURITIES_881157 = MarketInstrument("SECURITIES_881157", "证券881157", "881157", "CN")

INDEX_WATCHLIST: tuple[MarketInstrument, ...] = (
    INDEX_50,
    INDEX_300,
    INDEX_1000,
    CHINEXT,
    STAR_50,
    HSTECH,
    BSE_50,
    CSI_2000,
    USDCNH,
    HKDCNH,
    CN10Y,
    SECURITIES_881157,
)
