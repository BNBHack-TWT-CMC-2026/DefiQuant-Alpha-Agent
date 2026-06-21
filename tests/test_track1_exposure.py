from __future__ import annotations

import json
import sys

import pytest

from defiquant.config import load_config
from defiquant.data.fixtures import fixture_market
from defiquant.track1_exposure import build_track1_exposure_sweep


def test_track1_exposure_sweep_recommends_mdd_and_multiplier() -> None:
    config = load_config("configs/strategy.tournament.json")
    market = fixture_market(config.universe_symbols)

    report = build_track1_exposure_sweep(
        config,
        market,
        exposure_multipliers=(1.0, 2.0, 4.0),
        mdd_targets=(0.10, 0.20, 0.30),
        target_windows=100,
        window_size_days=30,
        hard_drawdown=0.30,
    )

    assert report["methodology"]["research_only"] is True
    assert report["methodology"]["execution_leverage_supported"] is False
    assert report["parameters"]["target_windows"] == 100
    assert report["parameters"]["actual_windows"] <= 100
    assert report["recommended"]["target_mdd"] in {0.10, 0.20, 0.30}
    assert report["recommended"]["exposure_multiplier"] in {1.0, 2.0, 4.0}
    assert report["recommended"]["worst_max_drawdown"] <= 0.30
    assert len(report["summary"]) == 9
    assert report["recommended_window_results"]


def test_track1_exposure_sweep_rejects_empty_candidates() -> None:
    config = load_config("configs/strategy.json")
    market = fixture_market(config.universe_symbols)

    with pytest.raises(ValueError, match="exposure_multipliers"):
        build_track1_exposure_sweep(
            config,
            market,
            exposure_multipliers=(),
            mdd_targets=(0.20,),
        )


def test_track1_exposure_sweep_cli_outputs_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "track1-exposure-sweep",
            "--fixture",
            "--config",
            "configs/strategy.tournament.json",
            "--multipliers",
            "1,2",
            "--mdd-targets",
            "0.1,0.3",
            "--target-windows",
            "5",
            "--window-size-days",
            "30",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["parameters"]["actual_windows"] == 5
    assert payload["recommended"]["hard_cap_met"] is True
    assert len(payload["summary"]) == 4
