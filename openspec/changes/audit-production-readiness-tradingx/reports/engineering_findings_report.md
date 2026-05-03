# Engineering Findings Report

Audit date: 2026-05-03

Scope: local TradingX paper-only appliance, OpenSpec audit change
`audit-production-readiness-tradingx`.

## Critical

### C1. Live mode could be enabled without explicit Gate 4 approval

- Severity: Critical
- Status: confirmed bug, fixed now
- Reference: `src/tradingx/config.py`, `src/tradingx/live_probe_governance.py`,
  `schemas/quant/authority_boundary.schema.json`,
  `tests/unit/test_config.py`
- What was wrong: live enablement previously depended on technical flags and
  credentials, but not explicit operator acknowledgement or durable Gate 4
  approval evidence.
- Why it matters: this violated the top safety invariant that live trading must
  remain disabled and fail-closed until explicit Gate 4 sign-off.
- Reproduce/verify: the added red tests
  `test_resolve_broker_mode_blocks_without_gate4_signoff` initially showed a
  technically ready live config was allowed. After the fix, the same config is
  blocked with `operator_signoff_missing`, `gate4_checklist_missing`, and
  `gate4_approval_artifact_missing` unless a schema-valid durable approval
  artifact is configured. A follow-up regression test now proves that ad hoc
  JSON missing required `authority_boundary` fields is rejected.
- Suggested fix: implemented process-env acknowledgement controls
  `TRADINGX_GATE4_OPERATOR_SIGNOFF` and `TRADINGX_GATE4_CHECKLIST_APPROVED`,
  added `TRADINGX_GATE4_APPROVAL_FILE` durable authority-boundary evidence,
  validate that artifact against `authority_boundary.schema.json`, allow
  checklist evidence in the closed-world schema and builder, require non-empty
  checklist evidence for Gate 4, and reflect both acknowledgement and artifact
  status in safe summaries and Control Center posture.
- Tests: `tests/unit/test_live_enablement.py`,
  `tests/unit/test_config.py`, `tests/unit/test_data.py`,
  `tests/unit/test_risk.py`, full `./scripts/validate`.

## High

### H1. Concurrent signed web writes could race through idempotency

- Severity: High
- Status: confirmed bug, fixed now
- Reference: `src/tradingx/web/security.py:139`,
  `src/tradingx/web/security.py:250`, `tests/unit/test_web_security.py:182`
- What was wrong: the authorizer only wrote the idempotency record after the
  action completed, leaving a window where two same-key signed writes could both
  authorize.
- Why it matters: a local write action such as service start/stop or paper
  cycle execution could be duplicated under concurrent requests.
- Reproduce/verify: the added red test authorizes a request and immediately
  retries the same signed request before storing a response. It previously
  authorized again; it now returns 409 pending.
- Suggested fix: implemented an atomic pending reservation with `open("x")`,
  atomic temp-file replacement for completed records, replay only for completed
  matching records, fail-closed pending/corrupt/conflict handling, and
  preservation of the original reservation timestamp.
- Tests: `tests/unit/test_web_security.py`, full `./scripts/validate`.

### H2. Local `.env` has web write mode enabled

- Severity: High
- Status: confirmed environment risk, not changed
- Reference: redacted `config-summary` output; `.env.example:6`
- What is wrong: this local environment reports `web_write_mode_enabled=true`
  and signing configured, while docs and defaults expect write mode disabled
  unless explicitly testing local writes.
- Why it matters: write-capable local UI/API posture increases blast radius if
  the local signing secret or browser session is misused.
- Reproduce/verify: `uv run tradingx config-summary --env-file .env` reports
  write mode enabled without printing secret values.
- Suggested fix: operator should keep write mode disabled by default and enable
  only for bounded signed local tests.
- Tests that should cover it: config posture tests already cover defaults;
  add an operator preflight check that warns on write mode outside explicit test
  sessions.

## Medium

### M1. Gate 3 evidence is not ready

- Severity: Medium
- Status: confirmed readiness gap
- Reference: generated `gate3-report` criteria
- What is wrong: readiness is pending with `0 trades / 0 days`; recovery drill,
  SMTP drill, slippage, hit-rate, Sharpe, and replay evidence are pending.
- Why it matters: the project cannot support unattended paper promotion review
  without this evidence.
- Reproduce/verify: run `uv run tradingx gate3-report --env-file .env
  --paper-artifact-root artifacts --validation-artifact-root
  artifacts/audit-production-readiness/validation`.
- Suggested fix: run bounded paper operation long enough to produce paper
  history, then rerun Gate 3 readiness and package generation.
- Tests that should cover it: gate evidence tests and promotion package tests.

### M2. Gate 3 decision report cannot be generated from current artifacts

- Severity: Medium
- Status: confirmed command failure
- Reference: `src/tradingx/reporting.py:103`
- What is wrong: `decision-report --gate 3` raises `ValueError` because no gate
  validation reports are available.
- Why it matters: gate review packet generation is blocked until validation
  reports exist.
- Reproduce/verify: run `uv run tradingx decision-report --gate 3
  --validation-artifact-root artifacts/audit-production-readiness/validation
  --paper-artifact-root artifacts`.
