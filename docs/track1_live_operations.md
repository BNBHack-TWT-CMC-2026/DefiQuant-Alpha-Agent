# Track 1 Live Operations Runbook

This runbook defines the safe operating loop for the Track 1 live trading
window. It does not approve funding, registration, or mainnet transactions by
itself.

## Hard Stops

Stop for explicit approval before:

- running `uv run defiquant register-track1 --live`,
- funding the Track 1 wallet,
- running any `execute --live` command,
- increasing live notional caps above `configs/live_operations.json`,
- exporting, importing, printing, or pasting wallet/API secrets.

## Before Registration

Run read-only preflight:

```powershell
uv run defiquant track1-preflight --run-read-only
```

Confirm:

- `checks.auth_status.ok` is `true`,
- `checks.wallet_address.ok` is `true`,
- the BSC wallet address matches the DoraHacks wallet field,
- `checks.wallet_portfolio.ok` is `true`,
- no secret or API credential identifier is copied into public artifacts.

Live registration remains blocked until explicit approval:

```powershell
uv run defiquant register-track1 --live
```

## Funding Policy

Funding is a hard stop. Do not send funds automatically.

Use `configs/live_operations.json` as the local cap source:

- recommended initial capital: `5.0` USD equivalent,
- maximum initial capital without new approval: `10.0` USD equivalent,
- minimum in-scope value for measurement: `1.01` USD equivalent.

After funding approval and transfer, rerun:

```powershell
uv run defiquant track1-preflight --run-read-only
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --dry-run
```

## Live Trade Command Shape

The only allowed live execution shape is:

```powershell
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --portfolio twak --validate-quotes --live --confirm-live I_UNDERSTAND_TWAK_LIVE_SWAP_RISK --max-live-notional-usd 1
```

Choose the cap from `configs/live_operations.json`:

- `smoke`: first approved live smoke trade,
- `default`: normal daily trade cap,
- `maximum_without_new_approval`: hard ceiling unless a new approval is recorded.

## Daily Live Loop

During `2026-06-22T00:00:00Z` to `2026-06-28T23:59:59Z`:

1. Run read-only preflight.
2. Run CMC-backed signal or dry-run execution planning.
3. Run TWAK quote validation in dry-run mode.
4. Check the planned order count and total notional.
5. If live execution is needed, stop for approval if the cap or command differs
   from the current approved run.
6. Capture tx hash, command output, UTC/KST timestamp, and daily notes.

## Halt Criteria

Stop live activity when any condition is true:

- TWAK auth, wallet address, or wallet portfolio check fails.
- CMC data loading fails or uses stale candles.
- Quote validation fails for any planned order.
- Planned order or batch exceeds the approved live notional cap.
- Any symbol is outside `configs/eligible_tokens.json`.
- Drawdown reaches the configured risk gate.
- A submitted transaction returns an unexpected payload or no tx hash.
- The local operator is unsure whether a command is read-only or live.

## Evidence Archive

Use a local ignored path:

```text
artifacts/track1-live/
  registration/
    registration-preflight.json
    registration-output.json
    dorahacks-submission-note.md
  2026-06-22/
    preflight.json
    dry-run-plan.json
    quote-validation.json
    live-execution.json
    tx-notes.md
```

Do not commit `artifacts/` or `reports/`. Redact secrets before sharing any
evidence publicly.
