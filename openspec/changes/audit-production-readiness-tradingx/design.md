## Context

TradingX is a Python 3.11 local trading appliance with a FastAPI backend,
Alpaca paper integration, a React/Vite Control Center, local file-backed
artifacts by default, and optional Postgres projections. The current project
documentation describes the system as paper-only, evidence-first, and gated:
live trading must remain fail-closed until explicit Gate 4 sign-off.

The audit is being run on 2026-05-03 from
`/Users/ahmedabd/Desktop/AI Projects/TradingX`.

### Repository Map

- Backend package: `src/tradingx/`
- CLI entry point: `tradingx = tradingx.__main__:main`
- Web backend: `src/tradingx/web/app.py`,
  `src/tradingx/web/runtime.py`, `src/tradingx/web/security.py`
- Web frontend: `webapp/src/`, built by `npm --prefix webapp run build`
- Runtime host and supervisor: `src/tradingx/runtime_host.py`,
  `src/tradingx/supervisor.py`
- Paper runtime/service/scheduler: `src/tradingx/controller.py`,
  `src/tradingx/service.py`, `src/tradingx/scheduler.py`,
  `src/tradingx/automation.py`
- Safety and authorization: `src/tradingx/live_enablement.py`,
  `src/tradingx/authority.py`, `src/tradingx/operator_control.py`,
  `src/tradingx/execution.py`
- Persistence: legacy local artifacts under `artifacts/` and `data/`;
  optional Postgres modules under `src/tradingx/persistence/`
- Evidence and gates: `src/tradingx/gate3.py`,
  `src/tradingx/replay_slippage.py`, `src/tradingx/validation.py`,
  `src/tradingx/promotion.py`
- Tests: `tests/unit`, `tests/contract`, `tests/integration`,
  `tests/smoke`, and `webapp/src/**/__tests__`

### Commands To Record

Audit evidence will record the command, result, and status for:

- `openspec validate audit-production-readiness-tradingx --strict`
- `uv sync --all-groups` if dependencies are missing
- `npm --prefix webapp install` if frontend dependencies are missing
- `uv run tradingx config-summary --env-file .env`
- `uv run tradingx live-disable-status --env-file .env`
- `./scripts/validate-fast`
- `./scripts/validate`
- `npm --prefix webapp test`
- `npm --prefix webapp run build`
- `uv build`
- safe bounded CLI/runtime smoke checks when credentials and market-hours
  constraints allow
- local Control Center backend startup through
  `uv run tradingx web --env-file .env`

### Assumptions

- The audit must not print credential values; environment files may be
  inspected structurally but not copied into reports.
- Real Alpaca paper credentials, market hours, Telegram, SMTP, and Postgres may
  be unavailable. Those checks are recorded as `not verified`, not passing.
- Any automation must be bounded with explicit `--max-*` or equivalent stop
  condition.
- Web write-mode tests may only run locally and must require a signing secret.
- Live trading remains out of scope and must stay disabled.
- Existing user changes must not be overwritten or reverted.

## Goals / Non-Goals

**Goals:**

- Initialize OpenSpec and make it the persistent audit context.
- Map TradingX architecture, CLI commands, web/API contracts, persistence,
  external services, runtime lifecycle, and evidence lifecycle.
- Run safe local verification and record skipped/not-verified checks honestly.
- Review critical user flows and backend/frontend safety boundaries.
- Review tests for safety, authorization, idempotency, recovery, and gate
  evidence coverage.
- Implement only high-impact, locally verifiable safe fixes.
- Produce engineering, fix-plan, non-technical, and adversarial committee
  reports.

**Non-Goals:**

- Enable live trading or change Gate 4 posture.
- Submit live orders.
- Run unbounded services.
- Require real credentials, market hours, Telegram, SMTP, or Postgres for the
  audit to complete.
- Change trading strategy behavior unless an obvious safety defect is found.
- Replace the existing `.specify/` artifacts; OpenSpec is used for this audit.

## Decisions

- Use `openspec/changes/audit-production-readiness-tradingx/` as the single
  audit control folder so assumptions, checklists, requirements, findings, and
  reports survive chat context loss.
- Treat fail-closed live trading, write-action authorization, duplicate paper
  prevention, bounded automation, and secret redaction as Critical/High
  controls.
