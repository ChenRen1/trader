"""策略股票池构建服务。"""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
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
        raise RuntimeError("akshare 未安装，无法构建指数股票池。") from exc


@dataclass(frozen=True)
class IndexConstituent:
    index_code: str
    index_name: str
    symbol: str
    name: str
    fetched_at: datetime


@dataclass(frozen=True)
class DividendUniverseConfig:
    index_codes: tuple[str, ...] = ("000015", "000922")


class DividendUniverseService:
    """从红利指数构建策略股票池。"""

    @staticmethod
    def _normalize_symbol(symbol: object) -> str:
        digits = "".join(ch for ch in str(symbol).strip() if ch.isdigit())
        return digits.zfill(6)

    @classmethod
    def fetch_index_constituents(cls, index_code: str) -> list[IndexConstituent]:
        ak = _load_akshare()
        frame = None
        try:
            with _no_proxy_environment():
                frame = ak.index_stock_cons_csindex(symbol=index_code)
        except Exception:
            frame = None
        if frame is None or frame.empty:
            with _no_proxy_environment():
                frame = ak.index_stock_cons(symbol=index_code)
        if frame is None or frame.empty:
            return []

        fetched_at = datetime.now()
        rows: list[IndexConstituent] = []
        for _, row in frame.iterrows():
            symbol = cls._normalize_symbol(row.get("成分券代码") or row.get("品种代码"))
            if not symbol:
                continue
            name = str(row.get("成分券名称") or row.get("品种名称") or "").strip()
            index_name = str(row.get("指数名称") or "").strip()
            rows.append(
                IndexConstituent(
                    index_code=index_code,
                    index_name=index_name,
                    symbol=symbol,
                    name=name,
                    fetched_at=fetched_at,
                )
            )
        return rows

    @classmethod
    def build_universe(cls, config: DividendUniverseConfig | None = None) -> list[IndexConstituent]:
        cfg = config or DividendUniverseConfig()
        merged: dict[str, IndexConstituent] = {}
        for index_code in cfg.index_codes:
            for item in cls.fetch_index_constituents(index_code):
                merged[item.symbol] = item
        return sorted(merged.values(), key=lambda item: item.symbol)