- Suggested fix: produce Gate 1/2/3 validation report artifacts before decision
  report generation, or emit a structured pending report instead of a traceback.
- Tests that should cover it: CLI error-shape test for missing validation
  reports.

### M3. Scheduler-launched market days do not expose a heartbeat cap

- Severity: Medium
- Status: suspected operational risk
- Reference: `src/tradingx/scheduler.py:162`, `src/tradingx/scheduler.py:247`
- What is wrong: scheduler runs each launched market day with
  `max_heartbeats=None`; the scheduler itself can be bounded by
  `max_scheduled_days`, but the daily heartbeat count is not directly bounded
  through the CLI.
- Why it matters: audit and rehearsal runs need explicit stop conditions that
  are easy to verify.
- Reproduce/verify: inspect `run-market-scheduler --help` and scheduler code.
- Suggested fix: add a scheduler CLI `--max-heartbeats-per-day` or equivalent
  bounded rehearsal mode.
- Tests that should cover it: scheduler lifecycle tests with max scheduled days
  and heartbeat cap.

### M4. Recovery drill failure evidence is too opaque

- Severity: Medium
- Status: suspected evidence-quality risk
- Reference: `src/tradingx/web/runtime.py:929`
- What is wrong: recovery drill catches all exceptions and records a generic
  failure message.
- Why it matters: later review cannot distinguish missing credentials, broker
  outage, missing artifacts, or an internal bug without separate logs.
- Reproduce/verify: inspect `run_recovery_drill`; real drill not run because it
  may touch broker-backed controller paths.
- Suggested fix: record sanitized exception type/reason code while preserving
  secret redaction.
- Tests that should cover it: recovery drill tests for missing credentials and
  broker failure error shapes.

## Low

### L1. Frontend build emits a large chunk warning

- Severity: Low
- Status: confirmed
- Reference: `npm --prefix webapp run build`
- What is wrong: Vite reports a 732 kB minified JS chunk.
- Why it matters: slower initial Control Center loads on low-power operator
  devices.
- Suggested fix: consider code splitting after safety-critical work.
- Tests that should cover it: build budget check if performance becomes a gate.

### L2. External integrations were not verified

- Severity: Low
- Status: not verified
- Reference: redacted config summaries and skipped smoke test
- What is wrong: Postgres, Telegram, SMTP delivery, live Alpaca, and market-hour
  paper smoke checks were not verified in this local run.
- Why it matters: these are needed before unattended paper or later promotion.
- Suggested fix: rerun in an environment with DSN/alert transport configuration
  and regular market hours.
- Tests that should cover it: gated integration/smoke tests with explicit env
  markers.

## Commands Run

- `git status --short --branch`: initial clean branch; final code changes and
  OpenSpec files are uncommitted.
- `openspec init`, `openspec new change audit-production-readiness-tradingx`,
  `openspec validate audit-production-readiness-tradingx --strict`: passed.
- Focused pytest red run: 6 expected failures.
- Focused pytest after initial fixes: 48 passed.
- Focused pytest after review fixes: 52 passed.
- User-listed focused pytest after review fixes: 34 passed.
- Review contract-focused pytest: 53 passed.
- `./scripts/validate-fast` after review fixes: 166 passed, 12 warnings.
- `./scripts/validate-fast`: 164 passed, 12 warnings.
- `npm --prefix webapp test`: 108 passed.
- `npm --prefix webapp run build`: passed with Vite chunk warning.
- `uv build`: passed.
- `./scripts/validate`: 1459 passed, 98 skipped, 14 warnings; smoke skipped
  because regular US market hours were closed.
- `config-summary` and `live-disable-status`: live disabled, paper-only true,
  no secrets printed.
- Local web server on `127.0.0.1:8766` with write mode forced off: read APIs
  passed; unsigned POST rejected with 403.
- Gate/evidence commands: evidence empty; Gate 3 package pending; replay
  pending; SMTP alert drill pending/unconfigured; Gate 3 decision report failed
  because no validation reports exist.

## Skipped Or Not Verified

- Visual browser UI inspection: Browser Use local `tab.goto()` timed out before
  the tab left `about:blank`.
- Real paper order submission and paper smoke test: not verified because
  regular US market hours were closed, and the audit avoided unbounded/external
  broker actions.
- Postgres integration: not verified without `TRADINGX_TEST_POSTGRES_DSN`.
- SMTP/Telegram delivery: not verified; transports not configured.
- Live trading: intentionally not verified beyond fail-closed readouts.

## Browser/UI Notes

The Control Center backend served the built frontend and APIs on `127.0.0.1:8766`
with write mode disabled. API posture showed fail-closed live status and missing
Gate 4 approvals. Frontend unit tests and production build passed. Visual UI
navigation through the in-app browser was not verified due to Browser Use local
navigation timeout.

## Assumptions Made

- Real credential values were not inspected or reported.
- Local `.env` summaries are safe because the application redacts secrets.
- Existing process on port 8765 belongs to the user and was not stopped.
- Paper broker submission flows were reviewed through code/tests instead of
  run against the broker during closed market hours.
