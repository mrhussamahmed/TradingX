## Why

TradingX is intended to be a local, paper-only trading appliance with strong
operator control, audit evidence, and promotion gates, but the repository did
not yet have OpenSpec audit context for a production-readiness review. This
change creates a persistent OpenSpec-backed audit trail before deeper review,
verification, and safe remediation work.

## What Changes

- Create an OpenSpec audit control package for production readiness,
  safety-boundary validation, critical user-flow review, and verification
  evidence tracking.
- Capture conservative audit assumptions, command evidence, skipped checks,
  findings, and a prioritized fix plan in OpenSpec.
- Define expected requirements and acceptance scenarios for the TradingX
  safety boundary, local Control Center, paper runtime, scheduler, evidence,
  recovery, validation gates, persistence, web authorization, and testing.
- Implement only locally verifiable, high-impact safe fixes discovered during
  the audit.
- No breaking runtime behavior is intended; live trading must remain
  fail-closed.

## Capabilities

### New Capabilities
- `safety-boundary`: Paper-only and live-trading fail-closed safety controls.
- `control-center`: Local Control Center read/write behavior, runtime host
  visibility, and operator UI safety.
- `paper-runtime`: Manual and supervised paper runtime lifecycle,
  idempotency, bounded execution, and stop behavior.
- `scheduler`: Market-day automation and recurring scheduler lifecycle safety.
- `evidence`: Audit, validation, runtime, alert, and promotion evidence
  generation and integrity.
- `recovery`: Paper recovery, reconciliation, drills, alerts, and restart
  behavior.
- `validation-gates`: Gate 1, Gate 2, Gate 3, and Gate 4 readiness and
  promotion safeguards.
- `persistence`: Legacy local persistence and optional Postgres behavior.
- `web-authorization`: Local web write-mode, request signing, authorization,
  and idempotency boundary.
- `testing`: Safety, runtime, frontend, integration, smoke, and gate coverage.

### Modified Capabilities
- None. OpenSpec had no existing main specs before this audit change.

## Impact

- Adds OpenSpec audit artifacts under
  `openspec/changes/audit-production-readiness-tradingx/`.
- May add focused tests and safe fixes under `src/tradingx/`, `webapp/`, or
  `tests/` if the audit confirms locally verifiable safety defects.
- Does not enable live trading, loosen authorization, delete data, or require
  real broker credentials.
