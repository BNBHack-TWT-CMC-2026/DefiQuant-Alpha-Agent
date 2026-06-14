from __future__ import annotations

from collections.abc import Collection
from typing import Any

from defiquant.models import PortfolioState


def parse_twak_portfolio(
    payload: Any,
    *,
    chain: str,
    stable_symbol: str,
    prices: dict[str, float],
    allowed_symbols: Collection[str],
) -> PortfolioState:
    chain_key = chain.lower()
    stable_key = stable_symbol.upper()
    allowed = {symbol.upper() for symbol in allowed_symbols}
    entries = _portfolio_entries(payload)

    cash = 0.0
    positions: dict[str, float] = {}
    for entry in entries:
        if _entry_chain(entry).lower() != chain_key:
            continue

        symbol = _entry_symbol(entry)
        if symbol is None:
            continue
        if symbol not in allowed and symbol != stable_key:
            continue

        balance = _entry_number(entry, ("balance", "amount", "quantity", "available"))
        if balance is None:
            raise ValueError(f"TWAK portfolio token {symbol} is missing balance")
        if balance <= 0:
            continue

        if symbol == stable_key:
            usd_value = _entry_number(entry, ("usdValue", "usd_value", "valueUsd", "value_usd"))
            cash += usd_value if usd_value is not None and usd_value > 0 else balance
            continue

        price = prices.get(symbol)
        if price is None or price <= 0:
            raise ValueError(f"Missing positive price for wallet token {symbol}")
        positions[symbol] = positions.get(symbol, 0.0) + balance

    portfolio = PortfolioState(cash=cash, positions=positions)
    portfolio.high_watermark = portfolio.value(prices)
    return portfolio


def _portfolio_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    if isinstance(payload, dict):
        for key in ("tokens", "assets", "balances", "portfolio"):
            entries = payload.get(key)
            if isinstance(entries, list):
                return [entry for entry in entries if isinstance(entry, dict)]
    raise ValueError("TWAK portfolio payload must be a list or contain a token list")


def _entry_chain(entry: dict[str, Any]) -> str:
    value = entry.get("chain") or entry.get("chainId") or entry.get("network") or ""
    return str(value)


def _entry_symbol(entry: dict[str, Any]) -> str | None:
    value = entry.get("symbol") or entry.get("tokenSymbol")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper()


def _entry_number(entry: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = entry.get(key)
        parsed = _optional_float(value)
        if parsed is not None:
            return parsed
    return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not stripped:
            return None
        return float(stripped)
    return None
