from __future__ import annotations

import json
import os
import subprocess

from defiquant.execution.base import ExecutionAdapter
from defiquant.models import Order


class TwakCliExecutionAdapter(ExecutionAdapter):
    def __init__(self, dry_run: bool = True, cli_path: str | None = None) -> None:
        self.dry_run = dry_run
        self.cli_path = cli_path or os.getenv("TWAK_CLI", "twak")

    def execute(self, orders: list[Order]) -> list[str]:
        payload = [
            {
                "symbol": order.symbol,
                "side": order.side,
                "notional": order.notional,
                "targetWeight": order.target_weight,
                "reason": order.reason,
            }
            for order in orders
        ]
        if self.dry_run:
            return [f"twak-dry-run:{json.dumps(payload, sort_keys=True)}"]

        command = [self.cli_path, "trade", "--json", json.dumps(payload)]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return [completed.stdout.strip()]
