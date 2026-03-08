"""价格驱动的持仓与账户同步服务。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from trader.database.models import Account, Instrument, InstrumentPrice, Position
from trader.database.services.fill_sync import FillSyncService
from trader.market.source import get_spot_price
from trader.risk_management import PositionRiskMonitor
from trader.strategy.services import AnnualReportDividendYieldService


class PriceSyncService:
    """当标的现价变化时，重算关联持仓与账户汇总。"""

    @staticmethod
    def _resolve_quote_market(instrument: Instrument) -> str:
        return instrument.market

    @staticmethod
    def _normalize_priced_at(raw_value: object) -> datetime:
        if isinstance(raw_value, datetime):
            quoted_at = raw_value
        else:
            quoted_at = timezone.now()
        if timezone.is_naive(quoted_at):
            return timezone.make_aware(quoted_at, timezone.get_current_timezone())
        return quoted_at

    @staticmethod
    @transaction.atomic
    def update_instrument_spot_price(instrument: Instrument) -> InstrumentPrice:
        """拉取标的现价并写入 instrument_prices。"""
        quote = get_spot_price(instrument.symbol, PriceSyncService._resolve_quote_market(instrument))
        priced_at = PriceSyncService._normalize_priced_at(quote.get("quoted_at"))
        source = str(quote.get("source") or "market.provider")

        payload: dict[str, Any] = {
            "last_price": quote.get("last_price"),
            "prev_close": quote.get("prev_close"),
            "source": source,
        }
        payload.update(PriceSyncService._build_dividend_payload(instrument=instrument, quote=quote))

        from trader.database.services.crud.instrument_price import InstrumentPriceService

        existing = InstrumentPrice.objects.filter(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=priced_at,
        ).first()
        if existing is not None:
            return InstrumentPriceService.update(
                existing,
                audit_source=source,
                **payload,
            )

        return InstrumentPriceService.create(
            instrument=instrument,
            bar_type=InstrumentPrice.BarType.SPOT,
            priced_at=priced_at,
            audit_source=source,
            **payload,
        )

    @staticmethod
    def _build_dividend_payload(*, instrument: Instrument, quote: dict[str, Any]) -> dict[str, Any]:
        if not (
            instrument.market == Instrument.Market.CN
            and instrument.instrument_type == Instrument.InstrumentType.STOCK
            and instrument.is_high_dividend
        ):
            return {}
        raw_price = quote.get("last_price")
        if raw_price in {None, ""}:
            return {}
        try:
            last_price = Decimal(str(raw_price))
        except Exception:
            return {}

        result = AnnualReportDividendYieldService.compute_for_symbol_with_price(
            symbol=instrument.symbol,
            name=instrument.name,
            last_price=last_price,
        )
        return {
            "annual_cash_dividend_per_10": result.cash_dividend_per_10,
            "annual_dividend_per_share": result.dividend_per_share,
            "annual_dividend_yield_pct": (
                (result.dividend_yield * Decimal("100")).quantize(Decimal("0.0001"))
                if result.dividend_yield is not None
                else None
            ),
            "annual_dividend_report": result.annual_report or "",
        }

    @staticmethod
    def update_spot_prices(*, instruments: list[Instrument] | None = None) -> dict[str, object]:
        """批量更新现价，返回成功与失败统计。"""
        if instruments is None:
            instruments = list(
                Instrument.objects.filter(
                    status=Instrument.Status.ACTIVE,
                    market__in=[Instrument.Market.CN, Instrument.Market.HK, Instrument.Market.MACRO],
                ).order_by("market", "symbol")
            )

        updated = 0
        errors: list[dict[str, str]] = []
        for instrument in instruments:
            try:
                PriceSyncService.update_instrument_spot_price(instrument)
                updated += 1
            except Exception as exc:
                errors.append(
                    {
                        "instrument": f"{instrument.symbol}.{instrument.market}",
                        "reason": str(exc),
                    }
                )
        return {
            "updated": updated,
            "failed": len(errors),
            "errors": errors,
        }

    @staticmethod
    @transaction.atomic
    def sync_price(price: InstrumentPrice) -> None:
        """按单条价格记录触发联动。"""
        if price.bar_type != InstrumentPrice.BarType.SPOT:
            return
        PriceSyncService.sync_instrument(price.instrument)

    @staticmethod
    @transaction.atomic
    def sync_instrument(instrument: Instrument) -> list[object]:
        """按标的重算全部关联持仓和账户。"""
        positions = list(
            Position.objects.filter(instrument=instrument)
            .select_related("account", "instrument")
            .order_by("id")
        )
        account_ids: set[int] = set()
        for position in positions:
            PriceSyncService._recalculate_position_mark_to_market(position)
            account_ids.add(position.account_id)

        for account_id in account_ids:
            account = Account.objects.filter(id=account_id).first()
            if account is not None:
                FillSyncService.recalculate_account(account)

        return PositionRiskMonitor().evaluate_model_positions(positions)

    @staticmethod
    def _recalculate_position_mark_to_market(position: Position) -> None:
        """仅按最新现价更新持仓估值，不按成交回算数量。"""
        latest_price = (
            InstrumentPrice.objects.filter(
                instrument=position.instrument,
                bar_type=InstrumentPrice.BarType.SPOT,
            )
            .order_by("-priced_at", "-created_at")
            .values_list("last_price", flat=True)
            .first()
        )
        if latest_price is None:
            return

        quantity = Decimal(str(position.quantity))
        average_price = Decimal(str(position.average_price))
        mark_price = Decimal(str(latest_price))
        if position.side == Position.Side.SHORT:
            market_value = (quantity * mark_price * Decimal("-1")).quantize(Decimal("0.0001"))
            unrealized_pnl = ((average_price - mark_price) * quantity).quantize(Decimal("0.0001"))
        else:
            market_value = (quantity * mark_price).quantize(Decimal("0.0001"))
            unrealized_pnl = ((mark_price - average_price) * quantity).quantize(Decimal("0.0001"))

        position.market_value = market_value
        position.unrealized_pnl = unrealized_pnl
        position.save(update_fields=["market_value", "unrealized_pnl", "updated_at"])
