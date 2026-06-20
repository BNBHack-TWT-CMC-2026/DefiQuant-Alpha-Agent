# Loop Engineering

This file defines the default working loop for this repository. Use it when the
user says to continue, proceed, run the loop, use automode, or gives a compact
approval such as `승인`, `계속`, or `가자`.

## Operating Mode

Default to continuous automode for ordinary development work.

Related local loop context:

- `.codex/ALPHA_LOOP.md`: Track 1 alpha-pool and mode-selection operating
  context. Keep this kind of loop procedure in `.codex/`, not tracked `docs/`.

Automode means:

- Do not ask for step-by-step permission for normal repo work.
- Create Issues, comments, branches, commits, PRs, review comments, and merges
  when the current loop requires them.
- Run local checks without waiting for separate user approval.
- Batch related shell reads and checks where possible.
- Keep moving across loop boundaries until the queue is exhausted, a manual
  intervention gate is reached, or the user explicitly pauses the run.
- After one loop is merged and cleaned up, update the queue and start the next
  executable queue item only when it does not require user action.

Automode does not override platform security prompts. If the tool runtime asks
for approval, request it with the broadest safe prefix for the current category.

## Continuous Queue Drain

The default behavior is queue drain, not step-by-step handoff.

- Treat `Current Loop Queue` as an executable backlog.
- Start item 1 automatically when the user says to continue or when the previous
  loop just finished.
- Do not stop merely to ask which item is next if the queue already says what is
  next.
- Do not present a long step plan unless it reduces risk or the user asks for
  one. Prefer brief progress updates while doing the work.
- If item 1 contains a manual intervention gate, do every safe precursor first:
  docs, preflight checks, dry-runs, evidence capture, Issue/PR work, and exact
  command preparation. Stop at the gate and ask the user for the specific needed
  action or approval.
- If item 1 is blocked by a manual action, do not skip it by default. Record the
  blocker in the queue and ask the user. Continue to another queue item only if
  the user explicitly says to skip or park the blocked item.
- When switching to the next queue item, create or select its GitHub Issue and
  continue the GitHub loop without waiting for another user prompt.

## Manual Intervention Gates

Stop and ask the user when progress requires them to do or approve something
outside safe repo automation.

Examples:

- mainnet transaction submission,
- wallet funding or moving funds,
- irreversible registration,
- entering, revealing, copying, importing, or exporting secrets,
- approving paid x402 spending,
- choosing between materially different submission paths,
- logging into an external website or completing a web form,
- solving a local auth/keychain problem that cannot be fixed safely from code.

When stopping, provide:

- the exact blocker,
- the safe work already completed,
- the exact command, page, or action needed from the user,
- what will resume automatically after the user confirms completion.

## Hard Stop Conditions

Stop and ask for explicit user approval before:

- mainnet transaction submission,
- sending funds or funding a wallet,
- revealing, copying, importing, or exporting private keys, seed phrases,
  wallet passwords, API secrets, or HMAC secrets,
- destructive filesystem or git actions that can discard work,
- deleting GitHub Issues, PRs, or branches that are not part of the completed
  loop,
- changing repository ownership, visibility, billing, or permissions,
- installing a plugin or connector,
- making an irreversible external registration if the user has not already
  approved that exact registration in the current thread.

## Loop Shape

Each loop should use this structure at loop boundaries:

```text
Loop N
목표:
완료 조건:
작업 범위:
검증:
결과:
다음 loop 후보:
```

The assistant should not print this full block before every small action. Use it
only when starting a new queue-drain run, after completing a loop batch, or when
a blocker changes the plan.

## GitHub Loop

For tracked repo work:

1. Confirm clean starting state.
2. Create or select a GitHub Issue.
3. Add an Issue comment with the design judgment before editing.
4. Branch from `main`.
5. Implement focused changes.
6. Run `uv run pytest` and `uv run ruff check`; run `.\scripts\check.ps1` for
   behavior, typing, tooling, or integration changes.
