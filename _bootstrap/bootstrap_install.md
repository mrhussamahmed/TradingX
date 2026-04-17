---
id: RUNBOOK-0002
title: Bootstrap install
version: 1.0.1
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: RUNBOOK-0002@1.0.0
superseded_by: null
author_session: SESS-0000-00-00-000
---

# Bootstrap Install Runbook

**Purpose.** This runbook defines exactly how the `_bootstrap/` folder
is converted into a live, self-consistent repository during Phase 0.
It exists because the constitution and handover templates reference
file paths (`scripts/check_index.py`, `docs/handover/STATE.md`,
`./scripts/validate`, etc.) that do not exist at the moment the coder
AI begins Phase 0. Without a deterministic install procedure, the
session-start rituals would depend on files that don't exist, which
is the "bootstrap not self-hosting" defect caught in external review.

**When to follow this runbook.** Exactly once, at the start of the very
first coder session (Phase 0). After this runbook has run to
completion, `_bootstrap/` is deleted and this file lives at
`docs/operations/bootstrap_install.md` as historical reference.

**Authority.** This runbook is authoritative for the bootstrap install
sequence. If any other document contradicts it, halt and raise a
Stop-and-Ask.

---

## Prerequisites

Before starting, the coder AI confirms:

1. The current working directory is the project root (`TradingX/`).
2. `_bootstrap/` exists and contains these required bootstrap files.
   Ignore OS/editor metadata files such as `.DS_Store`,
   `Thumbs.db`, and AppleDouble `._*` sidecar files when checking
   this prerequisite:
   - `constitution.md`
   - `project_brief.md`
   - `implementation_constraints.md`
   - `INDEX.md`
   - `SESSIONS_README.md`
   - `session_recovery.md`
   - `bootstrap_install.md` (this file)
3. The repository is a git repository (`git init` has been run or
   `specify init --here` will handle it).
4. Nothing else exists in the project root except standard git files,
   `README.md` if any, `_bootstrap/`, and ignorable OS/editor
   metadata files such as `.DS_Store`. Unexpected non-hidden project
   files are a Stop-and-Ask.
5. Operator has provided a valid starting session ID in the form
   `SESS-<YYYY-MM-DD>-<NNN>`. If not, the coder AI generates one based
   on the current UTC date.

If any prerequisite fails, the coder AI halts and raises a
Stop-and-Ask rather than continuing.

---

## Sequence

The sequence is deterministic. Steps are executed in order. A step is
complete only when the stated outcome is verified. If a step fails,
the coder AI halts and raises a Stop-and-Ask; it does NOT improvise.

### Step 1 — Install Spec Kit and initialize

```
specify init --here --ai claude
```

Outcome: Spec Kit's default directory layout exists at the project
root. Spec Kit creates `.specify/memory/constitution.md` as its
canonical constitution path (verified against Spec Kit source
2026-04-17 — see `docs/archive/implementation_constraints.md` for
the source citation). All references throughout this project's
documents use this path exactly.

### Step 2 — Install Superpowers plugin (limited skill set)

Install the Superpowers plugin and enable ONLY these skills:

- `brainstorming`
- `test-driven-development`
- `systematic-debugging`
- `requesting-code-review`
- `subagent-driven-development`

Disable all other Superpowers skills to control token cost and surface
area.

### Step 3 — Create the target directory structure

Create (as empty directories with `.gitkeep` files where needed):

```
docs/
  INDEX.md                            ← placed in Step 4
  adrs/
    templates/
  handover/
    STATE.md                          ← placed in Step 5
    SESSION_LOG.md                    ← placed in Step 5
    OPEN_QUESTIONS.md                 ← placed in Step 5
    UNVERIFIED_CLAIMS.md              ← placed in Step 5
    SESSIONS/
      README.md                       ← placed in Step 4
  operations/
    session_recovery.md               ← placed in Step 4
    bootstrap_install.md              ← placed in Step 4
  validation/
scripts/
  check_index.py                      ← written in Step 6
  validate                            ← written in Step 6
src/
tests/
  unit/
  integration/
  smoke/
config/
  capital/
  broker/
  risk/
  schemas/
```

Plus the project_brief and implementation_constraints in a persistent
location where the coder AI can find them during Phase 1:

```
docs/archive/project_brief.md                  ← placed in Step 4
docs/archive/implementation_constraints.md     ← placed in Step 4
```

### Step 4 — Move the bootstrap files to their final locations

Move, do NOT copy (so `_bootstrap/` ends up empty):

