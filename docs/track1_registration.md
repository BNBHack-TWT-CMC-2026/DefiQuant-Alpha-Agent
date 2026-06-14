# Track 1 Registration Runbook

Track 1 registration is an irreversible external action. This runbook keeps the
safe preparation steps separate from the final live registration.

## Safe Preflight

Default mode prints command plans and does not call TWAK:

```powershell
uv run defiquant track1-preflight
```

Read-only mode checks local TWAK authentication, the BSC wallet address, and the
BSC wallet portfolio. It does not submit registration or swaps:

```powershell
uv run defiquant track1-preflight --run-read-only
```

If the CLI is installed through npm, set the command prefix before running:

```powershell
$env:TWAK_CLI="npx @trustwallet/cli"
uv run defiquant track1-preflight --run-read-only
```

The expected preflight report includes:

- `registration_dry_run`: the TWAK registration command plan.
- `checks.auth_status`: local TWAK auth status.
- `checks.wallet_address`: BSC wallet address used for DoraHacks submission.
- `checks.wallet_portfolio`: read-only BSC portfolio snapshot.
- `hard_stop`: actions that require explicit approval.

## Hard Stop

Do not run live registration automatically. Stop and get explicit approval in
the current thread before:

```powershell
uv run defiquant register-track1 --live
```

After approval, capture the command output and transaction hash. Do not capture
or paste wallet passwords, private keys, seed phrases, TWAK API secrets, or CMC
API keys.

## Submission Evidence

Store these values in the DoraHacks submission notes and local evidence archive:

- BSC agent wallet address.
- Track 1 registration transaction hash.
- Registration timestamp in UTC and KST.
- Screenshot or URL confirming DoraHacks submission.
- Representative live trade transaction hashes after the trading window starts.

## Failure Handling

- If `auth_status` is not configured, rerun TWAK auth setup outside the repo and
  repeat read-only preflight.
- If `wallet_address` fails, confirm the local TWAK wallet exists and the
  keychain password is available in the current Windows session.
- If `wallet_portfolio` is empty, do not fund automatically. Funding is a hard
  stop and needs explicit approval.