7. Commit with a Korean Conventional Commit message.
8. Push branch and create a draft PR.
9. Post a `코드 리뷰` comment before any selection or fix work.
10. If findings exist, post a separate `리뷰 선별` comment before editing.
11. Apply accepted fixes as focused `fix:` commits.
12. Wait for CI, mark ready, merge, return to `main`, prune branches.
13. Update `Current Loop Queue` in this file so the completed loop is removed,
    the next default loop is first, and any new blockers or follow-up loops are
    recorded.
14. If the next queue item is safe to start and does not require manual user
    action, begin it immediately.
15. If the next queue item requires manual action, stop and ask the user for
    that action instead of skipping to a later item.
16. Report only when a batch is complete, a manual intervention gate is reached,
    or the user asks for status.

## Loop Queue Maintenance

At the end of every completed loop:

- Update `Default next loops after ...` to reference the latest merged PR or
  completed milestone.
- Remove the completed loop from the queue.
- Promote the next executable loop to item 1.
- Add newly discovered follow-ups, blockers, or hard-stop gates to the queue.
- Keep irreversible actions split into a dry-run/evidence loop and a separate
  explicit-approval live action.
- If the promoted item can proceed without manual intervention, start it
  immediately after queue maintenance.
- If the promoted item requires manual intervention, keep it first in the queue
  and ask the user instead of silently moving to a later item.

## Code Review Comment Format

Use Korean section names in GitHub artifacts:

```markdown
## 코드 리뷰

### 발견 사항
- [심각도] file:line - 문제, 영향, 권장 수정.

### 열린 질문
- 없음.

### 남은 위험
- 남은 위험.

### 검증
- 실행한 명령과 결과.
```

If no issues are found, write:

```markdown
## 코드 리뷰

### 발견 사항
- 발견 사항 없음.

### 열린 질문
- 없음.

### 남은 위험
- 남은 위험.

### 검증
- 실행한 명령과 결과.
```

Use this selection format only after the review content exists:

```markdown
## 리뷰 선별

### 반영
- 항목과 이유.

### 보류 / 스킵 / 별도 Issue
- 항목과 이유.

### 다음 수정
- 적용할 커밋 범위.
```

## Current Loop Queue

Default next loops after PR #72 Track 2 regime-split strategy spec on
2026-06-17 KST:

1. Hard stop: Track 1 tournament live swap approval. Latest dry-run produced
   four quote-validated BSC buy orders for COAI, LAB, SKYAI, and TAG with total
   planned notional about 23.51 USDT. Before live execution, require
   explicit user approval, BNB gas confirmation, live cap selection, and the
   exact command confirmation phrase.
2. Manual gate: Track 1 live registration status. If not already registered,
   live registration requires explicit approval and should be completed before
   the live trading window.
3. Manual gate: final public agent URL or hosting choice. The read-only endpoint
   can run locally, but a real public URL still requires an external hosting
   decision before BNB Agent SDK live registration and final DoraHacks
   submission.
4. Manual gate: run and archive final submission evidence bundle with the real
   public agent URL and final wallet address after those values are confirmed.
5. Parked hard stop: BNB Agent SDK live identity registration. Dry-run runbook
   and endpoint payload generation are complete; live registration still
   requires final agent URL, optional SDK install, wallet funding,
   `PRIVATE_KEY`, `WALLET_PASSWORD`, and explicit approval in the current
   thread.
6. Manual gate: DoraHacks final form submission. Use the registered BSC wallet
   address and local evidence artifact, then submit Track 2 through the Add
   option. Track 2 package now includes a non-executing regime strategy spec:
   up-channel long-bias, down-channel short-bias, and neutral transition lanes
   using support line, trend angle, Supertrend, Ichimoku-lite cloud, and volume
   impulse reasons.
7. Research follow-up: validate the leveraged 10-minute volume impulse
   backtester with real 10-minute market data. PR #60 intentionally preserved
   the existing Track 1 and Track 2 files and added only a non-executing
   research backtester; PR #68 added a 100-case deterministic parameter sweep,
   and PR #70 moved the default leverage assumption to 80x based on fixture
   max drawdown of about 22.56%. Fixture sweep results are method validation
   only. It still needs a real 10-minute CSV or a separate intraday data source
   before it can inform competition strategy decisions.
