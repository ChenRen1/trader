"""股指期货-现货基差计算服务。"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from dataclasses import dataclass
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


def _to_decimal(value: object) -> Decimal | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return Decimal(text)


def _load_akshare() -> Any:
    try:
        return importlib.import_module("akshare")
    except ModuleNotFoundError as exc:
        raise RuntimeError("akshare 未安装，无法计算股指基差。") from exc


def _cn_prefixed_candidates(symbol: str) -> list[str]:
    cleaned = "".join(char for char in symbol.strip().lower() if char.isalnum())
    digits = "".join(char for char in cleaned if char.isdigit()).zfill(6)
    return [f"sh{digits}", f"sz{digits}", f"bj{digits}"]


@dataclass(frozen=True)
class IndexBasisRow:
    future_code: str
    name: str
    spot_symbol: str
    future_close: Decimal | None
    spot_price: Decimal | None
    basis: Decimal | None
    basis_pct: Decimal | None
    trade_date: date | None
    status: str
    future_source: str = ""
    error: str = ""

    def as_dict(self) -> dict[str, str | None]:
        return {
            "future_code": self.future_code,
            "name": self.name,
            "spot_symbol": self.spot_symbol,
            "future_close": str(self.future_close) if self.future_close is not None else None,
            "spot_price": str(self.spot_price) if self.spot_price is not None else None,
            "basis": str(self.basis) if self.basis is not None else None,
            "basis_pct": str(self.basis_pct) if self.basis_pct is not None else None,
            "trade_date": self.trade_date.isoformat() if self.trade_date is not None else None,
            "status": self.status,
            "future_source": self.future_source,
            "error": self.error or None,
        }


@dataclass(frozen=True)
class IndexBasisSnapshot:
    calculated_at: datetime
    rows: list[IndexBasisRow]


class IndexBasisService:
    """计算 IF/IH/IC/IM（优先加权）与指数现货基差。"""

    CONTRACTS: tuple[tuple[str, str, str], ...] = (
        ("IF", "沪深300", "000300"),
        ("IH", "上证50", "000016"),
        ("IC", "中证500", "000905"),
        ("IM", "中证1000", "000852"),
    )
    CONTRACT_BY_SPOT: dict[str, tuple[str, str, str]] = {item[2]: item for item in CONTRACTS}

    @classmethod
    def _calculate_single_row(cls, future_code: str, name: str, spot_symbol: str) -> IndexBasisRow:
        try:
            future_close, trade_date = cls._fetch_future_weighted_price(future_code)
            future_source = "open_interest_weighted"
            if future_close is None:
                future_close, trade_date = cls._fetch_future_close(future_code)
                future_source = "continuous_fallback"
            spot_price = cls._fetch_spot_price(spot_symbol)
            if future_close is None or spot_price is None:
                return IndexBasisRow(
                    future_code=future_code,
                    name=name,
                    spot_symbol=spot_symbol,
                    future_close=future_close,
                    spot_price=spot_price,
                    basis=None,
                    basis_pct=None,
                    trade_date=trade_date,
                    status="missing_data",
                    future_source=future_source,
                    error="future_close or spot_price is empty",
                )
            basis = future_close - spot_price
            basis_pct = None
            if spot_price != Decimal("0"):
                basis_pct = (basis / spot_price * Decimal("100")).quantize(Decimal("0.01"))
            return IndexBasisRow(
                future_code=future_code,
                name=name,
                spot_symbol=spot_symbol,
                future_close=future_close,
                spot_price=spot_price,
                basis=basis.quantize(Decimal("0.01")),
                basis_pct=basis_pct,
                trade_date=trade_date,
                status="ok",
                future_source=future_source,
            )
        except Exception as exc:
            return IndexBasisRow(
                future_code=future_code,
                name=name,
                spot_symbol=spot_symbol,
                future_close=None,
                spot_price=None,
                basis=None,
                basis_pct=None,
                trade_date=None,
                status="error",
                future_source="",
                error=str(exc),
            )

    @classmethod
    def _calculate_rows(cls) -> list[IndexBasisRow]:
        return [cls._calculate_single_row(future_code, name, spot_symbol) for future_code, name, spot_symbol in cls.CONTRACTS]

    @classmethod
    def _fetch_future_close(cls, future_code: str) -> tuple[Decimal | None, date | None]:
        ak = _load_akshare()
        symbol = f"{future_code}0"
        with _no_proxy_environment():
            frame = ak.futures_main_sina(symbol=symbol)
        if frame is None or frame.empty:
            return None, None
        row = frame.tail(1).iloc[0]
        trade_date = row.get("日期")
        close_value = _to_decimal(row.get("收盘价"))
        return close_value, trade_date

    @classmethod
    def _fetch_cffex_contracts(cls, future_code: str) -> tuple[list[str], date | None]:
        ak = _load_akshare()
        base_day = date.today()
        for delta in range(0, 10):
            day = base_day - timedelta(days=delta)
            day_str = day.strftime("%Y%m%d")
            try:
                with _no_proxy_environment():
                    info_df = ak.futures_contract_info_cffex(date=day_str)
                if info_df is None or info_df.empty:
                    continue
                subset = info_df[info_df["品种"].astype(str) == future_code]
                if subset.empty:
                    continue
                contracts = (
                    subset["合约代码"]
                    .astype(str)
                    .dropna()
                    .drop_duplicates()
                    .sort_values()
                    .tolist()
                )
                if contracts:
                    return contracts, day
            except Exception:
                continue
        return [], None

    @classmethod
    def _fetch_future_weighted_price(cls, future_code: str) -> tuple[Decimal | None, date | None]:
        ak = _load_akshare()
        contracts, trade_day = cls._fetch_cffex_contracts(future_code)
        if not contracts:
            return None, trade_day

        with _no_proxy_environment():
            quote_df = ak.futures_zh_spot(symbol=",".join(contracts), market="FF", adjust="0")
        if quote_df is None or quote_df.empty:
            return None, trade_day

        weighted_sum = Decimal("0")
        weight_total = Decimal("0")
        for _, row in quote_df.iterrows():
            price = _to_decimal(row.get("current_price"))
            hold = _to_decimal(row.get("hold"))
            if price is None or hold is None or hold <= Decimal("0"):
                continue
            weighted_sum += price * hold
            weight_total += hold
        if weight_total == Decimal("0"):
            return None, trade_day
        return (weighted_sum / weight_total).quantize(Decimal("0.01")), trade_day

    @classmethod
    def _fetch_spot_price(cls, symbol: str) -> Decimal | None:
        ak = _load_akshare()
        prefixed = _cn_prefixed_candidates(symbol)

        try:
            with _no_proxy_environment():
                spot_df = ak.stock_zh_index_spot_sina()
            hit = spot_df[spot_df["代码"].astype(str).isin(prefixed)]
            if not hit.empty:
                row = hit.iloc[0]
                price = _to_decimal(row.get("最新价"))
                if price is not None:
                    return price
        except Exception:
            pass

        for code in prefixed:
            try:
                with _no_proxy_environment():
                    daily_df = ak.stock_zh_index_daily(symbol=code)
                if daily_df is None or daily_df.empty:
                    continue
                row = daily_df.tail(1).iloc[0]
                price = _to_decimal(row.get("close"))
                if price is not None:
                    return price
            except Exception:
                continue
        return None

    @classmethod
    def calculate_snapshot(cls) -> IndexBasisSnapshot:
        return IndexBasisSnapshot(calculated_at=datetime.now(), rows=cls._calculate_rows())

    @classmethod
    def calculate(cls) -> list[IndexBasisRow]:
        """兼容旧调用：返回结果行列表。"""
        return cls.calculate_snapshot().rows

    @classmethod
    def calculate_for_spot_symbol(cls, spot_symbol: str) -> IndexBasisRow | None:
        mapping = cls.CONTRACT_BY_SPOT.get(spot_symbol)
        if mapping is None:
            return None
        future_code, name, symbol = mapping
        return cls._calculate_single_row(future_code, name, symbol)
