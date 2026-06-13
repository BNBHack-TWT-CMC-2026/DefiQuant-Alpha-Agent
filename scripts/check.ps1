$ErrorActionPreference = "Stop"
$env:UV_CACHE_DIR = Join-Path (Split-Path -Parent $PSScriptRoot) ".uv-cache"

uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
