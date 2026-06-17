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
uv run defiquant signal --config configs/strategy.json --alpha-source latest
uv run defiquant execute --config configs/strategy.json --alpha-source latest --adapter twak --portfolio twak --validate-quotes --dry-run
```

## Live Trade Command Shape

Run the read-only alpha decision first:

```powershell
uv run defiquant research-report --windows 90,180,365
uv run defiquant alpha-lab --windows 90,180,365 --max-candidates 1000 --top 10
uv run defiquant scan-alpha --symbols-source tradable --top 10
uv run defiquant alpha-evidence --mode auto --top 10
uv run defiquant submission-evidence --agent-url https://example.com --wallet-address 0x...
```

For live-window rehearsal, convert the same latest CMC quote alpha into target
weights before any TWAK command:

```powershell
uv run defiquant signal --config configs/strategy.<selected>.json --alpha-source latest
uv run defiquant execute --config configs/strategy.<selected>.json --alpha-source latest --adapter twak --portfolio twak --validate-quotes --dry-run
```

Then choose one of the reviewed mode configs:

- `configs/strategy.aggressive.json`
- `configs/strategy.balanced.json`
- `configs/strategy.defensive.json`
- `configs/strategy.frontier-risk.json`
- `configs/strategy.frontier-return.json`
- `configs/strategy.frontier-lowdrawdown.json`
- `configs/strategy.tournament.json`

The tournament lane also requires its broader verified BSC address map:

```powershell
uv run defiquant signal --config configs/strategy.tournament.json --alpha-source latest --token-addresses configs/token_addresses.bsc.tournament.json
uv run defiquant execute --config configs/strategy.tournament.json --alpha-source latest --token-addresses configs/token_addresses.bsc.tournament.json --adapter twak --portfolio twak --validate-quotes --dry-run
```

Use `strategy.tournament.json` only when the explicit goal is Track 1 prize
PnL, the latest quote scan still supports the selected tokens, and the planned
batch stays inside the approved live notional cap.

The only allowed live execution shape is:

```powershell
uv run defiquant execute --config configs/strategy.<selected>.json --alpha-source latest --adapter twak --portfolio twak --validate-quotes --live --confirm-live I_UNDERSTAND_TWAK_LIVE_SWAP_RISK --max-live-notional-usd 1
```

Replace `<selected>` with a reviewed config suffix only after the matching
dry-run and quote validation have been captured. For the first approved smoke
trade, prefer `defensive` or `frontier-risk` unless the approval explicitly
names a different mode and cap. If the selected config is `tournament`, include
`--token-addresses configs/token_addresses.bsc.tournament.json` in the live
command as well.

The default `signal` and `execute` path still uses daily OHLCV candles. The
`--alpha-source latest` path is a Track 1 execution overlay for current CMC
quote momentum and liquidity; it does not change Track 2 or the deterministic
backtest path.

Choose the cap from `configs/live_operations.json`:

- `smoke`: first approved live smoke trade,
- `default`: normal daily trade cap,
- `maximum_without_new_approval`: hard ceiling unless a new approval is recorded.

## Daily Live Loop

During `2026-06-22T00:00:00Z` to `2026-06-28T23:59:59Z`:

1. Run read-only preflight.
2. Run `research-report` and record the robust baseline mode.
3. Run `alpha-lab` and record whether any candidate beats the baseline across
   the same windows.
4. Run `scan-alpha` and record the latest quote alpha mode.
5. Run `alpha-evidence --mode auto` and save the latest quote alpha packet.
6. Run `submission-evidence` and save the generated manifest.
7. Run CMC-backed dry-run execution planning with the selected mode config.
8. Run TWAK quote validation in dry-run mode.
9. Check the planned order count and total notional.
10. If live execution is needed, stop for approval if the cap or command differs
   from the current approved run.
11. Capture tx hash, command output, UTC/KST timestamp, and daily notes.

## Halt Criteria

Stop live activity when any condition is true:

- TWAK auth, wallet address, or wallet portfolio check fails.
- CMC data loading fails or uses stale candles.
- Alpha mode selection cannot be reproduced from saved scan output.
- Research report recommends a safer baseline mode and there is no explicit
  reason to override it.
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
    research-report.json
    alpha-lab.json
    alpha-evidence.json
    submission-evidence-manifest.json
    dry-run-plan.json
    quote-validation.json
    live-execution.json
    tx-notes.md
```

Do not commit `artifacts/` or `reports/`. Redact secrets before sharing any
evidence publicly.
