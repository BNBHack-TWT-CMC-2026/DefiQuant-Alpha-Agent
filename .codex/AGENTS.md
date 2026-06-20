# defiQuant Agent Guide

This file is the source of truth for Codex CLI, Codex Desktop, and other coding
agents working in this repository.

## Mission

Build a dual-track BNB Hack submission from one shared strategy core:

- Track 1: autonomous BSC trading agent using CMC data, TWAK signing/execution,
  and BNB AI Agent SDK.
- Track 2: non-executing CMC Skill that exposes the same strategy as a
  backtestable strategy spec.

Current product priority after PR #11:

1. Track 1 registration and evidence capture.
2. Track 1 live operations runbook and small-cap execution rehearsal.
3. Track 2 CMC Skill packaging through the DoraHacks Add option.
4. CMC Agent Hub read-only context integration.
5. BNB Agent SDK identity registration path.

## Repository Map

- `src/defiquant/strategy.py`: shared alpha model.
- `src/defiquant/risk.py`: drawdown, concentration, turnover, and cash
  guardrails.
- `src/defiquant/competition.py`: competition token allowlist and qualification
  checks.
- `src/defiquant/backtest.py`: deterministic fixture backtester.
- `src/defiquant/data/`: market-data adapters.
- `src/defiquant/execution/`: paper and TWAK execution adapters.
- `configs/strategy.json`: active strategy and competition settings.
- `configs/eligible_tokens.json`: copied competition allowlist.
- `skills/cmc-defiquant/`: Track 2 CMC Skill draft.
- `docs/submission_checklist.md`: submission requirements.
- `context_info.md`: captured hackathon rules.

## Toolchain

- Python: 3.14 via `uv`.
- Package manager and runner: `uv`.
- Formatter and linter: `ruff`.
- Type checker: `ty`.
- Test runner: `pytest`.
- GitHub work: prefer `gh`.
- Current-doc lookups for libraries and CLIs: use Context7 MCP first when
  available.

## Standard Commands

Run the full local gate:

```powershell
.\scripts\check.ps1
```

Run individual checks:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Smoke-test the CLI:

```powershell
uv run defiquant backtest --fixture --config configs/strategy.json
uv run defiquant signal --fixture --config configs/strategy.json
uv run defiquant execute --fixture --config configs/strategy.json --adapter twak --dry-run
uv run defiquant execute --fixture --config configs/strategy.json --adapter twak --portfolio twak --validate-quotes --dry-run
```

## Local Skills

- Use `.codex/skills/codex-code-review` when reviewing local diffs, commits, or
  GitHub PRs without an external review service.
- The code review skill defines the six-pass review flow: correctness,
  simplicity, tests, silent failures, types/data model, and security/operations.
- In the GitHub workflow, run this local code review skill after PR creation and
  before review selection comments or fix commits.

## Loop Engineering

- Use `.codex/LOOP.md` as the default loop/automode operating procedure.
- Keep loop-engineering procedures in `.codex/` files. Do not create tracked
  `docs/` files for agent queue-drain rules, automode policy, or local loop
  decision procedures. Public tracked docs should describe product behavior,
  strategy rationale, evidence, and submission runbooks only.
- Use `.codex/ALPHA_LOOP.md` for Track 1 alpha-pool and mode-selection loop
  operating context.
- When the user says `승인`, `계속`, `가자`, `automode`, or asks to proceed,
  continue the current loop without asking for step-by-step confirmation.
- For normal repo work, autonomously create Issues, record design comments,
  branch, implement, test, commit, push, open PRs, review, fix, merge, and clean
  branches.
- Use continuous queue-drain behavior: after one loop is merged and cleaned up,
  update `.codex/LOOP.md`, promote the next executable queue item, and start it
  immediately only when it does not require manual user action.
- After each completed loop, update `.codex/LOOP.md` so `Current Loop Queue`
  reflects the latest merged PR or completed milestone and the next executable
  loop is first.
