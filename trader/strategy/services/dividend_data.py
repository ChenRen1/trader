"""股息数据服务（年报口径）。"""

from __future__ import annotations

import importlib
import os
import random
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd
import requests

from trader.database import Instrument

ZERO = Decimal("0")


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
        raise RuntimeError("akshare 未安装，无法计算股息率。") from exc


def _to_decimal(value: object) -> Decimal | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "-"}:
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


@dataclass(frozen=True)
class AnnualDividendYieldResult:
    symbol: str
    name: str
    last_price: Decimal | None
    annual_report: str | None
    cash_dividend_per_10: Decimal | None
    dividend_per_share: Decimal | None
    dividend_yield: Decimal | None
    status: str
    error: str = ""


class AnnualReportDividendYieldService:
    """使用“最近完整年报分红 / 当前价”计算股息率。"""

    @staticmethod
    def _prefixed_candidates(symbol: str) -> list[str]:
        normalized = "".join(ch for ch in str(symbol).strip() if ch.isdigit()).zfill(6)
        if normalized.startswith("6"):
            return [f"sh{normalized}", f"sz{normalized}"]
        return [f"sz{normalized}", f"sh{normalized}"]

    @classmethod
    def _fetch_spot_price_sina(cls, symbol: str) -> Decimal | None:
        for prefixed in cls._prefixed_candidates(symbol):
            url = f"https://hq.sinajs.cn/rn={hex(random.randint(0, 2**31 - 1))[2:]}&list={prefixed}"
            try:
                with _no_proxy_environment():
                    response = requests.get(
                        url,
                        headers={"Referer": "https://finance.sina.com.cn"},
                        timeout=15,
                    )
                text = response.text.strip()
                if "=\"" not in text:
                    continue
                payload = text.split("=\"", 1)[1].rsplit("\"", 1)[0]
                fields = payload.split(",")
                if len(fields) < 4:
                    continue
                last_price = _to_decimal(fields[3])
                if last_price is not None and last_price > ZERO:
                    return last_price
            except Exception:
                continue
        return None

    @classmethod
    def _pick_latest_annual_cash_dividend(cls, symbol: str) -> tuple[str | None, Decimal | None]:
        ak = _load_akshare()
        with _no_proxy_environment():
            frame = ak.stock_dividend_cninfo(symbol=symbol)
        if frame is None or frame.empty:
            return None, None

        df = frame.copy()
        if "派息比例" not in df.columns:
            return None, None
        df["派息比例"] = pd.to_numeric(df["派息比例"], errors="coerce")
        df = df[df["派息比例"].notna() & (df["派息比例"] > 0)].copy()
        if df.empty:
            return None, None

        report_col = df.get("报告时间")
        if report_col is not None:
            report_text = df["报告时间"].astype(str)
            is_annual = report_text.str.contains("年报", na=False)
            is_non_annual = (
                report_text.str.contains("半年", na=False)
                | report_text.str.contains("中报", na=False)
                | report_text.str.contains("一季", na=False)
                | report_text.str.contains("三季", na=False)
            )
            df = df[is_annual & (~is_non_annual)]
            if df.empty:
                return None, None

        effective_date = pd.to_datetime(df.get("除权日"), errors="coerce")
        fallback_date = pd.to_datetime(df.get("实施方案公告日期"), errors="coerce")
        df["effective_date"] = effective_date.fillna(fallback_date)
        df = df.sort_values("effective_date", ascending=False)
        latest = df.iloc[0]
        report = str(latest.get("报告时间") or "").strip() or None
        return report, _to_decimal(latest.get("派息比例"))

    @classmethod
    def compute_for_symbol(cls, *, symbol: str, name: str = "") -> AnnualDividendYieldResult:
        try:
            report, cash_per_10 = cls._pick_latest_annual_cash_dividend(symbol)
            if cash_per_10 is None:
                return AnnualDividendYieldResult(
                    symbol=symbol,
                    name=name or symbol,
                    last_price=None,
                    annual_report=report,
                    cash_dividend_per_10=None,
                    dividend_per_share=None,
                    dividend_yield=None,
                    status="missing_annual_dividend",
                )

            last_price = cls._fetch_spot_price_sina(symbol)
            if last_price is None:
                return AnnualDividendYieldResult(
                    symbol=symbol,
                    name=name or symbol,
                    last_price=None,
                    annual_report=report,
                    cash_dividend_per_10=cash_per_10,
                    dividend_per_share=(cash_per_10 / Decimal("10")).quantize(Decimal("0.0001")),
                    dividend_yield=None,
                    status="missing_spot_price",
                )

            dividend_per_share = (cash_per_10 / Decimal("10")).quantize(Decimal("0.0001"))
            dividend_yield = (dividend_per_share / last_price).quantize(Decimal("0.0001"))
            return AnnualDividendYieldResult(
                symbol=symbol,
                name=name or symbol,
                last_price=last_price,
                annual_report=report,
                cash_dividend_per_10=cash_per_10,
                dividend_per_share=dividend_per_share,
                dividend_yield=dividend_yield,
                status="ok",
            )
        except Exception as exc:
            return AnnualDividendYieldResult(
                symbol=symbol,
                name=name or symbol,
                last_price=None,
                annual_report=None,
                cash_dividend_per_10=None,
                dividend_per_share=None,
                dividend_yield=None,
                status="error",
                error=str(exc),
            )

    @classmethod
    def compute_for_symbol_with_price(
        cls,
        *,
        symbol: str,
        last_price: Decimal,
        name: str = "",
    ) -> AnnualDividendYieldResult:
        try:
            report, cash_per_10 = cls._pick_latest_annual_cash_dividend(symbol)
            if cash_per_10 is None:
                return AnnualDividendYieldResult(
                    symbol=symbol,
                    name=name or symbol,
                    last_price=last_price,
                    annual_report=report,
                    cash_dividend_per_10=None,
                    dividend_per_share=None,
                    dividend_yield=None,
                    status="missing_annual_dividend",
                )
            dividend_per_share = (cash_per_10 / Decimal("10")).quantize(Decimal("0.0001"))
            dividend_yield = None
            if last_price > ZERO:
                dividend_yield = (dividend_per_share / last_price).quantize(Decimal("0.0001"))
            return AnnualDividendYieldResult(
                symbol=symbol,
                name=name or symbol,
                last_price=last_price,
                annual_report=report,
                cash_dividend_per_10=cash_per_10,
                dividend_per_share=dividend_per_share,
                dividend_yield=dividend_yield,
                status="ok" if dividend_yield is not None else "missing_spot_price",
            )
        except Exception as exc:
            return AnnualDividendYieldResult(
                symbol=symbol,
                name=name or symbol,
                last_price=last_price,
                annual_report=None,
                cash_dividend_per_10=None,
                dividend_per_share=None,
                dividend_yield=None,
                status="error",
                error=str(exc),
            )

    @classmethod
    def compute_for_high_dividend_instruments(cls) -> list[AnnualDividendYieldResult]:
        instruments = Instrument.objects.filter(
            market=Instrument.Market.CN,
            instrument_type=Instrument.InstrumentType.STOCK,
            is_high_dividend=True,
        ).order_by("symbol")
        return [
            cls.compute_for_symbol(symbol=item.symbol, name=item.name)
            for item in instruments
        ]
