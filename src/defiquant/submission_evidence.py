from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def write_submission_evidence_bundle(
    output_root: str | Path,
    payloads: dict[str, dict[str, Any]],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or datetime.now(UTC)
    bundle_dir = _create_bundle_dir(Path(output_root), timestamp)

    files: dict[str, str] = {}
    for name, payload in payloads.items():
        filename = f"{name}.json"
        path = bundle_dir / filename
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        files[name] = str(path)

    manifest = {
        "generated_at_utc": timestamp.astimezone(UTC).isoformat(),
        "bundle_dir": str(bundle_dir),
        "files": files,
        "safety": {
            "live_transaction": False,
            "wallet_read": False,
            "funding": False,
            "registration": False,
            "paid_x402": False,
        },
        "manual_gates_not_run": [
            "TWAK live swap",
            "TWAK wallet funding",
            "Track 1 live registration",
            "BNB Agent SDK live registration",
            "DoraHacks external form submission",
            "paid x402 request",
        ],
    }
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["files"] = {"manifest": str(manifest_path), **files}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _timestamp_slug(timestamp: datetime) -> str:
    value = timestamp.astimezone(UTC)
    return value.strftime("%Y%m%dT%H%M%SZ")


def _create_bundle_dir(output_root: Path, timestamp: datetime) -> Path:
    slug = _timestamp_slug(timestamp)
    output_root.mkdir(parents=True, exist_ok=True)
    for index in range(1, 1000):
        suffix = "" if index == 1 else f"-{index}"
        candidate = output_root / f"{slug}{suffix}"
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise RuntimeError(f"could not allocate submission evidence directory under {output_root}")