- Do not turn queue execution into user-facing step-by-step approval prompts.
  Give concise progress updates and stop for manual intervention gates, real
  blockers, or explicit user pause.
- Do not silently skip a queue item that needs user action. Keep it first,
  explain the blocker, and ask for the exact action or approval needed.
- Ask at manual intervention gates: mainnet transactions, funding,
  secrets/private keys/passwords, destructive actions, external irreversible
  registrations not already approved in the current thread, permission/billing
  changes, paid x402 spending, external website/form submission, local auth
  repair, or plugin installation.

## Development Rules

- Keep shared strategy logic execution-agnostic. Track 1 execution and Track 2
  Skill packaging must remain thin adapters.
- Never add live trading by default. Keep dry-run/testnet as the default path.
- Never introduce secrets into the repo. Use `.env` locally and update
  `.env.example` only with names, not values.
- Treat `configs/eligible_tokens.json` as the hard trading allowlist. Code
  should fail closed when symbols are outside it.
- Preserve the drawdown-first posture. A strategy that survives is better than
  one that backtests loudly and fails the risk gate.
- Prefer small, testable changes over sweeping rewrites.
- When changing behavior, add or update focused tests.
- Before claiming done, run the standard local gate or clearly say why it could
  not be run.

## Competition Guardrails

- We are submitting both tracks through the DoraHacks Add option.
- Track 1 is the primary deliverable.
- Track 1 registration must happen before the June 22, 2026 live-trading
  window.
- Track 2 must remain non-executing.
- Track 1 must trade only in-scope tokens, hold non-zero in-scope value at
  competition start, and trade at least once per day during the live window.
- Mainnet actions require explicit user approval in the current thread.

## Git Workflow

- GitHub is the record of reasoning. All Issues, commits, PRs, and review
  comments must be written in Korean and show: why this work exists, what
  judgment was made, what changed, and how it was verified.
- Start every tracked task from a GitHub Issue. The Issue body must include
  background/problem, goal, and completion criteria.
- Before editing code or docs, add an Issue comment explaining the design
  judgment, rejected alternatives, and verification plan.
- Do not commit directly to `main`. Branch from main using
  `feature/#issue-description`, `fix/#issue-description`,
  `refactor/#issue-description`, `docs/#issue-description`, or
  `chore/#issue-description`.
- Use Conventional Commits with Korean descriptions, such as
  `fix: TWAK 토큰 주소 매핑 적용`.
- Keep one commit to one logical change. Separate docs, behavior, tests, and
  review fixes when they are logically separate.
- Before each commit, run at least `uv run pytest` and `uv run ruff check`; run
  `.\scripts\check.ps1` when the change touches behavior, typing, or shared
  tooling.
- Open PRs with `Closes #issue`, a summary, changed files, technical judgment,
  and verification results.
- After PR creation, use `.codex/skills/codex-code-review` for the default
  review pass unless the user explicitly requests another review method. The
  review must check correctness, simplicity, tests, silent failures,
  types/data model, and security/operations.
- Record the actual code review content before any selection or fix work. Post
  a PR comment titled `코드 리뷰` with Korean section names: `발견 사항`,
  `열린 질문`, `남은 위험`, and `검증`. If no issue is found, explicitly say
  `발견 사항 없음`.
- Do not replace the code review content with a selection summary. The
  selection summary is a separate later PR comment.
- Before applying review fixes, comment on the PR with what feedback is
  accepted, deferred, skipped, or split into a new Issue.
- Apply accepted review fixes as focused `fix:` commits.
- Split out-of-scope review feedback into a new Issue with context from the PR.
- Merge only after review and verification are complete. After merge, return to
  `main`, pull, and delete local and remote merged branches.
- Never add AI tool signatures, internal tool names, internal skill/plugin
  names, secrets, wallet passwords, private keys, or API secrets to GitHub
  artifacts.

## Communication

- Use Korean for user-facing summaries unless the user asks otherwise.
- Keep final updates short: what changed, how it was verified, and what the next
  useful step is.
