# Track 2 CMC Skill Submission Notes

## Package

Submit the `skills/cmc-defiquant/` directory for Track 2.

Included files:

- `skill.json`: package metadata and safety declaration.
- `SKILL.md`: executable skill instructions.
- `README.md`: package overview.
- `examples/input.fixture.json`: deterministic review input.
- `examples/output.fixture.json`: deterministic target-weight output.

## Purpose

The skill turns CoinMarketCap OHLCV data into BNB Chain target weights with
transparent rationale and risk controls. It is intended for CMC Agent Hub /
Skills Marketplace style routing as a read-only analysis pipeline.

It reuses the same alpha pool as Track 1:

- `medium_momentum`
- `trend_strength`
- `volume_impulse`
- `liquidity_depth`
- `short_reversal_guard`
- `trend_angle`
- `supertrend_alignment`
- `volatility`

## Non-Execution Proof

This package does not include:

- TWAK CLI commands,
- private key or wallet password handling,
- transaction signing,
- order submission,
- funding logic,
- mainnet mutation.

The only local commands documented for this package are:

```powershell
uv run defiquant signal --fixture --config configs/strategy.json
uv run defiquant signal --config configs/strategy.json --cmc-days 90
uv run defiquant backtest --config configs/strategy.json --cmc-days 90 --cmc-end-date 2026-06-12
uv run defiquant research-report --windows 90,180,365
uv run defiquant alpha-lab --windows 90,180,365 --max-candidates 1000 --top 5
```

Track 1 execution remains outside this package under the repository execution
adapters and live-operation guardrails.

Track 1 `frontier-evidence`, TWAK dry-run, quote validation, registration, and
live swaps are intentionally excluded from the Track 2 Skill package.

## Review Checklist

- Confirm `skill.json` parses as JSON.
- Confirm examples parse as JSON.
- Run fixture signal and compare the shape to `examples/output.fixture.json`.
- Confirm `examples/input.fixture.json` matches `configs/strategy.json`.
- Confirm each non-stable fixture output includes the alpha pool reason keys.
- Confirm `SKILL.md` contains no wallet mutation instructions.
- Confirm `.env` and API keys are not included.
