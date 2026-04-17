---
id: RUNBOOK-0001
title: Session recovery
version: 1.1.1
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: RUNBOOK-0001@1.1.0
superseded_by: null
author_session: SESS-0000-00-00-000
---

# Session Recovery Runbook

**Purpose.** This runbook is executed when a new session discovers
evidence that a prior session was abandoned (interrupted before its
end-of-session ritual completed). It reconstructs what the prior
session did, decides whether the work is safely resumable, and
records the recovery in an auditable form.

**When to follow this runbook.** A session agent MUST execute this
runbook if, during the session-start ritual, it detects any of:

- `docs/handover/STATE.md` names an active session whose timestamp
  is more than 2 hours old and no corresponding session handover
  file exists with an `ended` timestamp.
- A session handover file exists with `session_status: abandoned`
  that has not yet been processed by a subsequent session.
- The most recent session handover has `session_status: open` but
  no corresponding successor session exists.
- A `WIP` commit exists with a `# SESSION_HANDOFF` marker and no
  corresponding open handover file.

**Authority.** This runbook is authoritative for the recovery
sequence. If any other document contradicts it, halt and raise a
Stop-and-Ask.

---

## Principles of safe recovery

1. **Observe before modify.** The recovery agent gathers information
   about prior-session state BEFORE making any modifications to
   existing files. Gathering includes reading files and running
   read-only commands like `git status` and `git log`.
2. **Creation is not modification.** Creating new files (such as the
   recovery handover document itself) is NOT a violation of the
   observation phase. The freeze applies to EXISTING files produced
   by the abandoned session, not to files the recovery agent creates
   as part of the recovery record.
3. **Bias toward asking.** When in doubt, classify the situation as
   Category B (requires clarification) rather than guessing.
4. **Leave a trace.** Recovery Categories A-C always produce a
   committed recovery artifact (a new document in the `recovery/`
   subdirectory plus any required updates to STATE.md, SESSION_LOG,
   and INDEX). Category D is the only exception: the agent preserves
   observations out-of-band and waits for explicit operator
   instruction before making repository writes.

---

## Phase 1 — Observation (read-only on abandoned-session outputs)

The recovery agent performs only read-only operations on files
produced by the abandoned session. The recovery agent MAY create
new files in the recovery workspace as part of this phase.

### Step 1.1 — Identify the abandoned session

Read `docs/handover/STATE.md` to find the last-recorded active
session. Read the last 5 session handover files in
`docs/handover/SESSIONS/` sorted by filename. Identify which session
is abandoned based on the trigger that invoked this runbook.

Record the abandoned session ID. Call it `SESS-<abandoned_id>`.

### Step 1.2 — Collect the evidence

Run (read-only):

```
git status
git log --oneline -20
git diff HEAD
grep -rn 'SESSION_HANDOFF' src/ tests/ docs/ || true
grep -rn 'IN_PROGRESS' src/ tests/ docs/ || true
```

Record:

1. Uncommitted working-tree changes.
2. Recent commit history (look for WIP commits).
3. Files containing `# SESSION_HANDOFF` or `IN_PROGRESS` markers.
4. The abandoned session's handover file if it exists (even if
   partially written).
5. The abandoned session's STATE.md entry if still present.

### Step 1.3 — Create the recovery workspace

Create (this is NEW file creation, not modification of abandoned-
session files):

- `docs/handover/recovery/SESS-<current_id>-recovering-SESS-<abandoned_id>.md`

This is a scratch document where the recovery agent records its
observations before making any decision. Populate it with the
evidence collected in Step 1.2.

Use front-matter:

```yaml
---
id: RECOVERY-<NNNN>
title: Recovery of SESS-<abandoned_id> by SESS-<current_id>
version: 1.0.0
status: draft
created: <today>
last_amended: <today>
supersedes: null
superseded_by: null
author_session: SESS-<current_id>

session_status: open
recovering_session: SESS-<abandoned_id>
---
```

Note that this document has a `session_status` of `open` (session-
lifecycle) and a `status` of `draft` (artifact-lifecycle) —
distinct fields per constitution Principle VIII.

---

## Phase 2 — Classification

Based on the evidence collected in Phase 1, the recovery agent
classifies the situation into one of four categories. The decision
is made against the recovery workspace document, not yet against
any existing file.

### Category A — Safely resumable

All of:
- Uncommitted changes are confined to a specific file set.
- All validation checks that existed BEFORE the abandoned session
  still pass. Newly-added failing tests are allowed ONLY if they are
  explicitly documented as intentional RED-phase TDD work in the
  abandoned handover, a `# SESSION_HANDOFF` marker, or an
  `IN_PROGRESS` note.
- A clear resume-point marker exists (`# SESSION_HANDOFF` comment,
  IN_PROGRESS tag with file:line reference, or abandoned handover
  with a populated `resume_point` field).
- No modifications to `.specify/memory/constitution.md`, `docs/INDEX.md`,
  or any `status: active` artifact other than session handovers.

### Category B — Requires clarification

Any of:
- Uncommitted changes span unrelated files suggesting the abandoned
  session was mid-refactor.
- Tests that existed before the abandoned session now fail.
- No clear resume-point marker, but work is clearly partially done.
- A strategy-quality gate (Gate 1, 2, 3) was being evaluated when
  the session was abandoned and partial evaluation exists.

