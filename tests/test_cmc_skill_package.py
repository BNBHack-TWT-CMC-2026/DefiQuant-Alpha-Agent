from __future__ import annotations

import json
from pathlib import Path

SKILL_DIR = Path("skills/cmc-defiquant")


def test_cmc_skill_manifest_points_to_examples() -> None:
    manifest = json.loads((SKILL_DIR / "skill.json").read_text(encoding="utf-8"))

    assert manifest["name"] == "defiquant-alpha-pool-risk"
    assert manifest["track"] == "coinmarketcap-skill"
    assert manifest["execution"] == "disabled"
    assert manifest["entrypoint"]["args"][:3] == ["-m", "defiquant.cli", "signal"]
    assert manifest["examples"] == {
        "input": "examples/input.fixture.json",
        "output": "examples/output.fixture.json",
    }
    assert manifest["safety"] == {
        "execution": "disabled",
        "wallet_access": "none",
        "twak_access": "none",
        "private_key_access": "none",
        "mutation": "read-only analysis",
    }


def test_cmc_skill_fixture_output_shape() -> None:
    output = json.loads((SKILL_DIR / "examples" / "output.fixture.json").read_text())

    assert len(output) == 4
    assert abs(sum(item["target_weight"] for item in output) - 1.0) < 1e-12
    assert output[-1] == {
        "symbol": "USDT",
        "target_weight": 0.79,
        "score": 0.0,
        "reasons": ["reserve=min_cash"],
    }
    for item in output:
        assert set(item) == {"symbol", "target_weight", "score", "reasons"}
        assert isinstance(item["reasons"], list)


def test_cmc_skill_fixture_output_uses_alpha_pool_reasons() -> None:
    output = json.loads((SKILL_DIR / "examples" / "output.fixture.json").read_text())
    non_stable = [item for item in output if item["symbol"] != "USDT"]
    expected_keys = {
        "medium_momentum",
        "trend_strength",
        "volume_impulse",
        "liquidity_depth",
        "short_reversal_guard",
        "trend_angle",
        "supertrend_alignment",
        "volatility",
    }

    assert non_stable
    for item in non_stable:
        reason_keys = {reason.split("=", maxsplit=1)[0] for reason in item["reasons"]}
        assert reason_keys == expected_keys


def test_cmc_skill_package_has_no_execution_instructions() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in [
            SKILL_DIR / "README.md",
            SKILL_DIR / "SKILL.md",
            SKILL_DIR / "SUBMISSION.md",
            SKILL_DIR / "skill.json",
        ]
    )

    forbidden = [
        "wallet_password",
        "register-track1 --live",
        "execute --live",
        "twak swap",
    ]
    for term in forbidden:
        assert term not in combined
