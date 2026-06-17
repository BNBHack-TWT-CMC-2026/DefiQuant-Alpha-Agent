from __future__ import annotations

import json
import sys
from dataclasses import replace

import pytest

from defiquant.config import load_config
from defiquant.data.fixtures import fixture_market
from defiquant.research import build_research_report, validate_research_config_compatibility


def test_build_research_report_ranks_multiple_configs() -> None:
    configs = {
        "aggressive": load_config("configs/strategy.aggressive.json"),
        "defensive": load_config("configs/strategy.defensive.json"),
    }
    market = fixture_market(configs["aggressive"].universe_symbols)

    report = build_research_report(configs, {30: market, 60: market})

    assert report["windows"] == [30, 60]
    assert report["recommended_config"] in {"aggressive", "defensive"}
    assert len(report["summary"]) == 2
    assert len(report["window_results"]) == 4
    assert all("risk_adjusted_score" in row for row in report["window_results"])
    assert all("eligible_windows" in row for row in report["summary"])


def test_research_config_compatibility_rejects_mismatched_universe() -> None:
    config = load_config("configs/strategy.aggressive.json")
    mismatched = replace(config, universe_symbols=("CAKE", "USDT"))

    with pytest.raises(ValueError, match="universe differs"):
        validate_research_config_compatibility(
            {
                "aggressive": config,
                "custom": mismatched,
            }
        )


def test_research_report_cli_outputs_fixture_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "research-report",
            "--fixture",
            "--windows",
            "30,60",
            "--configs",
            "configs/strategy.aggressive.json,configs/strategy.defensive.json",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["windows"] == [30, 60]
    assert payload["recommended_config"] in {"aggressive", "defensive"}
    assert len(payload["summary"]) == 2
    assert len(payload["window_results"]) == 4


def test_research_report_cli_defaults_include_frontier_configs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "research-report", "--fixture", "--windows", "30"],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    configs = {row["config"] for row in payload["summary"]}
    assert {
        "aggressive",
        "balanced",
        "defensive",
        "frontier-risk",
        "frontier-return",
        "frontier-lowdrawdown",
    }.issubset(configs)
