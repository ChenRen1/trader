"""成交驱动的持仓与账户同步服务。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from trader.database.models import Account, Fill, InstrumentPrice, Position
from trader.database.services.fx_rate import FxRateService

FOUR_DP = Decimal("0.0001")
EIGHT_DP = Decimal("0.00000001")


@dataclass
class _PositionState:
    signed_quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")


class FillSyncService:
    """当成交变化时，重算关联持仓与账户。"""

    @staticmethod
    @transaction.atomic
    def sync_fill(fill: Fill) -> Position:
        """同步单条成交，确保持仓和账户数据最新。"""
        position = fill.position or FillSyncService._get_or_create_position(fill)
        if fill.position_id != position.id:
            fill.position = position
            fill.save(update_fields=["position", "updated_at"])

        FillSyncService._recalculate_position(position)
        FillSyncService._recalculate_account(fill.account)
        return position

    @staticmethod
    @transaction.atomic
    def sync_position(position: Position) -> Position:
        """按某条持仓下的全部成交重算持仓。"""
        FillSyncService._recalculate_position(position)
        FillSyncService._recalculate_account(position.account)
        return position

    @staticmethod
    def _get_or_create_position(fill: Fill) -> Position:
        position = (
            Position.objects.filter(
                account=fill.account,
                instrument=fill.instrument,
                pricing_currency=fill.pricing_currency,
            )
            .order_by("-created_at")
            .first()
        )
        if position is not None:
            return position

        return Position.objects.create(
            account=fill.account,
            instrument=fill.instrument,
            pricing_currency=fill.pricing_currency,
            opened_at=fill.fill_time,
        )

    @staticmethod
    def _recalculate_position(position: Position) -> None:
        fills = list(
            position.fills.select_related("instrument")
            .order_by("fill_time", "created_at", "id")
        )
        if not fills:
            position.quantity = Decimal("0")
            position.available_quantity = Decimal("0")
            position.average_price = Decimal("0")
            position.cost_basis = Decimal("0")
            position.market_value = Decimal("0")
            position.unrealized_pnl = Decimal("0")
            position.position_ratio = Decimal("0")
            position.status = Position.Status.CLOSED
            position.opened_at = None
            position.closed_at = None
            position.save()
            return

        state = _PositionState()
        opened_at = fills[0].fill_time
        closed_at = None

        for fill in fills:
            quantity = Decimal(fill.quantity)
            delta = quantity if fill.side == Fill.Side.BUY else -quantity
            state = FillSyncService._apply_fill(state, fill.price, delta)
            if state.signed_quantity == Decimal("0"):
                closed_at = fill.fill_time
            else:
                closed_at = None

        signed_quantity = state.signed_quantity.quantize(EIGHT_DP)
        quantity = abs(signed_quantity).quantize(EIGHT_DP)
        average_price = state.average_price.quantize(FOUR_DP) if quantity != Decimal("0") else Decimal("0")
        cost_basis = (quantity * average_price).quantize(FOUR_DP)
        side = Position.Side.SHORT if signed_quantity < 0 else Position.Side.LONG

        mark_price = FillSyncService._get_mark_price(position, fallback=average_price)
        market_value = (signed_quantity * mark_price).quantize(FOUR_DP)
        unrealized_pnl = FillSyncService._calculate_unrealized_pnl(
            side=side,
            quantity=quantity,
            average_price=average_price,
            mark_price=mark_price,
        )

        position.side = side
        position.quantity = quantity
        position.available_quantity = quantity
        position.average_price = average_price
        position.cost_basis = cost_basis
        position.market_value = market_value
        position.unrealized_pnl = unrealized_pnl
        position.position_ratio = Decimal("0")
        position.status = Position.Status.OPEN if quantity != Decimal("0") else Position.Status.CLOSED
        position.opened_at = opened_at if quantity != Decimal("0") or opened_at else None
        position.closed_at = closed_at if quantity == Decimal("0") else None
        position.save()

    @staticmethod
    def _apply_fill(state: _PositionState, price: Decimal, delta: Decimal) -> _PositionState:
        signed_quantity = state.signed_quantity
        average_price = state.average_price

        if signed_quantity == Decimal("0"):
            return _PositionState(signed_quantity=delta, average_price=Decimal(price))

        if signed_quantity > 0 and delta > 0:
            total_quantity = signed_quantity + delta
            average_price = (
                (average_price * signed_quantity) + (Decimal(price) * delta)
            ) / total_quantity
            return _PositionState(signed_quantity=total_quantity, average_price=average_price)

        if signed_quantity < 0 and delta < 0:
            total_quantity = abs(signed_quantity) + abs(delta)
            average_price = (
                (average_price * abs(signed_quantity)) + (Decimal(price) * abs(delta))
            ) / total_quantity
            return _PositionState(signed_quantity=signed_quantity + delta, average_price=average_price)

        remaining = signed_quantity + delta
        if signed_quantity > 0 and delta < 0:
            if remaining > 0:
                return _PositionState(signed_quantity=remaining, average_price=average_price)
            if remaining == 0:
                return _PositionState()
            return _PositionState(signed_quantity=remaining, average_price=Decimal(price))

        if signed_quantity < 0 and delta > 0:
            if remaining < 0:
                return _PositionState(signed_quantity=remaining, average_price=average_price)
            if remaining == 0:
                return _PositionState()
            return _PositionState(signed_quantity=remaining, average_price=Decimal(price))

        return _PositionState(signed_quantity=remaining, average_price=Decimal(price))

    @staticmethod
    def _get_mark_price(position: Position, *, fallback: Decimal) -> Decimal:
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
            return fallback
        return Decimal(str(latest_price))

    @staticmethod
    def _calculate_unrealized_pnl(
        *,
        side: str,
        quantity: Decimal,
        average_price: Decimal,
        mark_price: Decimal,
    ) -> Decimal:
        if quantity == Decimal("0"):
            return Decimal("0")
        if side == Position.Side.SHORT:
            return ((average_price - mark_price) * quantity).quantize(FOUR_DP)
        return ((mark_price - average_price) * quantity).quantize(FOUR_DP)

    @staticmethod
    def _recalculate_account(account: Account) -> None:
        fills = list(account.fills.order_by("fill_time", "created_at", "id"))
        if fills:
            cash_balance = Decimal(account.initial_balance)
            for fill in fills:
                gross_amount = Decimal(fill.amount) if fill.amount else Decimal(fill.price) * Decimal(fill.quantity)
                costs = Decimal(fill.commission) + Decimal(fill.tax)
                if fill.side == Fill.Side.BUY:
                    cash_balance -= gross_amount + costs
                else:
                    cash_balance += gross_amount - costs
        else:
            cash_balance = Decimal(account.available_cash)

        position_totals = account.positions.aggregate(
            total_market_value=Sum("market_value"),
            total_unrealized_pnl=Sum("unrealized_pnl"),
        )
        del position_totals
        total_market_value = Decimal("0")
        total_unrealized_pnl = Decimal("0")
        for position in account.positions.select_related("instrument").all():
            total_market_value += FxRateService.convert(
                Decimal(str(position.market_value)),
                position.pricing_currency,
                account.base_currency,
            )
            total_unrealized_pnl += FxRateService.convert(
                Decimal(str(position.unrealized_pnl)),
                position.pricing_currency,
                account.base_currency,
            )
        total_market_value = total_market_value.quantize(FOUR_DP)
        total_unrealized_pnl = total_unrealized_pnl.quantize(FOUR_DP)
        frozen_cash = Decimal(str(account.frozen_cash)).quantize(FOUR_DP)
        liability = Decimal(str(account.liability)).quantize(FOUR_DP)
        total_equity = (cash_balance + frozen_cash + total_market_value - liability).quantize(FOUR_DP)

        account.available_cash = cash_balance.quantize(FOUR_DP)
        account.total_market_value = total_market_value
        account.total_unrealized_pnl = total_unrealized_pnl
        account.total_equity = total_equity
        account.save(
            update_fields=[
                "available_cash",
                "total_market_value",
                "total_unrealized_pnl",
                "total_equity",
                "updated_at",
            ]
        )
        FillSyncService._recalculate_position_ratios(account, total_equity=total_equity)

    @staticmethod
    def recalculate_account(account: Account) -> None:
        """对外暴露账户重算入口。"""
        FillSyncService._recalculate_account(account)

    @staticmethod
    def _recalculate_position_ratios(account: Account, *, total_equity: Decimal) -> None:
        """按账户总资产回写持仓占比。"""
        denominator = Decimal(str(total_equity))
        positions = list(account.positions.all())
        for position in positions:
            ratio = Decimal("0")
            if denominator != Decimal("0"):
                ratio = (abs(Decimal(str(position.market_value))) / denominator).quantize(EIGHT_DP)
            position.position_ratio = ratio
            position.save(update_fields=["position_ratio", "updated_at"])
