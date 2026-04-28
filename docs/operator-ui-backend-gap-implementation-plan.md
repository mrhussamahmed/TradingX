# Operator UI Backend Gap Implementation Plan

Date: 2026-04-28
Status: draft for adversarial review
Source of truth: `docs/operator-ui-backend-gap-plan.md`

## Problem Statement

The approved source plan requires Mission Control to stop treating render
freshness as safety evidence. This implementation plan translates that
source plan into an execution sequence for backend contracts, read-model
derivation, frontend consumption, regression tests, and final review
documentation.

If this file conflicts with `docs/operator-ui-backend-gap-plan.md`, the
source plan wins. This file must not broaden scope, relax safety
requirements, or reinterpret missing evidence as fresh evidence.

## Safety Invariants

- Never use `generated_at_utc`, current time, UI refresh time, or report
  read time as required safety evidence.
- Portfolio required evidence is account/position evidence only; OMS
  journal and closed-trade timestamps stay diagnostic.
- Gate 3 required evidence is satisfied only when every required
  criterion has a source timestamp and no required criterion is stale.
- Gate 3 report-level required evidence uses the oldest required
  criterion timestamp, not the latest.
- Zero-P1 Gate 3 evidence needs an explicit evidence-of-absence scan
  boundary or remains missing-source.
- Legacy Gate 3 reports must not receive current timestamps through an
  overlay. Regenerate them or keep them missing-source unless timestamps
  are proven from the report's own evidence refs and matching payload.
- Runtime decision evidence is the opportunity-selection timestamp only;
  heartbeat, activation, runtime state, exposure, or OMS context cannot
  refresh it.
- Selection-backed `no_trade` is valid decision evidence, including when
  no ranked opportunity exists; unavailable numeric fields are `null`.

## Execution Strategy

Implement contract-first, then populate each source class independently.
Every wave should add failing regression coverage before the production
change, then wire the frontend only after the backend contract exists.

Do not combine portfolio, Gate 3, and decision source derivation in one
large patch. Keeping these changes separate makes adversarial review
easier and prevents one class of evidence from accidentally satisfying
another.

## Wave 0 - Baseline and Guardrails

Goal: capture the current state before changing contracts.

Tasks:

- Confirm the worktree and preserve any unrelated user changes.
- Run baseline tests that will be touched by this work:
  - `python -m pytest tests/unit/test_types.py tests/unit/test_web_readmodels.py tests/unit/test_gate3.py tests/contract/test_local_web_app_api_contract.py`
  - `npm --prefix webapp test`
- Record any pre-existing failures before editing.

Review focus:

- Verify the implementation starts from the approved source plan and not
  from the older reviewer handoff report.

## Wave 1 - Shared Contracts

Goal: add response shapes without claiming freshness before read models
can prove it.

Backend tasks:

- Extend `Gate3CriterionSnapshot` in `src/tradingx/types.py` with:
  - `source_evidence_at_utc: datetime | None = None`
  - `required: bool = True`
- Extend `Gate3ReadinessReport` with:
  - `source_evidence_at_utc: datetime | None = None`
  - `oldest_required_source_evidence_at_utc: datetime | None = None`
  - `latest_source_evidence_at_utc: datetime | None = None`
  - `required_criterion_ids: tuple[str, ...] = ()`
  - `missing_source_criterion_ids: tuple[str, ...] = ()`
- Extend `PortfolioWorkspaceSnapshot` with:
  - `source_evidence_at_utc: datetime | None = None`
  - `account_position_source_at_utc: datetime | None = None`
  - `execution_journal_source_at_utc: datetime | None = None`
  - `closed_trade_source_at_utc: datetime | None = None`
- Add runtime decision detail dataclasses in `src/tradingx/types.py`:
  - `RuntimeDecisionSignalDetail`
  - `RuntimeDecisionRegimeDetail`
  - `RuntimeDecisionRiskDetail`
  - `RuntimeDecisionExecutionDetail`
  - `RuntimeDecisionFreshnessDetail`
  - `RuntimeDecisionDetail`
- Add `build_runtime_decision_detail()` to the read-model protocol in
  `src/tradingx/web/app.py`, returning `RuntimeDecisionDetail | None`.
- Add `GET /api/runtime-host/decision/latest` in `src/tradingx/web/app.py`.

Frontend tasks:

- Add matching TypeScript types in `webapp/src/types.ts`.
- Add `getRuntimeHostDecision()` in `webapp/src/api.ts`.
- Add a nullable `runtimeDecisionDetail` field to the control-center data
  context with a conservative default of `null`.

