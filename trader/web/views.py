"""Web 视图。"""

from __future__ import annotations

from decimal import Decimal

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from trader.market.services import IndexBasisService
from trader.market.source.provider import get_kline, get_spot_price


def home(request: HttpRequest) -> HttpResponse:
    """首页视图。"""
    return render(request, "trader/home.html")


def market_chart_index(request: HttpRequest) -> HttpResponse:
    """行情图入口页。"""
    watchlist = [
        {"name": "沪深300", "market": "CN", "symbol": "000300"},
        {"name": "上证50", "market": "CN", "symbol": "000016"},
        {"name": "中证500", "market": "CN", "symbol": "000905"},
        {"name": "中证1000", "market": "CN", "symbol": "000852"},
        {"name": "创业板指", "market": "CN", "symbol": "399006"},
        {"name": "科创50", "market": "CN", "symbol": "000688"},
        {"name": "恒生科技", "market": "HK", "symbol": "HSTECH"},
    ]
    return render(request, "trader/market_chart_index.html", {"watchlist": watchlist})


def market_chart_page(request: HttpRequest, market: str, symbol: str) -> HttpResponse:
    """单标的行情图页面。"""
    return render(
        request,
        "trader/market_chart.html",
        {
            "market": market.upper(),
            "symbol": symbol.upper(),
        },
    )


def market_chart_data(request: HttpRequest, market: str, symbol: str) -> JsonResponse:
    """单标的 K 线与现价接口。"""
    market_key = market.upper()
    symbol_key = symbol.upper()

    try:
        bars = get_kline(symbol_key, market_key, limit=120)
    except Exception as exc:
        return JsonResponse({"error": f"kline unavailable: {exc}"}, status=502)

    try:
        spot = get_spot_price(symbol_key, market_key)
    except Exception:
        spot = None

    def _float(value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except Exception:
            return None

    basis_row = None
    if market_key == "CN":
        basis_row = IndexBasisService.calculate_for_spot_symbol(symbol_key)

    payload = {
        "symbol": symbol_key,
        "market": market_key,
        "spot": (
            {
                "last_price": _float(spot.get("last_price")),
                "prev_close": _float(spot.get("prev_close")),
                "change_pct": _float(spot.get("change_pct")),
                "source": str(spot.get("source", "")),
            }
            if spot is not None
            else None
        ),
        "bars": [
            {
                "time": str(item["date"]),
                "open": _float(item["open"]),
                "high": _float(item["high"]),
                "low": _float(item["low"]),
                "close": _float(item["close"]),
                "volume": _float(item["volume"]),
            }
            for item in bars
        ],
        "basis": (
            {
                "future_code": basis_row.future_code,
                "future_price": _float(basis_row.future_close),
                "spot_price": _float(basis_row.spot_price),
                "basis": _float(basis_row.basis),
                "basis_pct": _float(basis_row.basis_pct),
                "trade_date": str(basis_row.trade_date) if basis_row.trade_date else None,
                "source": basis_row.future_source,
                "status": basis_row.status,
                "error": basis_row.error or None,
            }
            if basis_row is not None
            else None
        ),
    }
    return JsonResponse(payload)