- Prefer documented commands and bounded variants from `README.md` and
  `docs/operations/operator_manual.md`.
- Mark external-service checks `not verified` when safe credentials or required
  service state are absent rather than creating artificial pass signals.
- Use TDD for production bug fixes. Documentation-only/report updates may be
  written directly.

## Risks / Trade-offs

- External credentials may be present in `.env` -> Inspect only presence and
  redacted summaries; never quote values.
- Market-dependent flows may be unavailable outside US regular hours -> Verify
  dry-run, mocked, bounded, and unit/contract paths; record live paper checks as
  not verified if unavailable.
- Full validation may be long-running -> Run it where safe, keep command
  evidence, and use focused reruns after fixes.
- OpenSpec strict validation may reject malformed specs -> Validate early and
  repair the audit specs before implementation.
- Browser-backed UI testing may require a running local server -> Start only
  local server processes with a clear stop condition and shut them down before
  completion.

## Audit Log

This section is updated throughout the audit.

| Command | Result | Status | Notes |
| --- | --- | --- | --- |
| `git status --short --branch` | `## main...origin/main` | passed | Worktree clean before OpenSpec initialization. |
| `openspec init` | OpenSpec structure created | passed | Added OpenSpec folders and Claude helper files. |
| `openspec new change audit-production-readiness-tradingx` | Change scaffold created | passed | Schema: `spec-driven`. |
| `openspec validate audit-production-readiness-tradingx --strict` | Change is valid | passed | Validated initial OpenSpec proposal, design, specs, and tasks. |
| `uv run pytest tests/unit/test_live_enablement.py tests/unit/test_config.py tests/unit/test_web_security.py tests/unit/test_data.py tests/unit/test_risk.py -q` | 6 expected failures | red | Added failing tests for missing Gate 4 approval blockers and pending idempotency duplicate race before production edits. |
| Same focused pytest command after first fixes | 48 passed | passed | Gate 4 env acknowledgement controls and idempotency reservation tests passed. |
| Follow-up focused pytest after review fixes | 5 expected failures | red | Added tests for durable Gate 4 approval evidence, atomic completed idempotency writes, and reservation timestamp preservation. |
| Follow-up focused pytest after review fixes | 52 passed | passed | Durable Gate 4 approval evidence and atomic completion writes passed. |
| Review contract-focused pytest | 53 passed | passed | Added control-posture contract route to the review-fix target set. |
| User-listed focused pytest after review fixes | 34 passed | passed | `tests/unit/test_web_security.py tests/unit/test_config.py tests/unit/test_live_enablement.py`. |
| `./scripts/validate-fast` after review fixes | 166 passed, 12 warnings | passed | Artifact index, ruff, black, mypy, and focused pytest after durable approval and atomic write changes. |
| Gate 4 schema-regression pytest | 3 expected failures | red | Proved ad hoc Gate 4 JSON could unlock live and authority-boundary builder/schema lacked checklist evidence. |
| Gate 4 schema-regression pytest after fix | 3 passed | passed | Ad hoc Gate 4 JSON is rejected; schema-backed authority-boundary artifact with checklist evidence is accepted. |
| Fixture regression pytest after Gate 4 schema fix | 6 passed | passed | Default promotion and portfolio preflight fixtures remain valid while Gate 4 still requires checklist-backed evidence. |
| User-listed focused pytest after Gate 4 schema fix | 36 passed | passed | `tests/unit/test_web_security.py tests/unit/test_config.py tests/unit/test_live_enablement.py`. |
| Live-boundary focused pytest after Gate 4 schema fix | 81 passed | passed | Config, live enablement, data, risk, web security, and authority-boundary tests passed with schema-backed Gate 4 fixtures. |
| `./scripts/validate-fast` after Gate 4 schema fix | 166 passed, 12 warnings | passed | Artifact index, ruff, black, mypy, and focused pytest passed after schema/builder/config updates. |
| `./scripts/validate-fast` | 164 passed, 12 warnings | passed | Artifact index, ruff, black, mypy, focused pytest. |
| `npm --prefix webapp test` | 108 passed | passed | Vitest frontend suite. |
| `npm --prefix webapp run build` | Build completed | passed-with-warning | Vite emitted a chunk-size warning for a 732 kB JS chunk. |
| `uv build` | sdist and wheel built | passed | Built `tradingx-0.1.0` artifacts. |
| `./scripts/validate` | 1459 passed, 98 skipped, 14 warnings | passed-with-skips | Smoke test skipped because regular US market hours were closed. Coverage 84.63%, above 80% gate. |
| `uv run tradingx config-summary --env-file .env` | Redacted summary printed | passed | Paper credentials present; live credentials absent; local `.env` has web write mode enabled and signing configured. No secret values printed. |
| `uv run tradingx live-disable-status --env-file .env` | Live disabled | passed | Blockers include broker not live, missing live credentials, config/env live layers disabled, operator/checklist env acknowledgements missing, and durable Gate 4 approval artifact missing. |
| `uv run tradingx web --env-file .env` with `TRADINGX_WEB_WRITE_MODE_ENABLED=false TRADINGX_WEB_PORT=8766` | Server started and stopped | passed | Port 8765 was already occupied by an existing TradingX process, so the audit instance used 8766. |
| `curl /api/config/summary` on 8766 | Read model returned fail-closed config | passed | Live trading disabled; write mode disabled for audit server. |
| `curl /api/v1/control-posture` on 8766 | Control posture returned fail-closed state | passed | Governance signoff/checklist missing and live not allowed. |
| Unsigned `POST /api/actions/service/stop` on 8766 | 403 | passed | Write action rejected because audit server write mode was disabled. |
| Browser Use in-app navigation to local server | Timed out before tab left `about:blank` | not verified | Browser runtime initialized, but local HTTP `tab.goto()` timed out. UI covered by frontend tests/build and API curl, not visual browser inspection. |
| `uv run tradingx evidence-report --artifact-root artifacts` | 0 cycles, 0 alerts, 0 validation reports | passed | Existing paper evidence is empty for this audit view. |
| `uv run tradingx gate3-report ...` | Gate 3 readiness pending | passed | 0 trades / 0 days; recovery, SMTP, slippage, hit-rate, and Sharpe evidence pending. |
| `uv run tradingx replay-slippage-report ... --include-quote-quality` | Replay summary pending | passed | No matched execution artifacts with quote/ADV context. |
| `uv run tradingx alert-drill --env-file .env --channel smtp` | Pending | passed-with-unconfigured-dependency | SMTP is not configured; wrote a pending alert drill record. |
| `uv run tradingx gate3-package ...` | Package pending | passed | Package reflects pending Gate 3 criteria and has no evidence refs. |
| `uv run tradingx decision-report --gate 3 ...` | `ValueError: No validation reports are available for gate 3.` | failed-expected | Gate decision report cannot be produced until gate validation reports exist. |
| `uv run tradingx promotion-check --strategy-id baseline-long-only-v1 --artifact-root artifacts --format json` | max state `disabled` | passed | Blocker: `authority_artifact_invalid`. |

