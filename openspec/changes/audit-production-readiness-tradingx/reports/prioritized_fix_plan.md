# Prioritized Fix Plan

## Fixed Now

1. Critical live Gate 4 fail-closed control
   - Change: added `TRADINGX_GATE4_OPERATOR_SIGNOFF` and
     `TRADINGX_GATE4_CHECKLIST_APPROVED` as process-env acknowledgements, and
     `TRADINGX_GATE4_APPROVAL_FILE` as required durable approval evidence.
     Gate 4 approval files now must validate against the closed-world
     `authority_boundary` schema and include non-empty checklist evidence refs.
   - Risk reduced: accidental live enablement before explicit Gate 4 approval.
   - Files: `src/tradingx/config.py`, `src/tradingx/live_probe_governance.py`,
     `schemas/quant/authority_boundary.schema.json`,
     `src/tradingx/web/app.py`, `.env.example`, live/config/risk/data tests.
   - Verification: focused pytest, `./scripts/validate-fast`,
     `./scripts/validate`, config summary, live-disable status, control posture
     API.

2. High web write idempotency race
   - Change: added atomic pending idempotency reservation before write action
     execution and atomic temp-file replacement for completed records.
   - Risk reduced: duplicate local signed write execution.
   - Files: `src/tradingx/web/security.py`, `tests/unit/test_web_security.py`.
   - Verification: pending duplicate test, full validation suite, read-only API
     POST rejection.

## Remains

- Add stale-pending idempotency recovery tooling for process crashes after
  authorization but before response storage.
- Add scheduler heartbeat caps or bounded rehearsal mode for
  `run-market-scheduler`.
- Improve recovery drill error evidence with sanitized reason codes.
- Consider structured pending output for missing gate decision artifacts instead
  of a traceback.
- Address frontend bundle-size warning after safety work.

## Needs Credentials

- Postgres domain/projection integration with `TRADINGX_TEST_POSTGRES_DSN`.
- SMTP and Telegram alert round trips.
- Alpaca paper smoke tests with valid paper credentials.

## Needs Market-Hours Validation

- Manual paper cycle for `SPY`.
- Bounded recurring paper service across `SPY,QQQ,IWM`.
- Market-day automation pre-open, heartbeat, closeout, and Gate 3 refresh.
- Real paper duplicate-order recovery behavior against broker state.

## Needs Operator Approval

- Any live-mode run or live credential validation.
- Keeping local `.env` web write mode enabled outside a bounded signed test.
- Actual Gate 4 approval decision, approver identity, and any live-probe
  posture. The code can validate a schema-valid durable local approval artifact
  but cannot create or approve it for the operator.

## Wait For Gate Promotion Work

- Gate 1/2/3 evidence completion.
- 180 calendar days or 100 closed trades for Gate 3.
- Gate 4 sign-off packet and live probe readiness.
- Capital caps, live kill-switch rehearsal, monitoring escalation, and fresh
  alert transport drills.
