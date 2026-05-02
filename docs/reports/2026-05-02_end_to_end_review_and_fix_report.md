# TradingX End-to-End Review and Fix Report

Review date: 2026-05-02

Scope: committed branch diff `main...HEAD` for the paper-promotion,
registry-split, and mobile-shell branch. This report intentionally does not
claim fixes that exist only as unstaged workspace edits.

## Committed Fixes In This Branch

### Promotion posture

- `promotion-check --strategy-id trend-following-v1` is treated as the source
  of truth for the default artifact root.
- The CLI test now expects `requested_state: "paper_trading"`,
  `max_state: "paper_trading"`, and empty blocker lists.
- `docs/validation/acceptance_gates.md` now documents paper-only trial posture:
  paper operation is allowed for local observation, while live trading remains
  fail-closed until Gate 4.

### Candidate registry contract

- `build_mandatory_candidate_registry(...)` now returns evaluated candidates
  only: trend following, vol target, and mean reversion.
- `build_runtime_candidate_registry(...)` includes the baseline with
  `status: "reference"` so runtime and UI flows can still resolve it.
- Runtime portfolio, activation, drift, sleeve ledger, web runtime, and
  readmodel paths now use the runtime registry where baseline resolution is
  required.
- Validation, CPCV/PBO, and evaluation paths use the mandatory registry so
  validation evidence counts are stable.

### Gate 1 marginal scope

- Gate 1 marginal contribution is scoped to the explicit trend/vol pair:
  `trend-following-v1` and `vol-target-v1`.
- `mean-reversion-v1` receives the other Gate 1 criteria but does not receive
  `marginal_portfolio_contribution` until a future gate amendment defines the
  3+ sleeve-backed marginal model.
- If the trend/vol pair is incomplete, marginal contribution remains
  `pending` instead of crashing.

### Automation reference generation

- Backtest reference generation skips sleeve candidates with no allowed
  instruments.
- This prevents empty `bars_by_symbol` payloads when a candidate universe is
  empty after benchmark-symbol exclusion.

### Mobile Control Center shell

- Narrow screens use explicit navigation and operator-rail drawer controls.
- A scrim closes open drawers.
- The operator canvas owns the mobile viewport, and drawer buttons do not
  occlude `.topStrip`.

## Findings Not Fixed By This Branch

The following findings were present in earlier local review notes, but their
source changes are not part of this committed branch diff and are not claimed
as fixed here:

- Duplicate signed web writes can race before idempotency response persistence.
- Web action inputs may accept impossible runtime values.
- Runtime heartbeat symbol rows may mix active runtime universe and historical
  activation/config coverage.
- OpenAPI docs and non-loopback web binding guardrails still need a separate
  product decision.
- The frontend production bundle still emits the existing large chunk warning.

## Verification

Clean-branch verification is recorded in
`docs/reports/2026-05-02_paper_promotion_registry_mobile_fix_report.md`.

## Review Packet

Questions reviewers should still press:

- Does paper-only promotion remain clearly separated from live enablement?
- Should the baseline ever re-enter mandatory validation, or remain a runtime
  reference only?
- When should the 3+ sleeve-backed Gate 1 marginal contribution model be
  specified for mean reversion?
- Which follow-up branch should own duplicate write idempotency and web action
  input validation?
