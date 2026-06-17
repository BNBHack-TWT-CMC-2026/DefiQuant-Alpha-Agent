# BNB Agent SDK Identity Runbook

This runbook prepares the BNB Agent SDK identity evidence without funding the
wallet or submitting an on-chain registration.

## Scope

- Use `bnb-register --dry-run` to produce ERC-8004 agent metadata preview.
- Keep Track 1 live registration and BNB Agent SDK live registration separate.
- Do not install the optional SDK, enter secrets, fund the wallet, or send a
  transaction during this dry-run step.

## Dry-Run Preview

Use the public agent URL placeholder until a real hosted endpoint is available:

```powershell
uv run defiquant bnb-register --config configs/strategy.json --agent-url https://example.com --wallet-address 0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc --network bsc-testnet --dry-run
```

The output should include:

- `dry_run: true`
- `network: bsc-testnet`
- `required_package: bnbagent`
- `live_hard_stop`
- `profile.name: defiQuant`
- `profile.wallet_address`
- `profile.endpoints`

Archive the preview output with the DoraHacks evidence bundle. Replace
`https://example.com` with the final demo endpoint before submission.

## Local Read-Only Endpoint

The public URL should serve the same read-only payloads that the CLI previews.
Run the local endpoint before choosing a hosting target:

```powershell
$env:DEFIQUANT_AGENT_URL="http://127.0.0.1:8000"
$env:DEFIQUANT_WALLET_ADDRESS="0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc"
$env:DEFIQUANT_NETWORK="bsc-testnet"
$env:PYTHONUTF8="1"
uv run fastapi dev src/defiquant/server.py
```

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/erc8183/status
```

The endpoint is metadata-only. It must not call CMC, TWAK, x402, or BNB Agent
SDK during request handling. Final hosting and the resulting public URL remain a
manual gate.

## Live Registration Hard Stop

BNB Agent SDK live registration is an on-chain identity action. Do not run it
until the user explicitly approves it in the current thread.

Live registration requires all of the following:

- final agent URL
- submitted BSC wallet address
- explicit network choice
- funded wallet for gas
- `PRIVATE_KEY`
- `WALLET_PASSWORD`
- exact confirmation phrase

The CLI rejects live registration unless the confirmation phrase is supplied:

```powershell
uv run defiquant bnb-register --config configs/strategy.json --agent-url https://example.com --wallet-address 0x9206D8416A11c5E54427fE5f226B3Ed384a266Cc --network bsc-testnet --live --confirm-live I_UNDERSTAND_BNB_AGENT_REGISTRATION_RISK
```

This command is only a reference. Do not execute it before approval.

## Evidence To Capture After Approval

- dry-run preview JSON
- final agent URL
- BSC wallet address
- selected network
- registration transaction hash
- explorer link
- DoraHacks submission screenshot or confirmation URL
