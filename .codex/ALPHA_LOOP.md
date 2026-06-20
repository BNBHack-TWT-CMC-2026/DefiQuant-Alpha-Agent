# Alpha Loop

This file is local agent operating context. Do not move loop-engineering
procedure into tracked `docs/` files. Public docs should describe the product,
strategy, evidence, and submission runbooks; `.codex/` should describe how the
agent drains work queues and makes operating decisions.

## Strategy Layers

The Track 1 strategy has two separate layers:

- alpha pool: daily OHLCV factors that rank tokens,
- exposure mode: CMC latest-quote regime selection that chooses aggressive,
  balanced, or defensive risk parameters.

The three modes are not three independent alphas. They control how much capital
the shared alpha pool is allowed to deploy.

`configs/strategy.tournament.json` is different: it is an opt-in Track 1 prize
lane with a broader CMC-discovered BSC address map and materially higher
capital deployment. Treat it as a tournament override, not as the default
conservative lane.

## Alpha Pool

The daily strategy combines these factor components:

- `medium_momentum`: lookback-period price momentum.
- `trend_strength`: fast/slow moving-average spread.
- `volume_impulse`: recent volume expansion versus lookback volume.
- `liquidity_depth`: average traded volume on a log scale.
- `short_reversal_guard`: small pullback tolerance and blowoff/crash penalty.
- `trend_angle`: normalized recent price slope.
- `supertrend_alignment`: ATR-based trend state used as a soft factor when enabled.
- `volatility`: drawdown-aware risk penalty.

Current tournament validation:

- `trend_angle=0.03` improved the 60/90-day tournament backtests without
  changing the 30-day result materially.
- `supertrend_alignment` is computed and reported, but its tournament weight is
  currently `0.0` because positive weighting degraded recent CMC backtests and
  negative weighting only improved 30-day return while damaging 60/90-day
  return. Do not enable it for live trading unless a fresh validation run beats
  the current tournament objective.

The output signal includes these components in `reasons` so live decisions can
be explained without exposing wallet secrets or execution state.

## Mode Decision

Before any live trading decision, run:

```powershell
uv run defiquant scan-alpha --symbols-source tradable --top 10
uv run defiquant signal --config configs/strategy.tournament.json --alpha-source latest --token-addresses configs/token_addresses.bsc.tournament.json
```

Use the result only as read-only context. Then dry-run the selected mode before
any live approval:

```powershell
uv run defiquant execute --config configs/strategy.aggressive.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --dry-run
uv run defiquant execute --config configs/strategy.balanced.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --dry-run
uv run defiquant execute --config configs/strategy.defensive.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --dry-run
uv run defiquant execute --config configs/strategy.tournament.json --alpha-source latest --token-addresses configs/token_addresses.bsc.tournament.json --adapter twak --portfolio twak --validate-quotes --dry-run
```

Choose the most aggressive mode only when:

- the scan recommends it,
- quote validation succeeds,
- total notional is inside the approved live cap,
- the wallet has enough BNB for gas,
- the planned symbols are all in `configs/eligible_tokens.json`,
- tournament symbols are all mapped in `configs/token_addresses.bsc.tournament.json`,
- the current drawdown state is below the halt threshold.

If any check is uncertain, use defensive mode or stop.

## Hard Stops

This loop never approves:

- wallet funding,
- Track 1 live registration,
- TWAK live swaps,
- BNB Agent SDK live registration,
- x402 paid calls,
- DoraHacks form submission.

Those remain manual gates that require explicit approval in the current thread.
