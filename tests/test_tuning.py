from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from defiquant.config import load_config
from defiquant.data.fixtures import fixture_market
from defiquant.tuning import load_risk_tuning_candidates, rank_risk_candidates


def test_risk_tuning_candidates_rank_fixture_market() -> None:
    config = load_config(Path("configs/strategy.json"))
    market = fixture_market(config.universe_symbols)
    candidates = load_risk_tuning_candidates("configs/risk_tuning.json")

    ranked = rank_risk_candidates(config, market, candidates)

    assert len(ranked) == len(candidates)
    assert ranked[0]["eligible"] is True
    assert ranked[0]["name"]
    assert "min_cash_weight" in ranked[0]["risk"]
    assert ranked[0]["qualified_trade_days"] >= config.competition.min_total_trade_days


def test_tune_risk_cli_outputs_ranked_candidates(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "tune-risk", "--fixture", "--top", "2"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["market_source"] == "fixture"
    assert len(payload["top"]) == 2
    assert payload["top"][0]["eligible"] is True
