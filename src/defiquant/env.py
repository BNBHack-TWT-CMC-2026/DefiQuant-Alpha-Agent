from __future__ import annotations

import os
from pathlib import Path


def env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None:
        return value

    for directory in (Path.cwd(), *Path.cwd().parents):
        dotenv = directory / ".env"
        if not dotenv.is_file():
            continue
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            if key.strip() != name:
                continue
            return raw_value.strip().strip("\"'")
    return default


def env_bool(name: str, default: bool) -> bool:
    value = env_value(name)
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
