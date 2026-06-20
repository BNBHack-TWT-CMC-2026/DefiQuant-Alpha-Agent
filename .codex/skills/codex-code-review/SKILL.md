---
name: codex-code-review
description: Review local diffs, commits, or GitHub PRs without relying on external review services. Use when the user asks for code review, PR review, review current changes, review before commit, review after PR creation, security-sensitive review, or wants review findings recorded in GitHub according to this repository's Korean Issue/PR workflow.
---

# Codex Code Review

Use this skill to perform a focused code review of local changes, commits, or a
GitHub PR. The goal is to find actionable defects, risks, missing tests, and
unsafe behavior, then record the review in the repository workflow when needed.

## Hard Rules

- Start from a code-review stance: findings first, ordered by severity.
- Do not invent issues. If no issue is found, say so and name residual risk.
- Do not use external paid review services unless the user explicitly asks.
- Do not put tool names, internal plugin names, automatic signatures, secrets,
  wallet passwords, private keys, API secrets, or seed phrases in GitHub
  artifacts.
- Write GitHub Issue, PR, review, and comment text in Korean.
- For this repo, treat wallet, signing, mainnet, private key, CMC API, TWAK,
  and BNB execution paths as security-sensitive.

## Scope Selection

Identify the review scope before reading code.

- PR review: use `gh pr view`, `gh pr diff`, and checks for that PR.
- Current branch review: compare against `origin/main` or the branch base.
- Pre-commit review: inspect `git diff` and `git diff --staged`.
- Commit review: inspect `git show <sha>` or `git diff <base>..<head>`.

Prefer these commands:

```powershell
git status --short
git diff --stat
git diff
git diff --staged
gh pr view <number> --json number,title,state,headRefName,baseRefName,statusCheckRollup
gh pr diff <number>
gh pr checks <number>
```

Use `rg` first for searches when available; otherwise use PowerShell search
commands.

## Review Axes

Review in these six passes. Keep the final answer concise; do not expose every
scratch note.

1. Correctness
   - behavioral regressions
   - wrong assumptions
   - edge cases
   - API contract mismatches

2. Simplicity
   - unnecessary complexity
   - duplication that causes real maintenance risk
   - abstractions that hide important behavior

3. Tests
   - missing tests for changed behavior
   - tests that only cover fixtures while production paths differ
   - assertions too weak to catch the likely failure

4. Silent failure
   - swallowed errors
   - empty outputs treated as success
   - dry-run/live-run confusion
   - partial external-command failure

5. Types and data model
   - invalid states representable in models
   - optional values used unsafely
   - parsing assumptions not defended
   - config schema drift

6. Security and operations
   - secrets in tracked files or logs
   - wallet/password/private-key exposure
   - mainnet actions without explicit approval
   - quote-only vs execution ambiguity
   - rate limits, paid API usage, and irreversible transactions

## Project-Specific Checks

For defiQuant, always check these when relevant:

- CMC REST and Agent Hub data should be read-only inputs.
- Track 2 Skill must not execute trades or mutate wallet state.
- TWAK live execution must be impossible by accident; dry-run/quote-only should
  be explicit and default-safe.
- BSC token swaps should use verified contract addresses, not ambiguous symbols.
- Real execution should use actual wallet balances, not fixture or assumed cash.
- Registration and trading deadlines must be stated with concrete UTC/KST dates.
- `.env` must remain ignored and must never be staged.
- GitHub text must follow the repository Git workflow in `.codex/AGENTS.md`.

## User-Facing Output

For user-facing review summaries:

```markdown
**발견 사항**
- [심각도] path:line - 문제, 영향, 권장 수정.

**열린 질문**
- 질문 또는 가정. 없으면 `없음`.

**남은 위험**
- 검증하지 못한 부분 또는 운영상 남는 위험.

**검증**
- 확인한 명령과 결과.
```

Severity labels:

- Critical: exploitable security issue, fund loss, irreversible mainnet action,
  broken core workflow.
- Major: likely bug, incorrect external integration, missing required guardrail.
- Minor: maintainability, unclear docs, weak tests with limited blast radius.

If no issues:

```text
발견 사항 없음.
남은 위험: ...
검증: ...
```

## GitHub PR Review Sequence

When reviewing a GitHub PR, use this sequence exactly:

1. Confirm PR number and repository.
2. Gather PR metadata, changed files, patch, and check status.
3. Perform the six review passes before writing any GitHub review comment.
4. Post the actual review content as its own PR comment titled `코드 리뷰`.
   This comment must include `발견 사항`, `열린 질문`, `남은 위험`, and
   `검증`. If no issue is found, say `발견 사항 없음` directly and name the
   residual risk.
5. Do not use the review comment as a selection summary. Review content and
   selection are separate artifacts.
6. If fixes are needed, post a second PR comment titled `리뷰 선별` before
   editing. State which feedback is accepted, deferred, skipped, or split into
   another Issue, and why.
7. If feedback is outside the PR scope, create a separate Issue and reference
   the PR number.
8. Do not mention internal tool names.

PR review comment template:

```markdown
## 코드 리뷰

### 발견 사항
- [심각도] path:line - 문제, 영향, 권장 수정.

### 열린 질문
- 없음.

### 남은 위험
- 남은 위험.

### 검증
- 실행한 명령 또는 확인한 결과.
```

If no issue is found:

```markdown
## 코드 리뷰

### 발견 사항
- 발견 사항 없음.

### 열린 질문
- 없음.

### 남은 위험
- 남은 위험.

### 검증
- 실행한 명령 또는 확인한 결과.
```

Review selection comment template:

```markdown
## 리뷰 선별

### 반영
- 항목과 이유

### 보류 / 스킵 / 별도 Issue
- 항목과 이유

### 다음 수정
- 적용할 커밋 범위
```

## Fix Workflow

If the user asks to fix review findings:

1. Ensure the PR already has a `코드 리뷰` comment with the actual findings.
2. Comment on the PR or Issue with accepted/skipped items before editing.
3. Make focused changes only for accepted items.
4. Run at least:

```powershell
uv run pytest
uv run ruff check
```

5. Run `.\scripts\check.ps1` when behavior, typing, or shared tooling changed.
6. Commit with a Korean Conventional Commit message, e.g.
   `fix: TWAK 토큰 주소 매핑 적용`.
7. Keep unrelated changes out of the commit.
