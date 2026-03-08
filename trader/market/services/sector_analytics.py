"""板块成分股涨幅统计服务。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from statistics import median

import pandas as pd
import requests
from trader.market.source.provider import DefaultMarketProvider


@contextmanager
def _no_proxy_environment():
    import os

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


@dataclass(frozen=True)
class SectorConstituent:
    code: str
    name: str
    last_price: Decimal | None
    change_pct: Decimal | None


@dataclass(frozen=True)
class Hs300ConstituentQuote:
    code: str
    name: str
    sector_name: str
    last_price: Decimal | None
    change_pct: Decimal | None


class SectorAnalyticsService:
    """板块统计服务。"""

    BASE_URL = "https://q.10jqka.com.cn/thshy/detail/code/{sector_code}/page/{page}/"
    INDUSTRY_CACHE_PATH = Path(__file__).resolve().parent.parent / "cache" / "hs300_industry_cache_v2.csv"
    INDUSTRY_CACHE_TTL = timedelta(days=7)

    @staticmethod
    def _to_decimal(value: object) -> Decimal | None:
        text = str(value).strip()
        if text in {"", "nan", "None", "--", "-"}:
            return None
        text = text.replace("%", "").replace(",", "")
        try:
            return Decimal(text)
        except Exception:
            return None

    @classmethod
    def _resolve_sector_code(cls, *, sector_code: str | None, sector_name: str | None) -> str:
        if sector_code:
            return sector_code.strip()
        if not sector_name:
            raise ValueError("sector_code 或 sector_name 至少提供一个")
        try:
            import akshare as ak

            with _no_proxy_environment():
                name_df = ak.stock_board_industry_name_ths()
            matched = name_df[name_df["name"].astype(str) == sector_name.strip()]
            if matched.empty:
                raise ValueError(f"未找到板块名称: {sector_name}")
            return str(matched.iloc[0]["code"]).strip()
        except Exception as exc:
            raise RuntimeError(f"板块名称解析失败: {sector_name}, {exc}") from exc

    @classmethod
    def _parse_page(cls, *, sector_code: str, page: int) -> list[SectorConstituent]:
        url = cls.BASE_URL.format(sector_code=sector_code, page=page)
        with _no_proxy_environment():
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
        response.raise_for_status()
        html_text = response.content.decode("gbk", errors="ignore")

        tables = pd.read_html(StringIO(html_text))
        if not tables:
            return []
        table = tables[0]
        if "代码" not in table.columns or "名称" not in table.columns:
            return []
        if len(table) == 1 and str(table.iloc[0]["代码"]).strip() == "暂无成份股数据":
            return []

        rows: list[SectorConstituent] = []
        for _, row in table.iterrows():
            code_text = str(row.get("代码", "")).strip()
            if not code_text or code_text == "暂无成份股数据":
                continue
            rows.append(
                SectorConstituent(
                    code=code_text.zfill(6) if code_text.isdigit() else code_text,
                    name=str(row.get("名称", "")).strip(),
                    last_price=cls._to_decimal(row.get("现价")),
                    change_pct=cls._to_decimal(row.get("涨跌幅(%)")),
                )
            )
        return rows

    @classmethod
    def fetch_sector_constituents(
        cls,
        *,
        sector_code: str | None = None,
        sector_name: str | None = None,
    ) -> list[SectorConstituent]:
        resolved_sector_code = cls._resolve_sector_code(sector_code=sector_code, sector_name=sector_name)
        results: list[SectorConstituent] = []
        page = 1
        while True:
            page_rows = cls._parse_page(sector_code=resolved_sector_code, page=page)
            if not page_rows:
                break
            results.extend(page_rows)
            page += 1
            if page > 30:
                break
        return results

    @classmethod
    def summarize_sector_change_stats(
        cls,
        *,
        sector_code: str | None = None,
        sector_name: str | None = None,
    ) -> dict[str, object]:
        resolved_sector_code = cls._resolve_sector_code(sector_code=sector_code, sector_name=sector_name)
        rows = cls.fetch_sector_constituents(sector_code=resolved_sector_code)
        valid_rows = [item for item in rows if item.change_pct is not None]
        changes = [item.change_pct for item in valid_rows]
        up = [item for item in valid_rows if item.change_pct > Decimal("0")]
        down = [item for item in valid_rows if item.change_pct < Decimal("0")]
        flat = [item for item in valid_rows if item.change_pct == Decimal("0")]

        b1 = Decimal("1")
        b3 = Decimal("3")
        b5 = Decimal("5")
        distribution = {
            "up_ge_5": sum(1 for item in valid_rows if item.change_pct >= b5),
            "up_3_to_5": sum(1 for item in valid_rows if b3 <= item.change_pct < b5),
            "up_1_to_3": sum(1 for item in valid_rows if b1 <= item.change_pct < b3),
            "up_0_to_1": sum(1 for item in valid_rows if Decimal("0") < item.change_pct < b1),
            "flat": len(flat),
            "down_0_to_1": sum(1 for item in valid_rows if -b1 < item.change_pct < Decimal("0")),
            "down_1_to_3": sum(1 for item in valid_rows if -b3 < item.change_pct <= -b1),
            "down_3_to_5": sum(1 for item in valid_rows if -b5 < item.change_pct <= -b3),
            "down_ge_5": sum(1 for item in valid_rows if item.change_pct <= -b5),
        }

        mean_change = None
        median_change = None
        if changes:
            mean_change = (sum(changes) / Decimal(len(changes))).quantize(Decimal("0.01"))
            median_change = Decimal(str(median(changes))).quantize(Decimal("0.01"))

        return {
            "sector_code": resolved_sector_code,
            "sector_name": sector_name or "",
            "total_constituents": len(rows),
            "valid_change_count": len(valid_rows),
            "up_count": len(up),
            "down_count": len(down),
            "flat_count": len(flat),
            "mean_change_pct": mean_change,
            "median_change_pct": median_change,
            "distribution": distribution,
        }

    @classmethod
    def fetch_hs300_constituents(cls) -> pd.DataFrame:
        import akshare as ak

        with _no_proxy_environment():
            frame = ak.index_stock_cons_csindex(symbol="000300")
        return frame.copy()

    @classmethod
    def _load_industry_cache(cls) -> dict[str, tuple[str, datetime]]:
        if not cls.INDUSTRY_CACHE_PATH.exists():
            return {}
        try:
            frame = pd.read_csv(cls.INDUSTRY_CACHE_PATH)
        except Exception:
            return {}

        cache: dict[str, tuple[str, datetime]] = {}
        for _, row in frame.iterrows():
            symbol = str(row.get("symbol", "")).strip().zfill(6)
            sector_name = str(row.get("sector_name", "")).strip()
            cached_at = pd.to_datetime(row.get("cached_at"), errors="coerce")
            if not symbol or not sector_name or pd.isna(cached_at):
                continue
            cache[symbol] = (sector_name, cached_at.to_pydatetime())
        return cache

    @classmethod
    def _save_industry_cache(cls, cache: dict[str, tuple[str, datetime]]) -> None:
        cls.INDUSTRY_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {"symbol": symbol, "sector_name": sector_name, "cached_at": cached_at.isoformat()}
            for symbol, (sector_name, cached_at) in sorted(cache.items())
        ]
        pd.DataFrame(rows).to_csv(cls.INDUSTRY_CACHE_PATH, index=False)

    @classmethod
    def _load_sw_industry_name_map(cls) -> dict[str, str]:
        import akshare as ak

        with _no_proxy_environment():
            frame = ak.stock_industry_category_cninfo(symbol="申银万国行业分类标准")
        mapping: dict[str, str] = {}
        for _, row in frame.iterrows():
            code = str(row.get("类目编码", "")).strip()
            name = str(row.get("类目名称", "")).strip()
            level = row.get("分级")
            if not code or not name or pd.isna(level):
                continue
            try:
                numeric_level = int(level)
            except Exception:
                continue
            if numeric_level >= 1:
                mapping[code] = name
        return mapping

    @classmethod
    def _load_latest_sw_industry_by_symbol(cls) -> dict[str, str]:
        import akshare as ak

        with _no_proxy_environment():
            frame = ak.stock_industry_clf_hist_sw()
        if frame is None or frame.empty:
            return {}

        data = frame.copy()
        data["symbol"] = data["symbol"].astype(str).str.zfill(6)
        data["update_time"] = pd.to_datetime(data["update_time"], errors="coerce")
        data = data.sort_values(["symbol", "update_time"])
        latest = data.groupby("symbol", as_index=False).tail(1)

        name_map = cls._load_sw_industry_name_map()
        result: dict[str, str] = {}
        for _, row in latest.iterrows():
            symbol = str(row.get("symbol", "")).strip().zfill(6)
            raw_code = str(row.get("industry_code", "")).strip()
            if not symbol or not raw_code:
                continue

            candidates = [f"S{raw_code}"]
            if len(raw_code) >= 2:
                candidates.append(f"S{raw_code[:2]}")

            sector_name = None
            for code in candidates:
                sector_name = name_map.get(code)
                if sector_name:
                    break
            result[symbol] = sector_name or "未分类"
        return result

    @classmethod
    def resolve_latest_industry_name(
        cls,
        symbol: str,
        *,
        cache: dict[str, tuple[str, datetime]] | None = None,
        force_refresh: bool = False,
    ) -> str:
        normalized_symbol = str(symbol).strip().zfill(6)
        if cache is not None and not force_refresh:
            cached = cache.get(normalized_symbol)
            if cached is not None:
                sector_name, cached_at = cached
                if datetime.now() - cached_at <= cls.INDUSTRY_CACHE_TTL:
                    return sector_name

        latest_map = cls._load_latest_sw_industry_by_symbol()
        sector_name = latest_map.get(normalized_symbol, "未分类")
        if cache is not None:
            cache[normalized_symbol] = (sector_name, datetime.now())
        return sector_name

    @classmethod
    def _fetch_single_hs300_quote(
        cls,
        *,
        provider: DefaultMarketProvider,
        code: str,
        name: str,
        sector_name: str,
    ) -> Hs300ConstituentQuote:
        try:
            quote = provider.get_spot_price(code, "CN")
            last_price = cls._to_decimal(quote.get("last_price"))
            change_pct = cls._to_decimal(quote.get("change_pct"))
        except Exception:
            last_price = None
            change_pct = None
        return Hs300ConstituentQuote(
            code=code,
            name=name,
            sector_name=sector_name,
            last_price=last_price,
            change_pct=change_pct,
        )

    @classmethod
    def fetch_hs300_sector_quotes(
        cls,
        *,
        max_workers: int = 8,
        refresh_industry_cache: bool = False,
    ) -> list[Hs300ConstituentQuote]:
        constituents = cls.fetch_hs300_constituents()
        provider = DefaultMarketProvider()
        industry_cache = cls._load_industry_cache()
        quotes: list[Hs300ConstituentQuote] = []
        industry_tasks: list[tuple[str, str]] = []
        tasks: list[tuple[str, str]] = []

        for _, row in constituents.iterrows():
            code = str(row.get("成分券代码", "")).strip().zfill(6)
            name = str(row.get("成分券名称", "")).strip()
            if not code:
                continue
            cached = industry_cache.get(code)
            if (
                not refresh_industry_cache
                and cached is not None
                and datetime.now() - cached[1] <= cls.INDUSTRY_CACHE_TTL
            ):
                tasks.append((code, name))
            else:
                industry_tasks.append((code, name))

        if industry_tasks:
            try:
                latest_map = cls._load_latest_sw_industry_by_symbol()
            except Exception:
                latest_map = {}
            for code, name in industry_tasks:
                sector_name = latest_map.get(code, "未分类")
                industry_cache[code] = (sector_name, datetime.now())
                tasks.append((code, name))

        cls._save_industry_cache(industry_cache)

        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
            futures = {
                executor.submit(
                    cls._fetch_single_hs300_quote,
                    provider=provider,
                    code=code,
                    name=name,
                    sector_name=industry_cache.get(code, ("未分类", datetime.now()))[0],
                ): code
                for code, name in tasks
            }
            results_by_code: dict[str, Hs300ConstituentQuote] = {}
            for future in as_completed(futures):
                item = future.result()
                results_by_code[item.code] = item

        constituent_codes = [
            str(row.get("成分券代码", "")).strip().zfill(6)
            for _, row in constituents.iterrows()
            if str(row.get("成分券代码", "")).strip()
        ]
        for code in constituent_codes:
            if code in results_by_code:
                quotes.append(results_by_code[code])
        return quotes

    @classmethod
    def summarize_hs300_sector_change_stats(
        cls,
        *,
        max_workers: int = 8,
        refresh_industry_cache: bool = False,
    ) -> list[dict[str, object]]:
        quotes = cls.fetch_hs300_sector_quotes(
            max_workers=max_workers,
            refresh_industry_cache=refresh_industry_cache,
        )
        grouped: dict[str, list[Hs300ConstituentQuote]] = {}
        for item in quotes:
            grouped.setdefault(item.sector_name or "未分类", []).append(item)

        results: list[dict[str, object]] = []
        for sector_name, rows in grouped.items():
            valid_rows = [item for item in rows if item.change_pct is not None]
            changes = [item.change_pct for item in valid_rows]
            up_count = sum(1 for item in valid_rows if item.change_pct > Decimal("0"))
            down_count = sum(1 for item in valid_rows if item.change_pct < Decimal("0"))
            flat_count = sum(1 for item in valid_rows if item.change_pct == Decimal("0"))
            mean_change = None
            median_change = None
            if changes:
                mean_change = (sum(changes) / Decimal(len(changes))).quantize(Decimal("0.01"))
                median_change = Decimal(str(median(changes))).quantize(Decimal("0.01"))
            results.append(
                {
                    "sector_name": sector_name,
                    "constituent_count": len(rows),
                    "valid_change_count": len(valid_rows),
                    "up_count": up_count,
                    "down_count": down_count,
                    "flat_count": flat_count,
                    "mean_change_pct": mean_change,
                    "median_change_pct": median_change,
                }
            )

        results.sort(
            key=lambda item: (
                item["mean_change_pct"] is None,
                -(item["mean_change_pct"] or Decimal("0")),
                item["sector_name"],
            )
        )
        return results
