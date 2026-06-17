from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from defiquant.submission_evidence import write_submission_evidence_bundle


def test_write_submission_evidence_bundle_creates_manifest(tmp_path: Path) -> None:
    manifest = write_submission_evidence_bundle(
        tmp_path,
        {
            "research-report": {"ok": True},
            "alpha-evidence": {"ok": True},
        },
        generated_at=datetime(2026, 6, 17, 1, 2, 3, tzinfo=UTC),
    )

    bundle_dir = tmp_path / "20260617T010203Z"
    assert manifest["bundle_dir"] == str(bundle_dir)
    assert Path(manifest["files"]["manifest"]).is_file()
    assert Path(manifest["files"]["research-report"]).is_file()
    assert Path(manifest["files"]["alpha-evidence"]).is_file()
    assert manifest["safety"]["live_transaction"] is False
    assert "paid x402 request" in manifest["manual_gates_not_run"]


def test_write_submission_evidence_bundle_handles_timestamp_collision(tmp_path: Path) -> None:
    timestamp = datetime(2026, 6, 17, 1, 2, 3, tzinfo=UTC)

    first = write_submission_evidence_bundle(tmp_path, {"first": {}}, generated_at=timestamp)
    second = write_submission_evidence_bundle(tmp_path, {"second": {}}, generated_at=timestamp)

    assert first["bundle_dir"].endswith("20260617T010203Z")
    assert second["bundle_dir"].endswith("20260617T010203Z-2")
    assert first["bundle_dir"] != second["bundle_dir"]


def test_submission_evidence_cli_writes_safe_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from defiquant.cli import main

    def fake_load_quotes(symbols: tuple[str, ...]) -> dict[str, dict[str, object]]:
        assert symbols == ("CAKE", "TWT", "AAVE", "LINK", "PENDLE", "USDT")
        return {
            "CAKE": _quote(change_1h=2.0, change_24h=8.0, change_7d=12.0),
            "LINK": _quote(change_1h=0.2, change_24h=2.0, change_7d=5.0),
            "USDT": _quote(change_1h=0.0, change_24h=0.0, change_7d=0.0),
        }

    monkeypatch.setattr("defiquant.cli.load_cmc_latest_quotes", fake_load_quotes)
    monkeypatch.setenv("TWAK_CLI", "twak")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "defiquant",
            "submission-evidence",
            "--fixture",
            "--windows",
            "30",
            "--output-dir",
            str(tmp_path),
            "--agent-url",
            "https://agent.example",
            "--wallet-address",
            "0xAgent",
        ],
    )

    main()

    manifest = json.loads(capsys.readouterr().out)
    assert manifest["safety"]["live_transaction"] is False
    assert set(manifest["files"]) == {
        "manifest",
        "research-report",
        "alpha-evidence",
        "cmc-context-packet",
        "agent-profile",
    }
    profile = json.loads(Path(manifest["files"]["agent-profile"]).read_text(encoding="utf-8"))
    assert profile["wallet_address"] == "0xAgent"
    assert any(endpoint["endpoint"].endswith("/health") for endpoint in profile["endpoints"])


def _quote(*, change_1h: float, change_24h: float, change_7d: float) -> dict[str, object]:
    return {
        "price": 1.0,
        "volume_24h": 10_000_000,
        "market_cap": 100_000_000,
        "percent_change_1h": change_1h,
        "percent_change_24h": change_24h,
        "percent_change_7d": change_7d,
    }
