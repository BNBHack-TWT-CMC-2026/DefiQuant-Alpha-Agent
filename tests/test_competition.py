from __future__ import annotations

import json
from pathlib import Path

import pytest

from defiquant.competition import (
    find_ineligible_symbols,
    load_eligible_symbols,
    raw_symbol_count,
    validate_universe,
)
from defiquant.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_competition_allowlist_preserves_source_count() -> None:
    path = ROOT / "configs" / "eligible_tokens.json"
    eligible = load_eligible_symbols(path)

    assert raw_symbol_count(path) == 149
    assert len(eligible) == 148
    assert {"USDT", "CAKE", "TWT", "AAVE", "LINK", "PENDLE"}.issubset(eligible)


def test_strategy_universe_is_inside_competition_allowlist() -> None:
    config = load_config(ROOT / "configs" / "strategy.json")

    assert find_ineligible_symbols(config.universe_symbols, config.eligible_symbols) == ()


def test_invalid_universe_is_rejected() -> None:
    eligible = load_eligible_symbols(ROOT / "configs" / "eligible_tokens.json")

    with pytest.raises(ValueError, match="outside the competition allowlist"):
        validate_universe(("BNB", "USDT"), eligible)


def test_track1_competition_contract_is_recorded() -> None:
    raw = json.loads((ROOT / "configs" / "live_operations.json").read_text(encoding="utf-8"))
    contract = raw["competition_contract"]

    assert contract["address"] == "0x212c61b9b72c95d95bf29cf032f5e5635629aed5"
    assert contract["explorer_url"].endswith(contract["address"])
    assert contract["registration_command"] == "twak compete register"
