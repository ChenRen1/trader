"""AkShare 数据源实现。"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any


@contextmanager
def _no_proxy_environment() -> Any:
    keys = (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "all_proxy",
    )
    old_env = {key: os.environ.get(key) for key in keys}
    try:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        yield
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _load_akshare() -> Any:
    try:
        return importlib.import_module("akshare")
    except ModuleNotFoundError as exc:
        raise RuntimeError("akshare 未安装，无法获取行情。") from exc


def _to_decimal(value: object) -> Decimal | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return Decimal(text)


def _normalize_cn_symbol(symbol: str) -> str:
    cleaned = "".join(char for char in symbol.strip().upper() if char.isalnum())
    if cleaned.startswith(("SH", "SZ", "BJ")) and cleaned[2:].isdigit():
        return cleaned[2:].zfill(6)
    digits = "".join(char for char in cleaned if char.isdigit())
    if not digits:
        return cleaned
    return digits.zfill(6)


def _cn_prefixed_candidates(symbol: str) -> list[str]:
    normalized = _normalize_cn_symbol(symbol)
    candidates = [f"sh{normalized}", f"sz{normalized}", f"bj{normalized}"]
    if normalized.startswith(("4", "8")):
        return [f"bj{normalized}", f"sh{normalized}", f"sz{normalized}"]
    if normalized.startswith(("0", "3")):
        return [f"sz{normalized}", f"sh{normalized}", f"bj{normalized}"]
    return candidates


def _normalize_hk_symbol(symbol: str) -> str:
    digits = "".join(char for char in symbol.strip().upper() if char.isdigit())
    return digits.zfill(5)


def _build_rows(frame: Any, *, source: str, limit: int) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    cols = {str(column).strip().lower(): column for column in frame.columns}
    date_col = cols.get("date") or cols.get("日期")
    open_col = cols.get("open") or cols.get("开盘")
    high_col = cols.get("high") or cols.get("最高")
    low_col = cols.get("low") or cols.get("最低")
    close_col = cols.get("close") or cols.get("收盘")
    volume_col = cols.get("volume") or cols.get("成交量")
    if not all([date_col, open_col, high_col, low_col, close_col]):
        return []
    rows: list[dict[str, Any]] = []
    for _, row in frame.tail(limit).iterrows():
        rows.append(
            {
                "date": str(row.get(date_col)),
                "open": _to_decimal(row.get(open_col)),
                "high": _to_decimal(row.get(high_col)),
                "low": _to_decimal(row.get(low_col)),
                "close": _to_decimal(row.get(close_col)),
                "volume": _to_decimal(row.get(volume_col)) if volume_col else None,
                "source": source,
            }
        )
    return rows


class AkshareSource:
    """AkShare 数据源，支持 CN/HK。"""

    def get_spot_price(self, symbol: str, market: str) -> dict[str, Any]:
        market_key = market.strip().upper()
        ak = _load_akshare()

        if market_key == "CN":
            prefixed_candidates = _cn_prefixed_candidates(symbol)
            try:
                with _no_proxy_environment():
                    index_df = ak.stock_zh_index_spot_sina()
                target = index_df[index_df["代码"].isin(prefixed_candidates)]
                if not target.empty:
                    target = target.copy()
                    target["rank"] = target["代码"].apply(
                        lambda code: prefixed_candidates.index(str(code))
                        if str(code) in prefixed_candidates
                        else 999
                    )
                    target = target.sort_values("rank")
                    row = target.iloc[0]
                    return {
                        "symbol": symbol,
                        "market": "CN",
                        "name": str(row.get("名称", "")),
                        "last_price": _to_decimal(row.get("最新价")),
                        "prev_close": _to_decimal(row.get("昨收")),
                        "change_pct": _to_decimal(row.get("涨跌幅")),
                        "quoted_at": datetime.now(),
                        "source": "akshare.stock_zh_index_spot_sina",
                    }
            except Exception:
                pass

            xq_symbol = prefixed_candidates[0].upper()
            xq_error: Exception | None = None
            try:
                with _no_proxy_environment():
                    frame = ak.stock_individual_spot_xq(symbol=xq_symbol)
                values = {str(item["item"]): item["value"] for _, item in frame.iterrows()}
                return {
                    "symbol": symbol,
                    "market": "CN",
                    "name": str(values.get("名称", "")),
                    "last_price": _to_decimal(values.get("现价")),
                    "prev_close": _to_decimal(values.get("昨收")),
                    "change_pct": _to_decimal(values.get("涨幅")),
                    "quoted_at": datetime.now(),
                    "source": "akshare.stock_individual_spot_xq",
                }
            except Exception as exc:
                xq_error = exc

            # 指数现价缺失时，优先用指数日线接口退化，避免误落到个股日线。
            try:
                for prefixed in prefixed_candidates:
                    try:
                        with _no_proxy_environment():
                            index_daily = ak.stock_zh_index_daily(symbol=prefixed)
                        rows = _build_rows(
                            index_daily,
                            source="akshare.stock_zh_index_daily",
                            limit=2,
                        )
                        if not rows:
                            continue
                        last_row = rows[-1]
                        prev_row = rows[-2] if len(rows) > 1 else None
                        last_close = _to_decimal(last_row.get("close"))
                        prev_close = _to_decimal(prev_row.get("close")) if prev_row is not None else None
                        if last_close is None:
                            continue
                        change_pct = None
                        if prev_close not in {None, Decimal("0")}:
                            change_pct = ((last_close - prev_close) / prev_close) * Decimal("100")
                        return {
                            "symbol": symbol,
                            "market": "CN",
                            "name": "",
                            "last_price": last_close,
                            "prev_close": prev_close,
                            "change_pct": change_pct,
                            "quoted_at": datetime.now(),
                            "source": "akshare.stock_zh_index_daily.fallback_close",
                        }
                    except Exception:
                        continue
            except Exception:
                pass

            # 中证指数历史接口兜底（如 932000）。
            try:
                with _no_proxy_environment():
                    csindex_df = ak.stock_zh_index_hist_csindex(
                        symbol=_normalize_cn_symbol(symbol),
                        start_date=(date.today() - timedelta(days=20)).strftime("%Y%m%d"),
                        end_date=date.today().strftime("%Y%m%d"),
                    )
                if csindex_df is not None and not csindex_df.empty:
                    last_row = csindex_df.tail(1).iloc[0]
                    prev_row = csindex_df.tail(2).iloc[0] if len(csindex_df) > 1 else None
                    last_close = _to_decimal(last_row.get("收盘"))
                    prev_close = _to_decimal(prev_row.get("收盘")) if prev_row is not None else None
                    if last_close is not None:
                        change_pct = None
                        if prev_close not in {None, Decimal("0")}:
                            change_pct = ((last_close - prev_close) / prev_close) * Decimal("100")
                        return {
                            "symbol": symbol,
                            "market": "CN",
                            "name": str(last_row.get("指数中文简称", "")),
                            "last_price": last_close,
                            "prev_close": prev_close,
                            "change_pct": change_pct,
                            "quoted_at": datetime.now(),
                            "source": "akshare.stock_zh_index_hist_csindex.fallback_close",
                        }
            except Exception:
                pass

            # 同花顺行业指数兜底（如 881157 证券）。
            try:
                normalized_symbol = _normalize_cn_symbol(symbol)
                with _no_proxy_environment():
                    ths_names = ak.stock_board_industry_name_ths()
                matched = ths_names[ths_names["code"].astype(str) == normalized_symbol]
                if not matched.empty:
                    ths_name = str(matched.iloc[0].get("name"))
                    with _no_proxy_environment():
                        ths_df = ak.stock_board_industry_index_ths(
                            symbol=ths_name,
                            start_date=(date.today() - timedelta(days=20)).strftime("%Y%m%d"),
                            end_date=date.today().strftime("%Y%m%d"),
                        )
                    if ths_df is not None and not ths_df.empty:
                        last_row = ths_df.tail(1).iloc[0]
                        prev_row = ths_df.tail(2).iloc[0] if len(ths_df) > 1 else None
                        last_close = _to_decimal(last_row.get("收盘价"))
                        prev_close = _to_decimal(prev_row.get("收盘价")) if prev_row is not None else None
                        if last_close is not None:
                            change_pct = None
                            if prev_close not in {None, Decimal("0")}:
                                change_pct = ((last_close - prev_close) / prev_close) * Decimal("100")
                            return {
                                "symbol": symbol,
                                "market": "CN",
                                "name": ths_name,
                                "last_price": last_close,
                                "prev_close": prev_close,
                                "change_pct": change_pct,
                                "quoted_at": datetime.now(),
                                "source": "akshare.stock_board_industry_index_ths.fallback_close",
                            }
            except Exception:
                pass

            raise LookupError(f"spot quote not found: CN:{symbol}") from xq_error

        if market_key == "HK":
            hk_symbol = _normalize_hk_symbol(symbol)
            with _no_proxy_environment():
                frame = ak.stock_hk_hist_min_em(symbol=hk_symbol, period="1")
            if frame.empty:
                raise LookupError(f"spot quote not found: HK:{symbol}")
            row = frame.tail(1).iloc[0]
            return {
                "symbol": hk_symbol,
                "market": "HK",
                "name": "",
                "last_price": _to_decimal(row.get("收盘")),
                "prev_close": None,
                "change_pct": None,
                "quoted_at": datetime.now(),
                "source": "akshare.stock_hk_hist_min_em",
            }

        if market_key == "MACRO":
            symbol_key = symbol.strip().upper()
            if symbol_key == "CN10Y":
                with _no_proxy_environment():
                    frame = ak.bond_zh_us_rate()
                if frame is None or frame.empty:
                    raise LookupError("spot quote not found: MACRO:CN10Y")
                last = frame.tail(1).iloc[0]
                prev = frame.tail(2).iloc[0] if len(frame) > 1 else None
                last_price = _to_decimal(last.get("中国国债收益率10年"))
                prev_close = _to_decimal(prev.get("中国国债收益率10年")) if prev is not None else None
                change_pct = None
                if last_price is not None and prev_close not in {None, Decimal("0")}:
                    change_pct = ((last_price - prev_close) / prev_close) * Decimal("100")
                return {
                    "symbol": symbol_key,
                    "market": "MACRO",
                    "name": "中国国债十年期",
                    "last_price": last_price,
                    "prev_close": prev_close,
                    "change_pct": change_pct,
                    "quoted_at": datetime.now(),
                    "source": "akshare.bond_zh_us_rate",
                }

            fx_pair_map = {
                "USDCNH": "USD/CNH",
                "HKDCNY": "HKD/CNY",
            }
            pair = fx_pair_map.get(symbol_key)
            if pair is not None:
                with _no_proxy_environment():
                    frame = ak.fx_spot_quote()
                matched = frame[frame["货币对"].astype(str).str.upper() == pair]
                if not matched.empty:
                    row = matched.iloc[0]
                    bid = _to_decimal(row.get("买报价"))
                    ask = _to_decimal(row.get("卖报价"))
                    last_price = None
                    if bid is not None and ask is not None:
                        last_price = ((bid + ask) / Decimal("2")).quantize(Decimal("0.0001"))
                    elif bid is not None:
                        last_price = bid.quantize(Decimal("0.0001"))
                    elif ask is not None:
                        last_price = ask.quantize(Decimal("0.0001"))
                    if last_price is not None:
                        return {
                            "symbol": symbol_key,
                            "market": "MACRO",
                            "name": "",
                            "last_price": last_price,
                            "prev_close": None,
                            "change_pct": None,
                            "quoted_at": datetime.now(),
                            "source": "akshare.fx_spot_quote",
                        }

            raise LookupError(f"spot quote not found: MACRO:{symbol}")

        raise ValueError(f"unsupported market: {market}")

    def get_kline(
        self,
        symbol: str,
        market: str,
        *,
        limit: int = 120,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        market_key = market.strip().upper()
        ak = _load_akshare()
        safe_limit = max(1, min(limit, 1000))
        start = start_date or (date.today() - timedelta(days=max(safe_limit * 3, 90))).strftime("%Y%m%d")
        end = end_date or date.today().strftime("%Y%m%d")

        if market_key == "CN":
            for prefixed in _cn_prefixed_candidates(symbol):
                try:
                    with _no_proxy_environment():
                        index_df = ak.stock_zh_index_daily(symbol=prefixed)
                    rows = _build_rows(
                        index_df,
                        source="akshare.stock_zh_index_daily",
                        limit=safe_limit,
                    )
                    if rows:
                        return rows
                except Exception:
                    continue
            with _no_proxy_environment():
                stock_df = ak.stock_zh_a_hist(
                    symbol=_normalize_cn_symbol(symbol),
                    period="daily",
                    start_date=start,
                    end_date=end,
                    adjust="",
                )
            return _build_rows(
                stock_df,
                source="akshare.stock_zh_a_hist",
                limit=safe_limit,
            )

        if market_key == "HK":
            with _no_proxy_environment():
                hk_df = ak.stock_hk_hist(
                    symbol=_normalize_hk_symbol(symbol),
                    period="daily",
                    start_date=start,
                    end_date=end,
                    adjust="",
                )
            return _build_rows(
                hk_df,
                source="akshare.stock_hk_hist",
                limit=safe_limit,
            )

        raise ValueError(f"unsupported market: {market}")
