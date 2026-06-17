from __future__ import annotations

import json
from dataclasses import dataclass
from math import log10
from pathlib import Path
from typing import Any

from defiquant.config import StrategyConfig
from defiquant.models import Signal

STABLE_SYMBOLS = frozenset(
    {
        "USDT",
        "USDC",
        "DAI",
        "TUSD",
        "FDUSD",
        "USDD",
        "USD1",
        "USDE",
        "USDF",
        "FRAX",
        "LISUSD",
        "DUSD",
        "EURI",
        "XUSD",
    }
)


@dataclass(frozen=True)
class AlphaMode:
    name: str
    max_position_weight: float
    min_cash_weight: float
    max_daily_turnover: float
    min_score: float
    top_n: int
    activation: dict[str, object]


def load_alpha_modes(path: str | Path) -> dict[str, AlphaMode]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    modes = raw.get("modes")
    if not isinstance(modes, list) or not modes:
        raise ValueError("alpha mode config must include a non-empty modes list")
    parsed = [_parse_mode(mode) for mode in modes]
    return {mode.name: mode for mode in parsed}


def load_token_addresses(path: str | Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("token address file must be a JSON object")
    return {
        str(symbol).upper(): address
        for symbol, address in payload.items()
        if isinstance(address, str) and address
    }


def scan_alpha_quotes(
    quotes: dict[str, dict[str, Any]],
    *,
    token_addresses: dict[str, str],
    top: int,
    modes: dict[str, AlphaMode],
) -> dict[str, Any]:
    rows = [
        _score_quote(symbol, quote, token_addresses)
        for symbol, quote in quotes.items()
        if symbol.upper() not in STABLE_SYMBOLS
    ]
    ranked = sorted(rows, key=lambda item: item["alpha_score"], reverse=True)
    tradable = [row for row in ranked if row["tradable"]]
    recommended_mode = _recommend_mode(tradable, ranked, modes)
    return {
        "recommended_mode": recommended_mode,
        "market_breadth": _market_breadth(ranked),
        "tradable_count": len(tradable),
        "scanned_count": len(ranked),
        "top_tradable": tradable[:top],
        "top_discovery": ranked[:top],
    }


def latest_quote_signals(
    quotes: dict[str, dict[str, Any]],
    *,
    token_addresses: dict[str, str],
    config: StrategyConfig,
) -> list[Signal]:
    rows = [
        _score_quote_for_strategy(symbol, quote, token_addresses, config)
        for symbol, quote in quotes.items()
        if symbol.upper() not in STABLE_SYMBOLS and symbol.upper() in token_addresses
    ]
    ranked = sorted(rows, key=lambda item: item["alpha_score"], reverse=True)
    selected = [
        row
        for row in ranked
        if float(row["alpha_score"]) > 0 and float(row["alpha_score"]) >= config.min_score
    ][: config.top_n]
    if not selected:
        return [
            Signal(
                config.stable_symbol,
                1.0,
                0.0,
                ("risk_off=no_positive_latest_quote_scores",),
            )
        ]

    score_floor = 0.001
    total_score = sum(max(score_floor, float(row["alpha_score"])) for row in selected)
    return [
        Signal(
            symbol=str(row["symbol"]),
            target_weight=max(score_floor, float(row["alpha_score"])) / total_score,
            score=float(row["alpha_score"]),
            reasons=tuple([*row["reasons"], f"latest_quote_alpha={row['alpha_score']:.4f}"]),
        )
        for row in selected
    ]


def latest_quote_prices(
    quotes: dict[str, dict[str, Any]],
    *,
    stable_symbol: str,
) -> dict[str, float]:
    prices = {
        symbol.upper(): float(quote["price"])
        for symbol, quote in quotes.items()
        if quote.get("price") is not None
    }
    prices.setdefault(stable_symbol, 1.0)
    return prices


def _parse_mode(raw: object) -> AlphaMode:
    if not isinstance(raw, dict):
        raise ValueError("alpha mode must be an object")
    mode = {str(key): value for key, value in raw.items()}
    name = mode.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("alpha mode requires a name")
    activation = mode.get("activation", {})
    if not isinstance(activation, dict):
        raise ValueError(f"alpha mode {name} activation must be an object")
    parsed_activation = {str(key): value for key, value in activation.items()}
    return AlphaMode(
        name=name,
        max_position_weight=_required_float(mode, "max_position_weight"),
        min_cash_weight=_required_float(mode, "min_cash_weight"),
        max_daily_turnover=_required_float(mode, "max_daily_turnover"),
        min_score=_required_float(mode, "min_score"),
        top_n=_required_int(mode, "top_n"),
        activation=parsed_activation,
    )


def _score_quote(
    symbol: str,
    quote: dict[str, Any],
    token_addresses: dict[str, str],
) -> dict[str, Any]:
    change_1h = _number(quote.get("percent_change_1h"))
    change_24h = _number(quote.get("percent_change_24h"))
    change_7d = _number(quote.get("percent_change_7d"))
    volume_24h = max(0.0, _number(quote.get("volume_24h")))
    market_cap = max(0.0, _number(quote.get("market_cap")))
    liquidity_bonus = min(6.0, log10(volume_24h + 1.0) * 0.55)
    depth_bonus = min(2.0, log10(market_cap + 1.0) * 0.12) if market_cap > 0 else 0.0
    downside_penalty = (max(0.0, -change_24h) * 0.35) + (max(0.0, -change_7d) * 0.12)
    blowoff_penalty = max(0.0, change_1h - 8.0) * 0.25
    alpha_score = (
        (0.45 * change_1h)
        + (0.35 * change_24h)
        + (0.20 * change_7d)
        + liquidity_bonus
        + depth_bonus
        - downside_penalty
        - blowoff_penalty
    )
    upper_symbol = symbol.upper()
    return {
        "symbol": upper_symbol,
        "alpha_score": round(alpha_score, 8),
        "tradable": upper_symbol in token_addresses,
        "token_address": token_addresses.get(upper_symbol, ""),
        "price": quote.get("price"),
        "volume_24h": quote.get("volume_24h"),
        "market_cap": quote.get("market_cap"),
        "percent_change_1h": quote.get("percent_change_1h"),
        "percent_change_24h": quote.get("percent_change_24h"),
        "percent_change_7d": quote.get("percent_change_7d"),
        "reasons": [
            f"1h={change_1h:.4f}",
            f"24h={change_24h:.4f}",
            f"7d={change_7d:.4f}",
            f"liquidity_bonus={liquidity_bonus:.4f}",
            f"downside_penalty={downside_penalty:.4f}",
        ],
    }


def _score_quote_for_strategy(
    symbol: str,
    quote: dict[str, Any],
    token_addresses: dict[str, str],
    config: StrategyConfig,
) -> dict[str, Any]:
    change_1h = _number(quote.get("percent_change_1h")) / 100.0
    change_24h = _number(quote.get("percent_change_24h")) / 100.0
    change_7d = _number(quote.get("percent_change_7d")) / 100.0
    volume_24h = max(0.0, _number(quote.get("volume_24h")))
    market_cap = max(0.0, _number(quote.get("market_cap")))
    medium_momentum = change_7d
    trend_strength = change_24h
    volume_impulse = min(1.0, log10(volume_24h + 1.0) / 10.0)
    liquidity_depth = min(1.0, log10(max(volume_24h, market_cap) + 1.0) / 12.0)
    short_reversal_guard = _latest_reversal_guard(change_1h)
    volatility_proxy = (abs(change_1h) + abs(change_24h) + (abs(change_7d) / 7.0)) / 10.0
    downside_penalty = (max(0.0, -change_24h) * 0.70) + (max(0.0, -change_7d) * 0.30)
    weights = config.alpha_weights
    alpha_score = (
        (weights.medium_momentum * medium_momentum)
        + (weights.trend_strength * trend_strength)
        + (weights.volume_impulse * volume_impulse)
        + (weights.liquidity_depth * liquidity_depth)
        + (weights.short_reversal_guard * short_reversal_guard)
        - (weights.volatility_penalty * volatility_proxy)
        - downside_penalty
    )
    upper_symbol = symbol.upper()
    return {
        "symbol": upper_symbol,
        "alpha_score": round(alpha_score, 8),
        "tradable": upper_symbol in token_addresses,
        "token_address": token_addresses.get(upper_symbol, ""),
        "price": quote.get("price"),
        "volume_24h": quote.get("volume_24h"),
        "market_cap": quote.get("market_cap"),
        "percent_change_1h": quote.get("percent_change_1h"),
        "percent_change_24h": quote.get("percent_change_24h"),
        "percent_change_7d": quote.get("percent_change_7d"),
        "reasons": [
            f"medium_momentum={medium_momentum:.4f}",
            f"trend_strength={trend_strength:.4f}",
            f"volume_impulse={volume_impulse:.4f}",
            f"liquidity_depth={liquidity_depth:.4f}",
            f"short_reversal_guard={short_reversal_guard:.4f}",
            f"volatility_proxy={volatility_proxy:.4f}",
            f"downside_penalty={downside_penalty:.4f}",
        ],
    }


def _latest_reversal_guard(one_hour_return: float) -> float:
    pullback_bonus = min(0.04, max(0.0, -one_hour_return)) * 0.50
    blowoff_penalty = max(0.0, one_hour_return - 0.04)
    crash_penalty = max(0.0, -one_hour_return - 0.08) * 2.00
    return pullback_bonus - blowoff_penalty - crash_penalty


def _recommend_mode(
    tradable: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    modes: dict[str, AlphaMode],
) -> dict[str, Any]:
    top_score = float(tradable[0]["alpha_score"]) if tradable else -999.0
    breadth = _market_breadth(ranked)
    if top_score >= _activation_value(
        modes, "aggressive", "min_top_score", 7.0
    ) and breadth >= _activation_value(modes, "aggressive", "min_market_breadth", 0.45):
        mode_name = "aggressive"
    elif top_score <= _activation_value(
        modes, "defensive", "max_top_score", 1.0
    ) or breadth <= _activation_value(modes, "defensive", "max_market_breadth", 0.30):
        mode_name = "defensive"
    else:
        mode_name = "balanced"

    mode = modes.get(mode_name) or next(iter(modes.values()))
    return {
        "mode": mode.name,
        "top_score": round(top_score, 8),
        "max_position_weight": mode.max_position_weight,
        "min_cash_weight": mode.min_cash_weight,
        "max_daily_turnover": mode.max_daily_turnover,
        "min_score": mode.min_score,
        "top_n": mode.top_n,
    }


def _activation_value(
    modes: dict[str, AlphaMode],
    mode_name: str,
    key: str,
    default: float,
) -> float:
    mode = modes.get(mode_name)
    if mode is None:
        return default
    value = mode.activation.get(key, default)
    return _required_number(value, key)


def _market_breadth(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    positive = sum(1 for row in rows if float(row["alpha_score"]) > 0)
    return round(positive / len(rows), 8)


def _number(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    return float(value)


def _required_float(raw: dict[str, object], key: str) -> float:
    return _required_number(raw.get(key), key)


def _required_int(raw: dict[str, object], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError(f"alpha mode requires numeric {key}")
    return int(value)


def _required_number(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"alpha mode requires numeric {key}")
    return float(value)
