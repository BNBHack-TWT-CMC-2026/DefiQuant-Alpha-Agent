# defiQuant

defiQuant is a single strategy engine with two thin adapters:

- Track 2: package the CMC-driven strategy as a CMC Skill.
- Track 1: reuse the same strategy output, then add wallet signing and BSC execution through TWAK/BNB tooling.

The project starts deliberately small: deterministic backtests, strict drawdown controls, and dry-run execution first. Live trading should only be enabled after testnet rehearsal.

## Current Status

The DoraHacks page is protected by AWS WAF CAPTCHA, so this repository is scaffolded from the provided competition summary. Re-check the official page manually before final submission, especially dates, eligible token universe, registration, and exact CMC Skill schema.

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

## Architecture

- `src/defiquant/strategy.py`: shared alpha model.
- `src/defiquant/risk.py`: guardrails for max drawdown, concentration, turnover, and cash.
- `src/defiquant/backtest.py`: deterministic daily rebalance simulator.
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

## Hackathon Work Plan

1. June 13-14: connect real CMC data, validate the eligible token universe, and run backtests.
2. June 15-16: align `skills/cmc-defiquant` with the official CMC Skill schema and prepare Track 2 submission.
3. June 17-19: wire TWAK/BNB execution on testnet and rehearse the full loop.
4. June 20: complete on-chain registration and fund only a small mainnet wallet.
5. June 21: final DoraHacks submission check.
6. June 22-28: monitor live trading, daily trade requirement, and drawdown.

## Safety Defaults

- Live execution is disabled unless `TWAK_DRY_RUN=false`.
- The max drawdown default is below the example disqualification threshold.
- Per-position caps and a minimum cash reserve are enforced after every signal.
- All execution adapters consume the same target-weight payload produced by the shared strategy.
