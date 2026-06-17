from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from defiquant.config import load_config
from defiquant.latest_evidence import build_latest_evidence_comparison


def test_build_latest_evidence_comparison_outputs_safe_config_rows() -> None:
    base_config = load_config("configs/strategy.json")
    configs = {
        "frontier-risk": load_config("configs/strategy.frontier-risk.json"),
        "frontier-return": load_config("configs/strategy.frontier-return.json"),
    }

    evidence = build_latest_evidence_comparison(
        base_config=base_config,
        configs=configs,
        quotes={
            "CAKE": _quote(change_1h=0.5, change_24h=3.0, change_7d=8.0),
            "LINK": _quote(change_1h=0.1, change_24h=1.0, change_7d=2.0),
            "USDT": _quote(change_1h=0.0, change_24h=0.0, change_7d=0.0),
        },
        token_addresses={"CAKE": "0xCake", "LINK": "0xLink", "USDT": "0xUsdt"},
        portfolio_cash=1000.0,
        generated_at=datetime(2026, 6, 17, tzinfo=UTC),
        twak_cli_path="twak",
    )

    assert evidence["generated_at_utc"] == "2026-06-17T00:00:00+00:00"
    assert evidence["config_count"] == 2
    assert evidence["highest_conviction_config_for_rehearsal"] in configs
    assert "not live approval" in evidence["ranking_method"]
    assert evidence["configs"][0]["signals"]
    assert evidence["configs"][0]["orders"]
    assert evidence["configs"][0]["twak_dry_run"]["commands"][0].startswith("twak-dry-run:")
    assert evidence["safety"] == {
        "live_transaction": False,
        "wallet_read": False,
        "funding": False,
        "registration": False,
        "quote_validation": False,
        "token_address_allowlist": True,
        "risk_manager_applied": True,
    }


def test_frontier_evidence_cli_uses_one_latest_quote_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    def fake_load_quotes(symbols: tuple[str, ...]) -> dict[str, dict[str, object]]:
        assert symbols == ("CAKE", "TWT", "AAVE", "LINK", "PENDLE", "USDT")
        return {
            "CAKE": _quote(change_1h=0.5, change_24h=3.0, change_7d=8.0),
            "LINK": _quote(change_1h=0.1, change_24h=1.0, change_7d=2.0),
            "USDT": _quote(change_1h=0.0, change_24h=0.0, change_7d=0.0),
        }

    monkeypatch.setattr("defiquant.cli.load_cmc_latest_quotes", fake_load_quotes)
    monkeypatch.setenv("TWAK_CLI", "twak")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "frontier-evidence",
            "--configs",
            "configs/strategy.frontier-risk.json,configs/strategy.frontier-return.json",
            "--portfolio-cash",
            "1000",
        ],
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["alpha_source"] == "coinmarketcap_latest_quotes"
    assert payload["purpose"] == "read_only_frontier_config_comparison"
    assert {row["config"] for row in payload["configs"]} == {
        "frontier-risk",
        "frontier-return",
    }
    assert payload["safety"]["live_transaction"] is False


def test_frontier_evidence_cli_rejects_incompatible_config_before_cmc_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from defiquant.cli import main

    raw = json.loads(Path("configs/strategy.frontier-risk.json").read_text(encoding="utf-8"))
    raw["competition"]["eligible_tokens_path"] = str(Path("configs/eligible_tokens.json").resolve())
    raw["universe"]["symbols"] = ["CAKE", "USDT"]
    mismatched_path = tmp_path / "strategy.mismatched.json"
    mismatched_path.write_text(json.dumps(raw), encoding="utf-8")

    def fail_load_quotes(symbols: tuple[str, ...]) -> dict[str, dict[str, object]]:
        raise AssertionError(f"CMC should not be called for incompatible configs: {symbols}")

    monkeypatch.setattr("defiquant.cli.load_cmc_latest_quotes", fail_load_quotes)
    monkeypatch.setattr(
        sys,
        "argv",
        ["defiquant", "frontier-evidence", "--configs", str(mismatched_path)],
    )

    with pytest.raises(ValueError, match="universe differs"):
        main()


def _quote(*, change_1h: float, change_24h: float, change_7d: float) -> dict[str, object]:
    return {
        "price": 1.0,
        "volume_24h": 10_000_000,
        "market_cap": 100_000_000,
        "percent_change_1h": change_1h,
        "percent_change_24h": change_24h,
        "percent_change_7d": change_7d,
    }
