from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Sequence

from defiquant.env import env_bool, env_value
from defiquant.execution.base import ExecutionAdapter
from defiquant.models import Order


class TwakCliExecutionAdapter(ExecutionAdapter):
    def __init__(
        self,
        dry_run: bool = True,
        cli_path: str | None = None,
        chain: str | None = None,
        stable_symbol: str | None = None,
        slippage_percent: float | None = None,
        quote_only: bool | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.cli_command = _command_prefix(cli_path or env_value("TWAK_CLI", "twak"))
        self.chain = chain or env_value("TWAK_CHAIN", "bnb")
        self.stable_symbol = stable_symbol or env_value("TWAK_STABLE_SYMBOL", "USDT")
        self.slippage_percent = slippage_percent or float(env_value("TWAK_SLIPPAGE_PERCENT", "1"))
        self.quote_only = (
            quote_only if quote_only is not None else env_bool("TWAK_QUOTE_ONLY", True)
        )

    def execute(self, orders: list[Order]) -> list[str]:
        commands = [self._swap_command(order) for order in orders]
        if self.dry_run:
            return [f"twak-dry-run:{_format_command(command)}" for command in commands]

        results: list[str] = []
        for command in commands:
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            results.append(completed.stdout.strip())
        return results

    def register_competition(self) -> str:
        command = [*self.cli_command, "compete", "register"]
        if self.dry_run:
            return f"twak-dry-run:{_format_command(command)}"

        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return completed.stdout.strip()

    def wallet_address(self) -> str:
        command = [*self.cli_command, "wallet", "address", "--chain", self.chain, "--json"]
        if self.dry_run:
            return f"twak-dry-run:{_format_command(command)}"

        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return completed.stdout.strip()

    def _swap_command(self, order: Order) -> list[str]:
        amount = order.source_amount if order.source_amount is not None else order.notional
        source = self.stable_symbol if order.side == "buy" else order.symbol
        target = order.symbol if order.side == "buy" else self.stable_symbol
        command = [
            *self.cli_command,
            "swap",
            _format_amount(amount),
            source,
            target,
            "--chain",
            self.chain,
            "--slippage",
            _format_amount(self.slippage_percent),
            "--json",
        ]
        if self.quote_only:
            command.append("--quote-only")
        return command


def _command_prefix(value: str) -> list[str]:
    return shlex.split(value, posix=False) or ["twak"]


def _format_amount(value: float) -> str:
    return f"{value:.12g}"


def _format_command(command: Sequence[str]) -> str:
    return json.dumps(list(command), separators=(",", ":"))
