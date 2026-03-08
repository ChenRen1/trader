"""计算股指期货与现货基差。"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from trader.market.services import IndexBasisService


class Command(BaseCommand):
    help = "计算 IF/IH/IC/IM（持仓加权优先）与现货指数基差。"

    def handle(self, *args, **options):
        snapshot = IndexBasisService.calculate_snapshot()
        rows = snapshot.rows
        self.stdout.write(f"calculated_at: {snapshot.calculated_at:%Y-%m-%d %H:%M:%S}")
        self.stdout.write("future  name      spot    fut_px     spot_px    basis     basis_pct  date        source                    status")
        self.stdout.write("-" * 125)
        for row in rows:
            self.stdout.write(
                f"{row.future_code:<6}"
                f"{row.name:<10}"
                f"{row.spot_symbol:<8}"
                f"{str(row.future_close or '-'):>10}  "
                f"{str(row.spot_price or '-'):>9}  "
                f"{str(row.basis or '-'):>8}  "
                f"{(str(row.basis_pct) + '%') if row.basis_pct is not None else '-':>9}  "
                f"{str(row.trade_date or '-'):>10}  "
                f"{row.future_source:<24}"
                f"{row.status}"
            )
            if row.error:
                self.stdout.write(f"  error: {row.error}")
