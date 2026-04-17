# Session handover directory

This directory contains one file per session, named by session ID.

## File naming

`SESS-<YYYY-MM-DD>-<NNN>.md`

Example: `SESS-2026-04-22-001.md` for the first session on April 22, 2026.

## Required front-matter

Every session handover document carries TWO lifecycle fields:

- `status` — the versioned-artifact lifecycle per constitution
  Principle VIII: `draft | active | superseded | deprecated | rejected`.
- `session_status` — the session lifecycle: `open | completed |
  handed_forward | abandoned`.

These two fields are distinct and MUST NOT be conflated. The constitution
v3.0.0 introduced the split to resolve a schema collision identified
in external review.

```yaml
---
id: SESS-2026-04-22-001
title: Session handover — SESS-2026-04-22-001
version: 1.0.0
status: active
created: 2026-04-22
last_amended: 2026-04-22
supersedes: null
superseded_by: null
author_session: SESS-2026-04-22-001

# Session-specific fields:
session_status: completed
agent: claude-opus-4-7
started: 2026-04-22 09:14:22 UTC
ended: 2026-04-22 11:47:08 UTC
phase: 3 — quality scaffolding
branch: main
predecessor: SESS-2026-04-21-003
successor: null
resume_point: null
---

# Session handover — SESS-2026-04-22-001
```

## Session summary (body of the handover file)

Every handover file MUST include these sections:

### Objectives

What was the session's plan?

### Outcomes

What actually happened? Link to commits, ADRs, and artifacts produced.

### Tests run

What tests were executed, and what were the results?

### ADRs written or modified

List each with id and purpose.

### Open items left for the next session

If `session_status` is `open` or `handed_forward`, this section is
mandatory. If `session_status` is `completed`, write "None."

Be specific enough that the next agent can resume without rediscovering
context. Examples of good entries:

- File `src/data/alpaca_adapter.py:142` has a `# SESSION_HANDOFF`
  marker. The next session needs to implement the
  `_parse_bar_response` method. Tests in
  `tests/unit/test_alpaca_adapter.py::test_bar_response_parsing`
  are currently skipped with reason `SESSION_HANDOFF`.
- Task T0042 in `specs/001-data-ingestion/tasks.md` is in progress.
  The first two subtasks are done; the third (writing the smoke test
  against the Alpaca paper API) is not started.
- Open question OPEN-0007 is awaiting operator response. Do not
  proceed with Phase 5 until answered.

### Blockers or risks identified this session

List anything the operator should know about: surprises, suspicious
backtest results, API quirks, dependency issues, regulatory concerns
that came up, things added to `UNVERIFIED_CLAIMS.md`.

### Stop-and-Ask items raised

List any OPEN-<NNNN> questions raised during this session. Example:

- OPEN-0007 — Emergency-alert channel SMTP credentials verification
  (operator to confirm SMTP config works; initial round-trip test is
  part of Gate 3 acceptance criteria).

## Constitution compliance self-check

The agent MUST self-check against these before ending the session.
The list covers all ten principles — any unchecked box means the
session MUST NOT close with `session_status: completed`.

**Caveat on self-checks (Principle IV):** the agent's own review of
its own work is not strong evidence. Self-checks catch obvious
violations but miss structural and semantic issues that external
review finds easily. If a session produced material artifacts
(new ADRs, constitution amendments, validation reports), the agent
SHOULD mark the session as `open` pending operator or independent
review rather than self-certifying as `completed`.

- [ ] Tier 1 (survival and integrity) was not sacrificed for Tier 2
      or Tier 3 this session (Principle I).
- [ ] All hard pre-trade constraints (liquidity, price,
      concentration, intraday-margin, stale-data, stale-state,
      kill-switch, live-mode defense-in-depth) are enforced in the
      risk module (Principle I).
- [ ] No claim of "working" or "profitable" was made without
      verifiable evidence (Principle II).
- [ ] All production code in this session was written after a
      failing test existed (Principle III).
- [ ] No `TODO` / `FIXME` / `XXX` / `HACK` tags were left in `src/`
      on the working branch; no silently-swallowed exceptions; no
      fake metrics; no unmarked mock/stub data (Principle IV).
- [ ] All numeric constants representing market, exchange, or
      regulatory facts carry a `# source:` comment
      (Principle IV, anti-hallucination).
- [ ] All external claims (APIs, products, regulations) are either
      sourced or marked `[UNVERIFIED]` and logged in
      `UNVERIFIED_CLAIMS.md` (Principle IV).
- [ ] Any complexity introduced was justified in an ADR; ML added
      only where it beat simpler baselines net of costs
      (Principle V).
- [ ] No runtime self-modification code was introduced; no retraining
      of models that affect live positions; no runtime mutation of
      risk limits or strategy parameters (Principle VI).
- [ ] Live trading remained disabled at all four safety layers
      (Principle VII).
- [ ] Every material decision this session produced an ADR or other
      versioned artifact with correct front-matter (Principle VIII).
- [ ] The `status` field (artifact lifecycle) and `session_status`
      field (session lifecycle) are distinct in every handover
      document written or modified this session (Principle VIII).
- [ ] `docs/INDEX.md` was updated for every artifact status change
      (Principle VIII).
- [ ] No technical details leaked into `spec.md`; no high-level
      business content crept into `plan.md` beyond framing
      (Principle IX).
- [ ] All three interface scopes (Telegram / Grafana / local web
      app) remained within their bounds; no Telegram parameter
      editing; no cloud control plane; no native desktop or mobile
      apps (Principle X).
- [ ] No risk controls were weakened or bypassed to make something
      work. Any such moment was escalated via Stop-and-Ask.

If any box is unchecked, the agent explains why in this section AND
sets the session_status to `open` or `handed_forward` rather than
`completed`.

## Closing a session as completed

A session may close as `session_status: completed` only when ALL of
the following hold:

- All tests pass.
- All work planned for the session is finished.
- No `IN_PROGRESS` markers remain in modified files.
- No new `WIP` commits are left uncompleted.
- `docs/handover/UNVERIFIED_CLAIMS.md` has no new unreviewed entries
  from this session.
- `docs/handover/STATE.md` reflects the completed state.
- The constitution compliance self-check above has no unchecked
  boxes.

If any of these fails, session_status is `open` or `handed_forward`
and a `resume_point` is required.

## Closing a session as open or handed_forward

When a session ends with work unfinished:

- `session_status: open` — the work continues in a follow-up session
  on the same branch, no specific successor identified yet.
- `session_status: handed_forward` — the work is explicitly being
  passed to a named successor session (uncommon; usually used when
  one agent explicitly hands off to another with context).

In both cases, `resume_point` is required and must be specific enough
that the successor can pick up without rediscovering context.

## Closing a session as abandoned

The session agent does NOT mark its own session as abandoned. A
session is marked abandoned only by a SUBSEQUENT session running the
recovery runbook at `docs/operations/session_recovery.md`. If the
agent detects that it is about to be unable to complete the end-of-
session ritual (e.g., context exhausted, crash imminent), it
attempts to write the handover with session_status `open` and as
much resume information as possible before failing.
