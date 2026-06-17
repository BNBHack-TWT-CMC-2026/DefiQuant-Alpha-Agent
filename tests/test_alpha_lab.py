from __future__ import annotations

import json
import sys

import pytest

from defiquant.alpha_lab import build_alpha_lab_report, generate_alpha_weight_candidates
from defiquant.config import AlphaWeights, load_config
from defiquant.data.fixtures import fixture_market


def test_strategy_config_uses_default_alpha_weights() -> None:
    config = load_config("configs/strategy.json")

    assert config.strategy.alpha_weights == AlphaWeights()


def test_frontier_strategy_configs_load_alpha_weights() -> None:
    risk_config = load_config("configs/strategy.frontier-risk.json")
    return_config = load_config("configs/strategy.frontier-return.json")
    lowdrawdown_config = load_config("configs/strategy.frontier-lowdrawdown.json")

    assert risk_config.strategy.alpha_weights.medium_momentum == 0.2
    assert risk_config.strategy.alpha_weights.volatility_penalty == 1.4
    assert return_config.strategy.alpha_weights.medium_momentum == 0.8
    assert return_config.strategy.alpha_weights.volatility_penalty == 0.8
    assert lowdrawdown_config.strategy.alpha_weights.trend_strength == 0.15
    assert lowdrawdown_config.strategy.alpha_weights.volatility_penalty == 1.7


def test_alpha_lab_generates_at_least_1000_deterministic_candidates() -> None:
    candidates = generate_alpha_weight_candidates(1000)

    assert len(candidates) == 1000
    assert candidates[0].name == "baseline"
    assert candidates[0].weights == AlphaWeights()
    assert len({candidate.name for candidate in candidates}) == 1000
    assert {candidate.weights.medium_momentum for candidate in candidates} == {
        0.20,
        0.35,
        0.50,
        0.65,
        0.80,
    }
    assert {
        0.80,
        1.10,
        1.40,
        1.70,
        2.00,
    }.issubset({candidate.weights.volatility_penalty for candidate in candidates})


def test_alpha_lab_report_ranks_candidates_on_fixture() -> None:
    config = load_config("configs/strategy.defensive.json")
    market = fixture_market(config.universe_symbols)

    report = build_alpha_lab_report(
        config,
        {30: market, 60: market},
        max_candidates=25,
        top=5,
    )

    assert report["candidate_count"] == 25
    assert report["recommended_candidate"]
    assert report["baseline"]["candidate"] == "baseline"
    assert set(report["frontiers"]) == {
        "best_risk_adjusted",
        "best_minimum_return",
        "best_average_return",
        "lowest_drawdown",
    }
    assert "average_total_return" in report["frontiers"]["best_average_return"]
    assert len(report["top_candidates"]) == 5
    assert all("alpha_weights" in item for item in report["top_candidates"])


def test_alpha_lab_cli_outputs_fixture_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "alpha-lab",
            "--fixture",
            "--windows",
            "30,60",
            "--max-candidates",
            "25",
            "--top",
            "3",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["candidate_count"] == 25
    assert "frontiers" in payload
    assert len(payload["top_candidates"]) == 3