| From | To |
|---|---|
| `_bootstrap/constitution.md` | `.specify/memory/constitution.md` |
| `_bootstrap/INDEX.md` | `docs/INDEX.md` |
| `_bootstrap/SESSIONS_README.md` | `docs/handover/SESSIONS/README.md` |
| `_bootstrap/session_recovery.md` | `docs/operations/session_recovery.md` |
| `_bootstrap/bootstrap_install.md` | `docs/operations/bootstrap_install.md` |
| `_bootstrap/project_brief.md` | `docs/archive/project_brief.md` |
| `_bootstrap/implementation_constraints.md` | `docs/archive/implementation_constraints.md` |

**Special case: replacing Spec Kit's generated constitution template.**
Step 1 creates `.specify/memory/constitution.md` as a generated
template. A plain `git mv` into an existing destination will fail, so
the constitution move is a replace sequence:

1. Delete the generated template at `.specify/memory/constitution.md`.
2. Move `_bootstrap/constitution.md` into that exact path (prefer
   `git mv` after deleting the generated file).
3. Verify the resulting file at `.specify/memory/constitution.md` is
   the bootstrap constitution, not the Spec Kit template.

The `project_brief.md` and `implementation_constraints.md` go to
`docs/archive/` because their purpose is historical: the coder AI
reads them during Phase 1 to feed `/speckit.specify` and
`/speckit.plan`, after which the generated spec and plan become the
live documents and the source briefs are reference material.

After this step, `_bootstrap/` should contain no remaining project
files. Before removing it, delete any ignorable OS/editor metadata
files left behind (for example `.DS_Store` or `._*`). Then remove the
directory:

```
rmdir _bootstrap
```

### Step 5 — Create the handover files

Create as empty-but-structured files:

**`docs/handover/STATE.md`** — starts with the initial state:

```yaml
---
id: STATE-0001
title: Project state
version: 1.0.0
status: active
created: <today>
last_amended: <today>
supersedes: null
superseded_by: null
author_session: <current session ID>
---

# Current project state

- Active session: <session ID>
- Active branch: main
- Active phase: 0
- Last completed gate: none
- Walking skeleton: not yet built
- Live trading enabled: no (disabled at all four layers)

## Pending items

- Phase 0 scaffolding in progress.
- Walking skeleton pending.
- Initial ADRs pending.
```

**`docs/handover/SESSION_LOG.md`** — append-only session log:

```
# Session log

One line per session. Format:
<YYYY-MM-DD HH:MM:SS UTC> | SESS-<id> | <phase> | <session_status> | <summary>

<current timestamp> | SESS-<current id> | 0 | open | Phase 0 bootstrap install started.
```

**`docs/handover/OPEN_QUESTIONS.md`** — empty initial:

```
# Open questions

None at bootstrap. Append new Stop-and-Ask items in reverse
chronological order (newest first).
```

**`docs/handover/UNVERIFIED_CLAIMS.md`** — empty initial:

```
# Unverified claims

Claims requiring operator verification or external source. Each entry:

- Source of the claim
- Date logged
- Why it needs verification
- Responsible session
```

### Step 6 — Write the validation scripts

Two scripts are mandated by the constitution and must exist before
any session-start ritual depends on them.

**`scripts/check_index.py`** — verifies that every file with YAML
front-matter declaring a versioned artifact has a matching entry in
`docs/INDEX.md`, and that every INDEX entry points to a real file
with matching `status` and `version`. Returns non-zero on any mismatch.

**`scripts/validate`** — orchestration script that runs:

1. `check_index.py`
2. `ruff check src/ tests/ scripts/`
3. `black --check src/ tests/ scripts/`
4. `mypy --strict src/`
5. `pytest tests/unit/ tests/integration/`
6. `pytest tests/smoke/` (gated on presence of `.env` with real
   credentials; skipped if absent with a clear message).

Returns non-zero on any failure. Make it executable:

```
chmod +x scripts/validate
```

Write minimum-viable versions of both scripts in Phase 0. They can
be elaborated in later phases but MUST exist and pass in Phase 0 or
Gate 0 cannot be claimed.

### Step 7 — Write initial ADRs

Write at minimum these ADRs in `docs/adrs/`:

- `ADR-0001-language-python-3.11.md`
- `ADR-0002-package-manager-<uv-or-poetry>.md` (coder AI picks)
- `ADR-0003-broker-alpaca.md`
- `ADR-0004-benchmark-spy.md`
- `ADR-0005-stage-progression-1-through-4.md`
- `ADR-0006-emergency-channel-smtp.md`
- `ADR-0007-market-hours-regular-only.md`
- `ADR-0008-walking-skeleton-deliverable.md`

Each ADR uses the standard front-matter from Principle VIII of the
constitution. Each references the constitution section that justifies
the pinned choice.

Also write the generic strategy-evaluation ADR template at
`docs/adrs/templates/strategy_evaluation.md` — the one applied
identically to every strategy candidate in Phase 1. This template
exists to prevent candidate-specific adversarial-check documentation
from creating confirmation bias, per the decision in
`docs/archive/project_brief.md`.