## Findings Register

### Critical

1. **Live mode could be enabled without explicit Gate 4 approval.**
   Confirmed bug, fixed now. Before this audit, `TradingConfig.live_block_reasons`
   required live credentials, broker mode, file/env live flags, code guard, and
   web signing, but did not require explicit Gate 4 acknowledgement or durable
   approval evidence. That contradicted the prime directive and the project gate
   docs. The fix now treats process-env flags as temporary acknowledgements and
   keeps live disabled unless a durable signed, unexpired, checklist-backed Gate
   4 approval artifact is also configured, closed-world schema-valid, and valid.

### High

1. **Concurrent signed web writes could pass idempotency authorization before
   the first response was stored.** Confirmed bug, fixed now. The authorizer
   checked for a completed idempotency record but did not reserve the key before
   executing the write action. A duplicate request with the same idempotency key
   could therefore authorize concurrently. The first fix added an atomic pending
   reservation and rejects pending duplicates with 409; the follow-up fix writes
   completed records through temp-file replacement and preserves the original
   reservation timestamp.
2. **The local `.env` has web write mode enabled.** Environment risk, not a code
   defect. The app still requires signed POSTs and the audit server was forced
   read-only, but this local operator environment is closer to write-capable
   than the default docs recommend.

### Medium

1. **Gate 3 evidence is materially incomplete.** Confirmed readiness gap. The
   generated Gate 3 readiness report is pending with 0 trades / 0 days and
   missing recovery, SMTP, slippage, hit-rate, Sharpe, and replay evidence.
