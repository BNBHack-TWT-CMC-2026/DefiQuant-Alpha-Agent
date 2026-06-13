from __future__ import annotations

from defiquant.execution.base import ExecutionAdapter
from defiquant.models import Order


class PaperExecutionAdapter(ExecutionAdapter):
    def execute(self, orders: list[Order]) -> list[str]:
        return [
            (
                f"paper:{order.side}:{order.symbol}:notional={order.notional:.2f}:"
                f"target={order.target_weight:.4f}"
            )
            for order in orders
        ]