Tests:

- Update `tests/unit/test_types.py` serialization coverage for all new
  optional fields.
- Update `tests/contract/test_local_web_app_api_contract.py` with the new
  endpoint and required nested fields.
- Add contract assertions that empty nested runtime detail objects are
  invalid.
- Add contract assertions that Gate 3 exposes the required criterion set
  through criterion-level `required` flags and report-level
  `required_criterion_ids`.
- Add webapp type/context tests proving the new endpoint is fetched but
  absence remains conservative.

Review focus:

- Ensure optional timestamp fields default to `None` and do not introduce
  accidental freshness.
- Ensure the new endpoint can return `null` only when no selection-backed
  decision exists.

## Wave 2 - Portfolio Source Evidence

Goal: expose portfolio required evidence from the strict account/position
source and keep adjacent timestamps diagnostic.

Backend tasks:

- Add helper methods in `src/tradingx/web/readmodels.py` to derive:
  - account source timestamp from service-cycle or future broker/account
    artifacts
  - position source timestamp from service-cycle or future broker/position
    artifacts
  - latest OMS journal timestamp
  - latest closed-trade timestamp
- Populate `PortfolioWorkspaceSnapshot.source_evidence_at_utc` from the
  account/position timestamp only.
- When account and position freshness are separate, compute
  `PortfolioWorkspaceSnapshot.source_evidence_at_utc` as the older of the
  two timestamps. A fresh account snapshot must not launder stale
  positions, and fresh positions must not launder stale account balances.
- When account and position freshness are separate, both sides are
  required. If either account evidence or position evidence is missing,
  keep `source_evidence_at_utc` and `account_position_source_at_utc` as
  `None`; one-sided evidence is diagnostic only.
- Populate diagnostic portfolio timestamps separately.
- Return `None` when account/position evidence is unavailable, even if
  OMS or closed-trade evidence is fresh.

Frontend tasks:

- Update Mission Control required portfolio evidence to use
  `portfolio.source_evidence_at_utc`.
- Keep OMS and closed-trade diagnostics out of required evidence.

Tests:

- Add `tests/unit/test_web_readmodels.py` cases for:
  - no account/position artifacts gives missing required source
  - account-only evidence keeps required portfolio source as `None`
  - position-only evidence keeps required portfolio source as `None`
  - service-cycle account/position evidence populates required source
  - fresh account evidence plus stale position evidence uses the stale
    position timestamp
  - stale account evidence plus fresh position evidence uses the stale
    account timestamp
  - stale account/position evidence plus fresh OMS activity still uses
    the stale account/position source
  - fresh closed-trade evidence alone does not satisfy required portfolio
    evidence
- Add frontend regression coverage that Mission Control reports missing
  portfolio evidence when only render timestamps exist.

Review focus:

- Challenge every portfolio timestamp path for broadness. Required
  evidence must stay tied to equity, buying power, and positions.

## Wave 3 - Gate 3 Source Lineage

Goal: make Gate 3 criterion evidence explicit and fail closed for
missing, stale, and legacy source gaps.

Backend tasks:

- Add timestamp extraction helpers in `src/tradingx/gate3.py` for:
  - closed trades
  - service cycles
  - execution lifecycle records
  - recovery drills
  - SMTP alert drills
  - replay slippage summaries
  - reference/evaluation evidence
  - operator-alert scan windows for zero-P1 evidence-of-absence
- Thread `source_evidence_at_utc` into every
  `Gate3CriterionSnapshot` built by shared, legacy, and governed report
  builders.
- Add report aggregation that computes:
  - `required_criterion_ids`
  - `missing_source_criterion_ids`
  - `oldest_required_source_evidence_at_utc`
  - `latest_source_evidence_at_utc`
  - `source_evidence_at_utc` as an alias for oldest required evidence
- Define required criteria explicitly in code so optional diagnostics do
  not block or satisfy required Gate 3 evidence by accident.
- Set `required=true` on required criteria and `required=false` on any
  optional diagnostic criteria. Report-level `required_criterion_ids`
  must be derived from those flags so clients do not infer the required
  set.
- Update `LocalWebReadModel.build_gate3_readiness()` so persisted legacy
  reports without source timestamps are either regenerated or returned
  missing-source. Do not overlay current artifact timestamps onto old
  criterion statuses.
