"""YFinance 数据源实现。"""

from __future__ import annotations

import importlib
from datetime import datetime
from decimal import Decimal
from typing import Any


def _load_yfinance() -> Any:
    try:
        return importlib.import_module("yfinance")
    except ModuleNotFoundError as exc:
        raise RuntimeError("yfinance 未安装，无法获取行情。") from exc


def _to_decimal(value: object, *, scale: str | None = None) -> Decimal | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    decimal_value = Decimal(text)
    if scale is not None:
        return decimal_value.quantize(Decimal(scale))
    return decimal_value


def _normalize_hk_symbol(symbol: str) -> str:
    raw = symbol.strip().upper()
    digits = "".join(char for char in raw if char.isdigit())
    if digits:
        normalized = digits.lstrip("0")
        if not normalized:
            normalized = "0"
        return normalized.zfill(4)
    return raw


class YfinanceSource:
    """YFinance 数据源，主要用于港股兜底。"""

    def get_spot_price(self, symbol: str, market: str) -> dict[str, Any]:
        market_key = market.strip().upper()
        if market_key in {"FX", "MACRO"}:
            yf = _load_yfinance()
            normalized = symbol.strip().upper()
            alias_map = {
                "HKDCNH": "HKDCNY",
            }
            normalized = alias_map.get(normalized, normalized)
            supported_fx = {"USDCNH", "HKDCNY"}
            if market_key == "MACRO" and normalized not in supported_fx:
                raise ValueError(f"unsupported macro symbol for yfinance: {symbol}")
            yahoo_symbol = f"{normalized}=X" if "=" not in normalized else normalized
            ticker = yf.Ticker(yahoo_symbol)
            info = ticker.fast_info

            last_price = _to_decimal(info.get("lastPrice"), scale="0.0001")
            prev_close = _to_decimal(info.get("previousClose"), scale="0.0001")
            change_pct = None
            if last_price is not None and prev_close not in {None, Decimal("0")}:
                change_pct = ((last_price - prev_close) / prev_close) * Decimal("100")

            return {
                "symbol": normalized,
                "market": market_key,
                "name": "",
                "last_price": last_price,
                "prev_close": prev_close,
                "change_pct": change_pct,
                "quoted_at": datetime.now(),
                "source": "yfinance.fast_info",
            }

        if market_key != "HK":
            raise ValueError(f"unsupported market for yfinance: {market}")

        yf = _load_yfinance()
        normalized = _normalize_hk_symbol(symbol)
        yahoo_symbol = normalized if "." in normalized else f"{normalized}.HK"
        ticker = yf.Ticker(yahoo_symbol)
        info = ticker.fast_info

        last_price = _to_decimal(info.get("lastPrice"), scale="0.0001")
        prev_close = _to_decimal(info.get("previousClose"), scale="0.0001")
        change_pct = None
        if last_price is not None and prev_close not in {None, Decimal("0")}:
            change_pct = ((last_price - prev_close) / prev_close) * Decimal("100")

        return {
            "symbol": _normalize_hk_symbol(symbol),
            "market": "HK",
            "name": "",
            "last_price": last_price,
            "prev_close": prev_close,
            "change_pct": change_pct,
            "quoted_at": datetime.now(),
            "source": "yfinance.fast_info",
        }

    def get_kline(
        self,
        symbol: str,
        market: str,
        *,
        limit: int = 120,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        del start_date, end_date
        market_key = market.strip().upper()
        if market_key != "HK":
            raise ValueError(f"unsupported market for yfinance: {market}")

        yf = _load_yfinance()
        normalized = _normalize_hk_symbol(symbol)
        yahoo_symbol = normalized if "." in normalized else f"{normalized}.HK"
        ticker = yf.Ticker(yahoo_symbol)
        frame = ticker.history(period=f"{max(limit * 3, 60)}d", interval="1d")
        rows: list[dict[str, Any]] = []
        for index, row in frame.tail(limit).iterrows():
            rows.append(
                {
                    "date": index.date().isoformat() if hasattr(index, "date") else str(index),
                    "open": _to_decimal(row.get("Open"), scale="0.0001"),
                    "high": _to_decimal(row.get("High"), scale="0.0001"),
                    "low": _to_decimal(row.get("Low"), scale="0.0001"),
                    "close": _to_decimal(row.get("Close"), scale="0.0001"),
                    "volume": _to_decimal(row.get("Volume")),
                    "source": "yfinance.history",
                }
            )
        return rows
