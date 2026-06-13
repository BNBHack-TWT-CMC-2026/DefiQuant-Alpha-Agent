from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from defiquant.models import PortfolioState


def load_eligible_symbols(path: str | Path) -> frozenset[str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    symbols = raw.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError(f"{path} must contain a string array at symbols")

    eligible_symbols: list[str] = []
    for symbol in symbols:
        if not isinstance(symbol, str):
            raise ValueError(f"{path} must contain a string array at symbols")
        eligible_symbols.append(symbol)
    return frozenset(eligible_symbols)


def find_ineligible_symbols(
    symbols: Iterable[str],
    eligible_symbols: frozenset[str],
) -> tuple[str, ...]:
    return tuple(symbol for symbol in symbols if symbol not in eligible_symbols)


def validate_universe(
    symbols: Iterable[str],
    eligible_symbols: frozenset[str],
    *,
    label: str = "universe",
) -> None:
    invalid = find_ineligible_symbols(symbols, eligible_symbols)
    if invalid:
        joined = ", ".join(invalid)
        raise ValueError(f"{label} contains tokens outside the competition allowlist: {joined}")


def in_scope_value(
    portfolio: PortfolioState,
    prices: dict[str, float],
    eligible_symbols: frozenset[str],
) -> float:
    return sum(
        units * prices.get(symbol, 0.0)
        for symbol, units in portfolio.positions.items()
        if symbol in eligible_symbols
    )


def has_minimum_in_scope_value(
    portfolio: PortfolioState,
    prices: dict[str, float],
    eligible_symbols: frozenset[str],
    minimum_usd: float,
) -> bool:
    return in_scope_value(portfolio, prices, eligible_symbols) >= minimum_usd


def raw_symbol_count(path: str | Path) -> int:
    raw: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    symbols = raw.get("symbols", [])
    return len(symbols) if isinstance(symbols, list) else 0