### Step 8 — Update INDEX.md

Update `docs/INDEX.md` with:

- CONST-0001 v3.0.1
- BRIEF-0001 v3.0.0 at `docs/archive/project_brief.md`
- CONSTRAINTS-0001 v1.0.0 at `docs/archive/implementation_constraints.md`
- INDEX-0001 v1.2.1 at `docs/INDEX.md` (self)
- RUNBOOK-0001 v1.1.1 at `docs/operations/session_recovery.md`
- RUNBOOK-0002 v1.0.1 at `docs/operations/bootstrap_install.md` (self)
- STATE-0001 v1.0.0 at `docs/handover/STATE.md`
- All ADR-NNNN entries written in Step 7

### Step 9 — Create the env skeleton and gitignore

Create `.env.example` and `.env.research.example` at the repo root
per the list in `docs/archive/implementation_constraints.md`. Each
variable on its own line with an inline comment explaining what it
is and where to get it.

Create `.env` and `.env.research` as empty placeholders with
comments. The operator fills in real values locally, outside the
session.

Write `.gitignore` that blocks `.env` and `.env.*` but permits
`.env.example` and `.env.research.example`.

### Step 10 — Docker, CI, and packaging skeletons

Create:

- `Dockerfile` — minimum-viable container build for Python 3.11.
- `docker-compose.yml` — local dev with Prometheus + Grafana stubs.
- `.github/workflows/ci.yml` — runs `./scripts/validate` on push
  and pull-request.
- `pyproject.toml` — Python project metadata, dependency list,
  ruff/black/mypy/pytest configuration.

### Step 11 — Build the walking skeleton

Implement the minimum-viable end-to-end paper-trading pipeline per
the Phase 0 walking-skeleton spec in the constitution:

- `src/tradingx/` package with one module per major capability
  (data, execution, portfolio, risk, controller).
- At minimum, enough code for `tests/smoke/test_alpaca_paper_roundtrip.py`
  to pass:
  - Authenticate to Alpaca paper.
  - Fetch an SPY quote.
  - Submit a 1-share paper buy.
  - Wait for fill.
  - Submit a 1-share paper sell.
  - Reconcile final state.
- All code written TDD per Principle III: failing test first, then
  implementation. Smoke test exists before the code that satisfies it.

The smoke test is SKIPPED by `./scripts/validate` if `.env` has no
real Alpaca paper credentials, with a clear message. The test MUST
pass when credentials are present; this is what Gate 0.5 verifies.

### Step 12 — Write the Phase 0 session handover

Write `docs/handover/SESSIONS/<SESSION_ID>.md` with full front-matter
per the constitution's session-lifecycle specification (both `status`
and `session_status` fields). Summarize:

- What was scaffolded.
- What ADR decisions were made and their brief rationales.
- Whether the walking-skeleton smoke test passes (Gate 0.5 status).
- Whether `./scripts/validate` passes without the smoke test (Gate 0
  status).
- What remains open.
- What Phase 1 will do.

If Gate 0 and Gate 0.5 both pass: session_status is `completed`.
Otherwise: session_status is `open`, with a resume point.

### Step 13 — Final commit

Single commit with conventional-commits message:

```
feat(phase-0): bootstrap install, scaffolding, and walking skeleton

Closes Phase 0. Gate 0 passed. Gate 0.5 <passed|pending>.

<brief list of ADR decisions>

Refs: CONST-0001@3.0.1
```

Push only if operator has provided a remote URL; otherwise commit
locally and note in the handover that pushing is pending operator
instruction.

---

## What NOT to do during bootstrap install

- Do NOT attempt any session-start ritual that depends on files not
  yet created. The session start ritual defined in the constitution
  depends on files placed in Steps 4 and 5; the coder AI follows
  THIS runbook on first run, not the session-start ritual.
- Do NOT start Phase 1 work before Phase 0 is signed off by the
  operator.
- Do NOT skip the walking-skeleton step. Phase 0 is not complete
  without it.
- Do NOT re-run this runbook after initial completion.
- Do NOT modify `_bootstrap/` contents during the install. Move
  files atomically (git mv) after clearing the generated Spec Kit
  constitution template at `.specify/memory/constitution.md`.

---

## Contradiction with the session-start ritual (resolved)

The constitution's session-start ritual reads STATE.md, SESSIONS/
handovers, and runs `./scripts/validate`. On the very first session,
none of those files exist yet. This runbook resolves the chicken-
and-egg problem: on the first session, the coder AI follows THIS
runbook instead of the session-start ritual. Once this runbook
completes, all subsequent sessions follow the normal session-start
ritual.

The first-session-exception is only for Phase 0's initial
bootstrap. Every subsequent session — even Phase 0 continuation
sessions if Phase 0 spans multiple sessions — follows the normal
session-start ritual.
