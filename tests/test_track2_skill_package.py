from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from defiquant.config import load_config

SKILL_DIR = Path("skills/cmc-defiquant")


def test_track2_skill_metadata_is_non_executing() -> None:
    metadata = json.loads((SKILL_DIR / "skill.json").read_text(encoding="utf-8"))

    assert metadata["track"] == "coinmarketcap-skill"
    assert metadata["execution"] == "disabled"
    assert metadata["entrypoint"]["args"][:2] == ["-m", "defiquant.cli"]
    assert "execute" not in metadata["entrypoint"]["args"]
    assert "register-track1" not in metadata["entrypoint"]["args"]
    assert metadata["safety"] == {
        "execution": "disabled",
        "wallet_access": "none",
        "twak_access": "none",
        "private_key_access": "none",
        "mutation": "read-only analysis",
    }


def test_track2_fixture_input_matches_strategy_config() -> None:
    payload = json.loads((SKILL_DIR / "examples/input.fixture.json").read_text(encoding="utf-8"))
    config = load_config("configs/strategy.json")

    assert payload["mode"] == "fixture"
    assert tuple(payload["universe"]) == config.universe_symbols
    assert payload["stable_symbol"] == config.strategy.stable_symbol
    assert payload["strategy"] == {
        "lookback_days": config.strategy.lookback_days,
        "trend_fast_days": config.strategy.trend_fast_days,
        "trend_slow_days": config.strategy.trend_slow_days,
        "top_n": config.strategy.top_n,
        "min_score": config.strategy.min_score,
        "trend_angle_days": config.strategy.trend_angle_days,
        "supertrend_period": config.strategy.supertrend_period,
        "supertrend_multiplier": config.strategy.supertrend_multiplier,
    }
    assert payload["risk"] == {
        "max_drawdown": config.risk.max_drawdown,
        "max_position_weight": config.risk.max_position_weight,
        "min_cash_weight": config.risk.min_cash_weight,
        "max_daily_turnover": config.risk.max_daily_turnover,
    }


def test_track2_fixture_output_matches_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "signal", "--fixture", "--config", "configs/strategy.json"],
    )

    main()

    expected = json.loads((SKILL_DIR / "examples/output.fixture.json").read_text(encoding="utf-8"))
    actual = json.loads(capsys.readouterr().out)
    assert actual == expected


def test_track2_docs_do_not_include_live_mutation_commands() -> None:
    combined = "\n".join(
        (SKILL_DIR / name).read_text(encoding="utf-8").lower()
        for name in ("README.md", "SKILL.md", "SUBMISSION.md")
    )

    forbidden = (
        " --live",
        "register-track1 --live",
        "twak swap",
        "private_key=",
        "wallet_password=",
    )
    assert not any(term in combined for term in forbidden)
