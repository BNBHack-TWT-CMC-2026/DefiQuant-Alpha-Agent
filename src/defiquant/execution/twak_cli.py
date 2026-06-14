from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from defiquant.env import env_bool, env_value
from defiquant.execution.base import ExecutionAdapter
from defiquant.models import Order


@dataclass(frozen=True)
class TwakQuoteValidation:
    symbol: str
    side: str
    command: list[str]
    quote: dict[str, Any]


class TwakCliExecutionAdapter(ExecutionAdapter):
    def __init__(
        self,
        dry_run: bool = True,
        cli_path: str | None = None,
        chain: str | None = None,
        stable_symbol: str | None = None,
        slippage_percent: float | None = None,
        quote_only: bool | None = None,
        token_addresses: dict[str, str] | None = None,
        token_addresses_path: str | None = None,
    ) -> None:
        self.dry_run = dry_run
        self.cli_command = _command_prefix(cli_path or env_value("TWAK_CLI", "twak"))
        self.chain = chain or env_value("TWAK_CHAIN", "bsc")
        self.stable_symbol = stable_symbol or env_value("TWAK_STABLE_SYMBOL", "USDT")
        self.slippage_percent = slippage_percent or float(env_value("TWAK_SLIPPAGE_PERCENT", "1"))
        self.quote_only = (
            quote_only if quote_only is not None else env_bool("TWAK_QUOTE_ONLY", True)
        )
        self.token_addresses = _normalize_addresses(
            token_addresses
            if token_addresses is not None
            else _load_token_addresses(self.chain, token_addresses_path)
        )

    def execute(self, orders: list[Order]) -> list[str]:
        commands = [self._swap_command(order) for order in orders]
        if self.dry_run:
            return [f"twak-dry-run:{_format_command(command)}" for command in commands]

        results: list[str] = []
        for command in commands:
            completed = _run_command(command)
            results.append(completed.stdout.strip())
        return results

    def validate_quotes(self, orders: list[Order]) -> list[TwakQuoteValidation]:
        results: list[TwakQuoteValidation] = []
        for order in orders:
            command = self._swap_command(order, quote_only=True)
            completed = _run_command(command)
            quote = _parse_quote_response(completed.stdout)
            results.append(TwakQuoteValidation(order.symbol, order.side, command, quote))
        return results

    def register_competition(self) -> str:
        command = [*self.cli_command, "compete", "register"]
        if self.dry_run:
            return f"twak-dry-run:{_format_command(command)}"

        completed = _run_command(command)
        return completed.stdout.strip()

    def auth_status(self) -> object:
        command = [*self.cli_command, "auth", "status", "--json"]
        if self.dry_run:
            return f"twak-dry-run:{_format_command(command)}"

        completed = _run_command(command)
        return json.loads(completed.stdout)

    def wallet_address(self) -> str:
        command = [*self.cli_command, "wallet", "address", "--chain", self.chain, "--json"]
        if self.dry_run:
            return f"twak-dry-run:{_format_command(command)}"

        completed = _run_command(command)
        return completed.stdout.strip()

    def wallet_portfolio_preview(self) -> str:
        command = [*self.cli_command, "wallet", "portfolio", "--chains", self.chain, "--json"]
        return f"twak-dry-run:{_format_command(command)}"

    def wallet_portfolio(self) -> object:
        command = [*self.cli_command, "wallet", "portfolio", "--chains", self.chain, "--json"]
        completed = _run_command(command)
        return json.loads(completed.stdout)

    def _swap_command(self, order: Order, quote_only: bool | None = None) -> list[str]:
        amount = order.source_amount if order.source_amount is not None else order.notional
        source_symbol = self.stable_symbol if order.side == "buy" else order.symbol
        target_symbol = order.symbol if order.side == "buy" else self.stable_symbol
        source = self._token_ref(source_symbol)
        target = self._token_ref(target_symbol)
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
        effective_quote_only = self.quote_only if quote_only is None else quote_only
        if effective_quote_only:
            command.append("--quote-only")
        return command

    def _token_ref(self, symbol: str) -> str:
        token_ref = self.token_addresses.get(symbol.upper())
        if token_ref:
            return token_ref
        if self.chain == "bsc":
            raise ValueError(f"Missing BSC token address for {symbol}")
        return symbol


def _command_prefix(value: str) -> list[str]:
    return shlex.split(value, posix=False) or ["twak"]


def _format_amount(value: float) -> str:
    return f"{value:.12g}"


def _format_command(command: Sequence[str]) -> str:
    return json.dumps(list(command), separators=(",", ":"))


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(_resolve_command(command), check=True, capture_output=True, text=True)


def _resolve_command(command: list[str]) -> list[str]:
    executable = shutil.which(command[0])
    if executable is None:
        return command
    return [executable, *command[1:]]


def _parse_quote_response(stdout: str) -> dict[str, Any]:
    if not stdout.strip():
        raise RuntimeError("TWAK quote returned empty output")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("TWAK quote returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("TWAK quote JSON must be an object")
    error = payload.get("error") or payload.get("errorCode")
    if error:
        raise RuntimeError(f"TWAK quote failed: {error}")
    return payload


def _load_token_addresses(chain: str, configured_path: str | None) -> dict[str, str]:
    path_value = configured_path or env_value(
        "TWAK_TOKEN_ADDRESSES_PATH",
        f"configs/token_addresses.{chain}.json",
    )
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Token address file must be a JSON object: {path}")
    return _normalize_addresses(payload)


def _normalize_addresses(payload: dict[str, Any]) -> dict[str, str]:
    addresses: dict[str, str] = {}
    for symbol, address in payload.items():
        if not isinstance(symbol, str) or not isinstance(address, str):
            raise ValueError("Token address mappings must be string to string")
        addresses[symbol.upper()] = address
    return addresses
