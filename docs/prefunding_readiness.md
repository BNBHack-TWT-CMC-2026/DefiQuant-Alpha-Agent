# Pre-Funding Readiness Runbook

This runbook covers only work that is safe before funding the Track 1 wallet.

## Hard Boundary

Do not run these before explicit approval:

- wallet funding,
- `uv run defiquant register-track1 --live`,
- `uv run defiquant execute ... --live`,
- `uv run defiquant bnb-register ... --live`,
- private key, wallet password, seed phrase, API secret export or disclosure,
- paid x402 calls,
- DoraHacks final form submission.

## CMC Risk Tuning

Compare risk presets against one shared market dataset:

```powershell
uv run defiquant tune-risk --config configs/strategy.json --candidates configs/risk_tuning.json --cmc-days 90 --top 5
```

Use a fixed end date for reproducible evidence:

```powershell
uv run defiquant tune-risk --config configs/strategy.json --candidates configs/risk_tuning.json --cmc-days 90 --cmc-end-date 2026-06-14 --top 5
```

The ranked output marks a candidate `eligible` only when it meets the minimum
trade-day requirement and stays within its drawdown cap.

Current default selection after the `2026-06-14` CMC run:

- preset: `high_reserve_cash_50`
- `top_n`: `3`
- `min_score`: `0.0`
- `max_position_weight`: `0.07`
- `min_cash_weight`: `0.5`
- `max_daily_turnover`: `0.12`

This was selected because it ranked first on the risk-adjusted score and had the
lowest drawdown among the eligible candidates in that run.

Observed validation on `2026-06-15` KST with CMC candles ending `2026-06-14`:

- `baseline_current` / `high_reserve_cash_50` ranked first.
- total return: `-0.02002662`
- max drawdown: `0.08831088`
- qualified trade days: `61`
- latest signal: `PENDLE 0.07`, `CAKE 0.07`, `LINK 0.07`, `USDT 0.79`

## Agent Endpoint Payloads

Prepare the payloads that a hosted agent endpoint should serve:

```powershell
uv run defiquant agent-endpoints --config configs/strategy.json --agent-url https://example.com --wallet-address 0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc --network bsc-testnet
```

This command does not host a server and does not register the BNB Agent SDK
identity. Replace `https://example.com` only after a real public endpoint exists.

## TWAK Read-Only Checks

Run safe TWAK checks:

```powershell
uv run defiquant track1-preflight --run-read-only
```

Then rehearse the execution loop without submitting swaps:

```powershell
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --dry-run
```

If wallet balance is zero, the execution dry-run may produce no orders. That is
acceptable before funding; do not fund automatically.

Observed validation on `2026-06-15` KST:

- TWAK auth: configured.
- BSC wallet: `0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc`.
- Native BNB balance: `0`.
- Execution dry-run audit: `order_count=0`, `quote_count=0`,
  `total_notional_usd=0`.

The next Track 1 step remains blocked by wallet funding and explicit live
registration approval.