### Category C — Broken and should be rolled back

Any of:
- `./scripts/validate` fails for reasons that are NOT limited to
  explicitly documented RED-phase TDD work. Any regression in a
  pre-existing check or test that passed before the abandoned session
  is Category C.
- A `status: active` artifact has been modified in a way the
  recovery agent cannot verify as intentional.
- Uncommitted changes leave the repo in a state that cannot compile
  or pass basic lint checks.
- The abandoned session touched the constitution or INDEX without
  a Sync Impact Report.

### Category D — Catastrophically broken

Any of:
- Secrets may have been exposed (`.env` contents appearing in
  commits or logs).
- Live-trading flags were modified without operator sign-off.
- Financial state (positions, orders, capital) shows evidence of
  tampering or corruption.
- The abandoned session's behavior suggests it acted outside the
  constitution's bounds.

---

## Phase 3 — Recovery action (here the agent may modify existing files)

Phase 3 is where modification of existing files becomes permitted,
because the agent has now finished observation and classification.
Actions are specific to the category.

### Category A actions

1. Use `git stash` or a dedicated `recovery/SESS-<current_id>` branch
   to isolate the current working tree if it is not already
   isolated.
2. Flip the abandoned session's handover `session_status` from
   whatever it is (likely absent or `open`) to `abandoned`. Update
   the `ended` field to the recovery timestamp with a note
   `reconstructed during recovery`.
3. Update STATE.md to reflect that the abandoned session is now
   closed as `abandoned` and the current session is active.
4. The current session proceeds with normal Phase 1+ work, explicitly
   stating in its Session Start Report that it is resuming
   SESS-<abandoned_id>'s work.
5. When the current session ends with the resumed work complete,
   it flips the abandoned session's `session_status` to `completed`
   per the constitution's session-lifecycle rules.

### Category B actions

1. Do NOT modify any of the abandoned session's artifacts.
2. Isolate current working tree on a `recovery/SESS-<current_id>`
   branch.
3. Promote the recovery workspace document from `status: draft` to
   `status: active` and set its `session_status` to `handed_forward`
   with a detailed resume_point.
4. Update STATE.md: mark abandoned session `session_status` as
   `abandoned`, mark current session `session_status` as `open`,
   record that clarification is pending.
5. Raise a Stop-and-Ask describing what was found and what the
   operator needs to decide.
6. Wait for operator response before proceeding.

### Category C actions

1. Do NOT modify any of the abandoned session's artifacts until the
   operator approves the rollback plan.
2. Create a proposed rollback plan in the recovery workspace
   document (specific commits to revert, specific files to restore
   from git history).
3. Raise a Stop-and-Ask presenting the rollback plan.
4. On operator approval, execute the rollback, update STATE.md,
   mark the abandoned session `session_status` as `abandoned` with a
   note, and begin new work on a fresh branch.
5. On operator rejection, fall back to Category B treatment.

### Category D actions

1. STOP IMMEDIATELY.
2. Do NOT modify anything.
3. Raise a CRITICAL Stop-and-Ask immediately via Telegram AND the
   emergency SMTP channel.
4. Wait for explicit operator instruction before any further action.

---

## Phase 4 — Close the recovery record

Categories A-C only. Category D does NOT enter this phase; it stops
after operator notification and waits for explicit instruction before
any repository write.

1. Commit the recovery workspace document and any related changes.
   Conventional-commits message:
   ```
   recovery(session): reconstruct SESS-<abandoned_id>, action=<A|B|C|D>
   ```
2. Update `docs/handover/SESSION_LOG.md` with a one-line entry:
   ```
   <timestamp> | SESS-<current_id> | recovery | <session_status> | Recovered SESS-<abandoned_id>, category <A|B|C|D>
   ```
3. Update `docs/INDEX.md` with the RECOVERY-<NNNN> entry in the
   "Recovery records" section (per-row, as recovery records are
   rare and individually significant).
4. If Category A: continue with normal Phase 1 of work.
   If Category B: wait for operator response.
   If Category C: wait for rollback approval.

---

## Fields that MUST appear in every recovery record

Every recovery workspace document MUST include:

- `recovering_session`: the abandoned session ID.
- `category`: A, B, C, or D (once classified).
- `evidence`: a summary of the observations from Phase 1.
- `resume_point`: best-effort based on `SESSION_HANDOFF` markers and
  IN_PROGRESS tags, or explicitly "UNKNOWN" if none found.
- `action_taken`: the specific Phase 3 actions executed.
- `operator_notification`: whether and how the operator was
  notified.

---

## Why Step 1 permits file creation but forbids file modification

Version 1.0.0 of this runbook contained a logical contradiction:
Step 1 said "do not modify any files" while later steps required
creating the recovery handover file. External review identified
this as an impossible sequence.

Version 1.1.0 resolves the contradiction by distinguishing
**modification of files produced by the abandoned session** (which
is forbidden until classification completes, because those are
potential evidence) from **creation of new files that record the
recovery process** (which is the entire point of observation).

The operational principle: during observation, the agent treats
the abandoned session's output as a crime scene — you look, you
photograph, you take notes — but you do not disturb. The recovery
workspace document is your notebook, not part of the scene.

Once classification completes in Phase 2, the agent moves to Phase
3 and modifications become permitted, scoped by category.