2. **Gate 3 decision report cannot be generated from current artifacts.**
   Confirmed command failure. `decision-report --gate 3` raises because no gate
   validation reports exist.
3. **Recurring market-day scheduler still launches each market day with
   `max_heartbeats=None`.** Suspected operational risk. It is bounded by the
   session close and supports `max_scheduled_days`, but the CLI does not expose a
   heartbeat cap for scheduler-launched days. Use a stop event/supervisor in
   production and add a bounded test option before unattended operation.
4. **Recovery drill error reporting is too opaque for audit evidence.**
   Suspected evidence-quality risk. `run_recovery_drill` catches all exceptions
   and records a generic failure message, making root-cause review harder.

### Low

1. **Frontend production bundle exceeds Vite's default warning threshold.** Low
   performance/maintainability risk. Build passes, but the main JS chunk is
   732 kB minified.
2. **Postgres and external alert transports were not verified.** Environment
   limitation. No Postgres DSN, SMTP, or Telegram configuration was available
   through safe summaries.

## Prioritized Fix Plan

### Safe Immediate Fixes

- **Fixed now, Critical:** Add explicit Gate 4 env acknowledgements and durable
  schema-validated approval evidence controls to live enablement.
  - Risk reduced: accidental live enablement.
  - Files affected: `src/tradingx/config.py`, `src/tradingx/web/app.py`,
    `.env.example`, live/config/risk/data tests.
  - Complexity: low.
  - Verification: focused pytest, `./scripts/validate-fast`,
    `./scripts/validate`, config-summary/live-disable-status, control-posture
    API.
  - Safe to implement now: yes.
- **Fixed now, High:** Add atomic pending idempotency reservations and atomic
  completed writes for web writes.
  - Risk reduced: duplicate signed local write execution.
  - Files affected: `src/tradingx/web/security.py`,
    `tests/unit/test_web_security.py`.
  - Complexity: medium.
  - Verification: new pending duplicate test, web security tests, full
    validation, read-only API POST rejection.
  - Safe to implement now: yes.

### Needs More Design

- Add stale-pending idempotency recovery semantics after process crash. Current
  behavior fails closed by leaving a pending key blocked or corrupt, which is
  safe but may require operator recovery tooling.
- Add a bounded scheduler heartbeat cap or audit-only stop condition to
  `run-market-scheduler`, then cover it in tests.
- Improve recovery drill evidence by preserving sanitized exception classes or
  reason codes without exposing secrets.

### Needs Credentials Or Market-Hours Verification

- Real Alpaca paper round trip for `SPY`.
- Bounded recurring paper service across `SPY,QQQ,IWM`.
- Full market-day automation with pre-open, heartbeat, closeout, and Gate 3
  refresh.
- Smoke test against real Alpaca paper credentials during regular US market
  hours.

### Needs Operator Approval

- Keep or disable local web write mode in `.env`. The default should remain
  disabled; enabling it should be an explicit local operator choice.
- Any live-mode validation beyond fail-closed readouts.

### Should Wait Until Gate Promotion Work

- Gate 1/2/3 evidence production and review.
- Gate 4 signed approval records with approver identity, timestamps, and
  revocation posture.
- Live probe/tiny-live workflows.

## Review Notes

- Paper/live boundary: live mode now requires real live credentials, broker mode
  `live`, file live flag, process live flag, code guard, web signing, process
  Gate 4 acknowledgements, valid durable Gate 4 approval evidence, no manual
  kill switch, and no dry-run mode.
- Web authorization: POST routes pass through `WebWriteAuthorizer`, require
  write mode, signing secret, timestamp, idempotency key, HMAC signature, and now
  an atomic pending reservation before action execution.
- Duplicate paper submission controls: paper loop uses deterministic
  `client_order_id`, journal records, and broker lookup for recovery, but real
  broker duplicate behavior was not verified during this audit.
- Persistence: legacy local artifacts remain default. Optional Postgres and
  projection paths are present but not verified without DSN.
- Scheduler: service cycles can be bounded with `max_cycles`; scheduler can be
  bounded by `max_scheduled_days`, but daily heartbeat count is not operator
  bounded through scheduler CLI.
- Frontend/backend contract: contract tests and frontend tests pass; visual UI
  inspection through in-app Browser Use was not verified due local navigation
  timeout.
