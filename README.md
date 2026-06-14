# defiQuant

defiQuant is a single strategy engine with two thin adapters:

- Track 1: CMC-driven strategy plus wallet signing and BSC execution through TWAK/BNB tooling.
- Track 2: the same strategy logic packaged as a CMC Skill through the DoraHacks Add option.

The project starts deliberately small: deterministic backtests, strict drawdown controls, and dry-run execution first. Live trading should only be enabled after testnet rehearsal.

## Current Status

The checked-in [context_info.md](context_info.md) captures the hackathon page text used for implementation. Although the page copy says "Pick one", DoraHacks supports adding the second track through the Add option, so this repo targets both tracks from the same strategy core.

## Quick Start

Run the fixture backtest:

```powershell
uv run pytest
uv run defiquant backtest --fixture --config configs/strategy.json
```

Generate the latest target weights from fixture data:

```powershell
uv run defiquant signal --fixture --config configs/strategy.json
```

Dry-run a TWAK execution plan:

```powershell
uv run defiquant execute --fixture --config configs/strategy.json --adapter twak --dry-run
```

Run the full local check:

```powershell
.\scripts\check.ps1
```

## Agent And CLI Setup

- Local Codex CLI notes/settings can live under `.codex/`, but that directory is intentionally ignored by git.
- The current local agent guide is `.codex/AGENTS.md`.
- Keep shareable project facts in tracked docs such as `README.md`, `context_info.md`, and `docs/submission_checklist.md`.
- Use `codex` from this repo root so local Codex settings can apply in your shell.

## Architecture

- `src/defiquant/strategy.py`: shared alpha model.
- `src/defiquant/risk.py`: guardrails for max drawdown, concentration, turnover, and cash.
- `src/defiquant/backtest.py`: deterministic daily rebalance simulator.
- `src/defiquant/competition.py`: hackathon allowlist and qualification guardrails.
- `src/defiquant/data/cmc.py`: CMC API client and response parser.
- `src/defiquant/execution/`: paper and TWAK CLI execution adapters.
- `skills/cmc-defiquant/`: draft CMC Skill package metadata.

## Toolchain

- Python: 3.14, pinned in `.python-version` and `pyproject.toml`.
- Package runner: `uv`.
- Formatting and linting: `ruff`.
- Type checking: `ty`, chosen over mypy/pyright for speed and fit with the Astral toolchain.
- Tests: `pytest`.
- CI: GitHub Actions with `uv sync`, Ruff, ty, and pytest.

If a backend server is added, use FastAPI and run it through `uv run fastapi ...`.

## Strategy

The initial model ranks eligible CMC-listed BNB Chain tokens using:

- medium-term momentum,
- short/long moving-average trend,
- liquidity preference,
- volatility penalty.

Weights are inverse-volatility adjusted, capped per asset, and forced to keep a cash/stable reserve. If portfolio drawdown breaches the configured limit, the risk manager moves to cash-only mode.

## Competition Rules Captured

- Track 1 on-chain registration must happen before `2026-06-22T00:00:00Z`.
- Track 2 Skill submission is due by the end of the build window on June 21, 2026.
- Live Track 1 trading runs June 22-28, 2026.
- Trades count only for the fixed eligible BEP-20 token list in `configs/eligible_tokens.json`.
- The default universe intentionally excludes native `BNB`, `XVS`, and `BAKE` because they are not present in the copied eligible list.
- The agent must trade at least once per day over the 7-day trading week.
- A wallet with $1 or less at the start of an hourly measurement is treated as having no capital at work for that hour.
- Drawdown is a hard risk gate; the local default is 25%, below the example 30% disqualification threshold.

## Hackathon Work Plan

1. June 13-14: connect real CMC data, validate the eligible token universe, and run backtests.
2. June 15-16: align `skills/cmc-defiquant` with the official CMC Skill schema and prepare Track 2 submission.
3. June 17-19: wire TWAK/BNB execution on testnet and rehearse the full Track 1 loop.
4. June 20: complete on-chain registration and fund only a small mainnet wallet.
5. June 21: final DoraHacks submission check.
6. June 22-28: monitor live trading, daily trade requirement, and drawdown.

## Safety Defaults

- Live execution is disabled unless `TWAK_DRY_RUN=false`.
- The max drawdown default is below the example disqualification threshold.
- Strategy config loading fails if the universe includes tokens outside the competition allowlist.
- Backtest output reports whether the strategy meets the minimum 7 qualified trade days.
- Per-position caps and a minimum cash reserve are enforced after every signal.
- All execution adapters consume the same target-weight payload produced by the shared strategy.
