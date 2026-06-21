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

Run the same flow with live CoinMarketCap OHLCV data:

```powershell
$env:CMC_API_KEY="your-cmc-api-key"
uv run defiquant signal --config configs/strategy.json --cmc-days 90
uv run defiquant backtest --config configs/strategy.json --cmc-days 90 --cmc-end-date 2026-06-12
uv run defiquant research-report --windows 90,180,365
uv run defiquant track1-exposure-sweep --cmc-days 90 --target-windows 100
uv run defiquant alpha-lab --windows 90,180,365 --max-candidates 1000 --top 10
uv run defiquant submission-evidence --windows 90,180,365 --agent-url https://example.com --wallet-address 0x...
```

When `--fixture` is omitted, the CLI requests daily CMC OHLCV candles for the configured
universe. By default it ends at the last complete UTC day; use `--cmc-end-date YYYY-MM-DD`
for reproducible submission evidence.

Scan current CMC quotes for the Track 1 alpha mode decision:

```powershell
uv run defiquant scan-alpha --symbols-source tradable --top 10
uv run defiquant scan-alpha --symbols-source eligible --top 15
uv run defiquant signal --config configs/strategy.aggressive.json --alpha-source latest
uv run defiquant signal --config configs/strategy.tournament.json --alpha-source latest --token-addresses configs/token_addresses.bsc.tournament.json
uv run defiquant alpha-evidence --mode auto --top 10
uv run defiquant frontier-evidence --portfolio-cash 1000
```

The tradable scan is read-only and recommends `aggressive`, `balanced`, or
`defensive` live parameters. The broad eligible scan is discovery-only; new
symbols are not executable until their BSC token address is verified and added
to `configs/token_addresses.bsc.json`. Use `--alpha-source latest` only for
Track 1 live-window rehearsal and execution planning; the default signal path
remains daily OHLCV for deterministic backtests and Track 2.

Dry-run a TWAK execution plan:

```powershell
uv run defiquant execute --config configs/strategy.json --cmc-days 90 --adapter twak --dry-run
uv run defiquant execute --config configs/strategy.aggressive.json --alpha-source latest --adapter twak --portfolio twak --validate-quotes --dry-run
uv run defiquant execute --config configs/strategy.tournament.json --alpha-source latest --token-addresses configs/token_addresses.bsc.tournament.json --adapter twak --portfolio twak --validate-quotes --dry-run
```

Run the full local check:

```powershell
.\scripts\check.ps1
```

Before funding the Track 1 wallet, run the safe readiness loop:

```powershell
uv run defiquant tune-risk --config configs/strategy.json --candidates configs/risk_tuning.json --cmc-days 90 --top 5
uv run defiquant research-report --windows 90,180,365
uv run defiquant track1-exposure-sweep --config configs/strategy.tournament.json --cmc-days 90 --target-windows 100
uv run defiquant alpha-lab --windows 90,180,365 --max-candidates 1000 --top 10
uv run defiquant agent-endpoints --config configs/strategy.json --agent-url https://example.com --wallet-address 0x... --network bsc-testnet
uv run defiquant track1-preflight --run-read-only
uv run defiquant alpha-evidence --mode auto --portfolio-cash 1000
uv run defiquant frontier-evidence --portfolio-cash 1000
uv run defiquant submission-evidence --agent-url https://example.com --wallet-address 0x...
uv run defiquant execute --config configs/strategy.aggressive.json --alpha-source latest --adapter twak --portfolio twak --validate-quotes --dry-run
```

## Agent And CLI Setup

- Local Codex CLI notes/settings can live under `.codex/`, but that directory is intentionally ignored by git.
- The current local agent guide is `.codex/AGENTS.md`.
- Keep shareable project facts in tracked docs such as `README.md`, `context_info.md`, and `docs/submission_checklist.md`.
- Use `codex` from this repo root so local Codex settings can apply in your shell.

## Architecture

- `src/defiquant/strategy.py`: shared alpha model.
- `src/defiquant/alpha.py`: CMC latest-quote alpha scanner, mode selector, and live-window signal source.
- `src/defiquant/alpha_lab.py`: deterministic alpha-weight sweep for self-improvement research.
- `src/defiquant/risk.py`: guardrails for max drawdown, concentration, turnover, and cash.
- `src/defiquant/backtest.py`: deterministic daily rebalance simulator.
- `src/defiquant/research.py`: multi-window mode comparison and deployment recommendation.
- `src/defiquant/competition.py`: hackathon allowlist and qualification guardrails.
- `src/defiquant/data/cmc.py`: CMC API client and response parser.
- `src/defiquant/execution/`: paper and TWAK CLI execution adapters.
- `skills/cmc-defiquant/`: draft CMC Skill package metadata.
- `configs/mcp/`: CMC MCP, CMC x402 MCP, and TWAK MCP client templates.
- `docs/agent_integrations.md`: end-to-end integration runbook.

## Toolchain

- Python: 3.14, pinned in `.python-version` and `pyproject.toml`.
- Package runner: `uv`.
- Formatting and linting: `ruff`.
- Type checking: `ty`, chosen over mypy/pyright for speed and fit with the Astral toolchain.
- Tests: `pytest`.
- CI: GitHub Actions with `uv sync`, Ruff, ty, and pytest.

If a backend server is added, use FastAPI and run it through `uv run fastapi ...`.

## Strategy

The model ranks eligible CMC-listed BNB Chain tokens with an alpha pool:

- medium-term momentum,
- short/long moving-average trend strength,
- recent volume impulse,
- liquidity depth,
- short-term reversal and blowoff guard,
- normalized trend angle,
- ATR-based Supertrend alignment,
- volatility penalty.