- Allow compatibility overlay only when the report's own `evidence_refs`
  identify matching payloads and those payloads prove the criterion
  timestamp.

Frontend tasks:

- Update `deriveGateEvidenceTimestamp()` to use
  `oldest_required_source_evidence_at_utc`.
- Treat non-empty `missing_source_criterion_ids` as missing gate evidence.
- Add per-criterion stale checks only for criteria marked `required=true`
  or listed in `required_criterion_ids`.
- Keep `latest_source_evidence_at_utc` display-only.

Tests:

- Add `tests/unit/test_gate3.py` cases for:
  - one fresh criterion plus one missing criterion does not produce
    report-level required evidence
  - report source timestamp is the oldest required criterion timestamp
  - optional diagnostic criteria do not satisfy or block required Gate 3
    evidence
  - zero-P1 passes only with scan-window-backed evidence-of-absence
  - zero-P1 without a scan boundary remains missing-source
  - `generated_at_utc` never satisfies source evidence
- Add `tests/unit/test_web_readmodels.py` cases for:
  - legacy persisted Gate 3 reports without source timestamps remain
    missing-source
  - fresh current artifacts do not refresh stale legacy persisted reports
    without regeneration
  - evidence-ref-proven compatibility timestamps are accepted only when
    criterion payloads match
- Add frontend regression coverage that stale or missing criterion-level
  evidence keeps required gate evidence in watch/missing state.
- Add frontend regression coverage that Mission Control uses backend
  `required` flags or `required_criterion_ids`, not a hard-coded
  criterion list.

Review focus:

- Look for laundering through `latest_source_evidence_at_utc`,
  `generated_at_utc`, persisted report read time, or current artifact
  overlays.

## Wave 4 - Runtime Decision Detail

Goal: expose a structured, testable latest decision detail whose required
freshness is selection-backed only.

Backend tasks:

- Implement `LocalWebReadModel.build_runtime_decision_detail()` using the
  latest `OpportunitySelectionRecord`.
- Return `None` only when no selection record exists.
- Set `decision_source_at_utc` to
  `OpportunitySelectionRecord.generated_at_utc`.
- Build `signal` from the selected ranked opportunity, or the top ranked
  opportunity for `no_trade` when one exists.
- If `decision="selected"` but `selected_symbol` is absent from
  `ranked_opportunities`, return a structured inconsistency detail
  instead of falling back to the top ranked opportunity:
  - keep `decision_source_at_utc` equal to the selection timestamp
  - keep `decision` and `selected_symbol` from the selection record
  - set `signal.available=false`
  - set unavailable signal numeric fields and threshold gap to `None`
  - set `risk.eligible=false`
  - set `risk.ineligibility_reason` to a deterministic integrity message
    such as `selected_symbol missing from ranked_opportunities`
- For selection-backed `no_trade` with no ranked opportunities, set:
  - `signal.available=false`
  - unavailable numeric fields to `None`
  - `risk.eligible=None`
- Keep runtime context and execution context timestamps separate in
  `freshness`.
- Avoid empty strings for unavailable numeric fields.

Frontend tasks:

- Fetch `runtimeDecisionDetail` in `DataContext`.
- Update Mission Control required decision evidence to use
  `runtimeDecisionDetail.decision_source_at_utc`.
- Keep `runtimeSelection.generated_at_utc` as compatibility display data
  only, not required safety evidence.

Tests:

- Add `tests/unit/test_web_readmodels.py` cases for:
  - no selection returns `None`
  - selected decision exposes selected symbol, score, weights, threshold,
    and selection-backed timestamp
  - `selected` decision with `selected_symbol` absent from
    `ranked_opportunities` returns the structured inconsistency shape and
    does not silently fall back to the top ranked opportunity
  - `no_trade` with ranked opportunities uses the top opportunity as
    signal context
  - `no_trade` with no ranked opportunities returns structured detail
    with null numeric fields and `signal.available=false`
  - fresh heartbeat/runtime/OMS context cannot change
    `decision_source_at_utc`
- Add contract tests for the endpoint response and nullability rules.
- Add frontend regression coverage that decision evidence stays stale
  when only heartbeat or OMS context is fresh.

Review focus:

- Check whether any field named `context_source_at_utc` is accidentally
  used as required decision evidence.

## Wave 5 - Mission Control Evidence Wiring

Goal: consume the backend source fields and keep the UI conservative when
contracts are missing or stale.

Frontend tasks:

- Update `deriveRequiredSafetyEvidence()` inputs to use:
  - heartbeat evidence from the current heartbeat source path
  - gate evidence from Gate 3 oldest required source evidence plus
    missing criterion IDs
  - portfolio evidence from `portfolio.source_evidence_at_utc`
  - decision evidence from
    `runtimeDecisionDetail.decision_source_at_utc`
- Add per-class threshold support while keeping the current shared
  threshold as the v1 default.
- Ensure the Evidence Freshness card and missing-evidence ledger consume
  the same derived `RequiredSafetyEvidence`.
- Leave render timestamps visible only as local context.

Tests:

- Extend
  `webapp/src/control-center/flavors/__tests__/OperatorMissionControlFlavor.test.ts`
  for fresh and stale portfolio, gate, and decision source evidence.
- Extend `webapp/src/control-center/__tests__/ControlCenterApp.test.tsx`
  for the new decision endpoint fetch and conservative fallback.
- Add model tests proving source fields, not render fields, drive
  required evidence.

Review focus:

- Search for `generated_at_utc` in Mission Control and verify no render
  timestamp satisfies required safety evidence.

## Wave 6 - Final Verification and Review Report

Goal: prove the implementation closes the approved backend gaps and
document the result.

Verification commands:

- `python -m pytest tests/unit/test_types.py tests/unit/test_web_readmodels.py tests/unit/test_gate3.py tests/contract/test_local_web_app_api_contract.py tests/unit/test_web_app.py`
- `npm --prefix webapp test`
- `npm --prefix webapp run lint -- --quiet`
- `npm --prefix webapp run build`

Documentation tasks:

- Update `docs/operator-ui-review-response-report.md` after code and
  tests pass.
- Summarize each closed backend gap with:
  - closing code path
  - regression coverage
  - verification command result
  - any remaining limitations
- Do not edit `docs/operator-ui-backend-gap-plan.md` unless a reviewer
  explicitly reopens the approved source plan.

Review focus:

- Confirm the report distinguishes implemented behavior from remaining
  limitations and does not claim evidence exists where source artifacts
  are still unavailable.

## Dependency Order

1. Backend dataclass fields and endpoint contracts.
2. Backend source derivation for portfolio, Gate 3, and decision detail.
3. Frontend type/API/context support.
4. Mission Control required evidence wiring.
5. Regression tests and reviewer report update.

Portfolio, Gate 3, and decision detail can be implemented in separate
patches after Wave 1, but Mission Control should not be switched to a
source class until that class has backend tests proving its timestamp
cannot be laundered.

## Adversarial Review Checklist

- Can any required evidence timestamp be satisfied by a render time?
- Can a fresh adjacent artifact make stale account/position evidence look
  fresh?
- Can one fresh Gate 3 criterion hide another missing or stale criterion?
- Can zero P1 incidents pass without a scan-window evidence boundary?
- Can legacy Gate 3 reports become fresh without regeneration or
  evidence-ref-proven timestamps?
- Can a fresh heartbeat, runtime state, activation, or OMS event refresh
  an old decision?
- Can `no_trade` with no ranked opportunities pass contract tests with
  empty objects or empty strings instead of explicit nullability?
- Do frontend freshness cards and ledgers use the same derived safety
  evidence path?
- Are all compatibility fields clearly diagnostic rather than required
  evidence?

## Files Expected To Change During Implementation

- `src/tradingx/types.py`
- `src/tradingx/web/readmodels.py`
- `src/tradingx/web/app.py`
- `src/tradingx/gate3.py`
- `tests/unit/test_types.py`
- `tests/unit/test_web_readmodels.py`
- `tests/unit/test_gate3.py`
- `tests/unit/test_web_app.py`
- `tests/contract/test_local_web_app_api_contract.py`
- `webapp/src/types.ts`
- `webapp/src/api.ts`
- `webapp/src/control-center/state/DataContext.tsx`
- `webapp/src/control-center/flavors/OperatorMissionControlModel.ts`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`
- `webapp/src/control-center/__tests__/ControlCenterApp.test.tsx`
- `webapp/src/control-center/flavors/__tests__/OperatorMissionControlFlavor.test.ts`
- `docs/operator-ui-review-response-report.md`

## Explicit Non-Changes

- Do not change live trading permissions.
- Do not change Gate 3 promotion authority.
- Do not fabricate historical source evidence.
- Do not remove `/api/runtime-host/selection/latest`.
- Do not treat OMS, closed trades, heartbeat, or activation context as
  substitutes for the required source class they merely contextualize.