Weights are inverse-volatility adjusted, capped per asset, and forced to keep a cash/stable reserve. If portfolio drawdown breaches the configured limit, the risk manager moves to cash-only mode.

For Track 1 live operations, the CLI can also convert current CMC latest quotes
into executable target weights with `--alpha-source latest`. That path uses the
same risk manager and TWAK guards, but it is intentionally excluded from
historical backtests because latest quote data is not a deterministic OHLCV
series.

Use `alpha-lab` to run deterministic alpha-weight sweeps. Its report separates
risk-adjusted, minimum-return, average-return, lowest-drawdown, and robustness
frontiers so candidate promotion is not based on a single overfit score. Each
candidate also reports positive-return windows, drawdown headroom, and a
promotable flag for conservative promotion review.

Use `track1-exposure-sweep` to split Track 1 OHLCV history into rolling windows
and evaluate research-only exposure multipliers together with candidate MDD
targets. This does not enable leverage in TWAK; it provides evidence for
position sizing, cash reserve, turnover, and live cap decisions.

Frontier configs from the current lab are available as
`configs/strategy.frontier-risk.json`, `configs/strategy.frontier-return.json`,
and `configs/strategy.frontier-lowdrawdown.json`.

`configs/strategy.tournament.json` is a separate opt-in Track 1 lane for the
live competition window. It uses a broader CMC-discovered BSC token address map
in `configs/token_addresses.bsc.tournament.json`, raises capital deployment, and
should be used only after latest-quote dry-run and TWAK quote validation. It
does not replace the default strategy or the non-executing Track 2 Skill path.

## Competition Rules Captured

- Track 1 on-chain registration must happen before `2026-06-22T00:00:00Z`.
- Track 2 Skill submission is due by the end of the build window on June 21, 2026.
- Live Track 1 trading runs June 22-28, 2026.
- Trades count only for the fixed eligible BEP-20 token list in `configs/eligible_tokens.json`.
- The default universe intentionally excludes native `BNB`, `XVS`, and `BAKE` because they are not present in the copied eligible list.
- The agent must trade at least once per day over the 7-day trading week.
- A wallet with $1 or less at the start of an hourly measurement is treated as having no capital at work for that hour.
- Drawdown is a hard risk gate; the local default is 20%, below the example 30% disqualification threshold.

## Hackathon Work Plan

1. June 13-14: connect real CMC data, validate the eligible token universe, and run backtests.
2. June 15-16: align `skills/cmc-defiquant` with the official CMC Skill schema and prepare Track 2 submission.
3. June 17-19: wire TWAK/BNB execution on testnet and rehearse the full Track 1 loop.
4. June 20: complete on-chain registration and fund only a small mainnet wallet.
5. June 21: final DoraHacks submission check.
6. June 22-28: monitor live trading, daily trade requirement, and drawdown.

## Safety Defaults

- TWAK swap planning defaults to dry-run and can read TWAK wallet portfolio with `--portfolio twak`.
- TWAK quote validation is available with `--validate-quotes`.
- TWAK live swaps require `--portfolio twak`, `--validate-quotes`, `--confirm-live I_UNDERSTAND_TWAK_LIVE_SWAP_RISK`, and a positive `--max-live-notional-usd` cap.
- The TWAK live cap is checked against both each planned order and the total planned batch before any swap submission.
- One-way external actions such as Track 1 or BNB Agent registration require `--live`.
- The max drawdown default is below the example disqualification threshold.
- Strategy config loading fails if the universe includes tokens outside the competition allowlist.
- Backtest output reports whether the strategy meets the minimum 7 qualified trade days.
- Per-position caps and a minimum cash reserve are enforced after every signal.
- All execution adapters consume the same target-weight payload produced by the shared strategy.

## Full Integration Commands

Preview the Track 1 registration command:

```powershell
uv run defiquant track1-preflight
uv run defiquant track1-preflight --run-read-only
uv run defiquant register-track1 --dry-run
```

Build the shared agent profile used for DoraHacks and BNB Agent SDK identity:

```powershell
uv run defiquant profile --config configs/strategy.json --agent-url https://example.com --wallet-address 0x...
```

Preview BNB Agent SDK ERC-8004 registration metadata:

```powershell
uv run defiquant bnb-register --config configs/strategy.json --agent-url https://example.com --wallet-address 0x... --network bsc-testnet --dry-run
```

MCP templates:

- `configs/mcp/cmc-mcp.json`: CMC Agent Hub with API key.
- `configs/mcp/cmc-x402.json`: CMC Agent Hub through x402 pay-per-call.
- `configs/mcp/twak.json`: TWAK MCP server through `twak serve`.
- `configs/cmc_agent_context.json`: read-only CMC Agent Hub prompt template and spend guardrails.
- `configs/bnb_agent_identity.json`: BNB Agent SDK identity dry-run and live guardrails.
- `configs/risk_tuning.json`: CMC-backed risk tuning candidate presets.
- `configs/alpha_modes.json`: Track 1 mode-switch thresholds and risk parameters.

Track 1 operations:

- `docs/prefunding_readiness.md`: safe checks before wallet funding.
- `docs/track1_registration.md`: registration preflight and evidence capture.
- `docs/track1_live_operations.md`: live-window operating loop and halt criteria.
- `uv run defiquant alpha-evidence --mode auto`: latest quote alpha, selected mode, target weights, and TWAK dry-run evidence packet.
- `configs/live_operations.json`: funding and live notional cap presets.
- `docs/bnb_agent_identity.md`: BNB Agent SDK identity dry-run and registration hard stop.
