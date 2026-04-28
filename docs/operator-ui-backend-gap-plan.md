# Operator UI Backend Gap Plan

Date: 2026-04-28
Status: draft for adversarial review

## Problem Statement

Mission Control now avoids false confidence by refusing to treat
frontend read-model timestamps as source safety evidence. That frontend
fix intentionally leaves three backend gaps visible:

1. Portfolio safety evidence has no source timestamp.
2. Gate 3 criteria have no source lineage timestamp separate from report
   read time.
3. Runtime decisions do not have a structured detail endpoint covering
   signal, regime, risk, execution, mode, and evidence freshness.

As a result, the UI correctly labels required portfolio, gate, and
decision evidence as missing even when related read models are fresh. The
backend now needs to expose evidence-source timestamps and structured
decision details so Mission Control can distinguish "freshly rendered"
from "freshly evidenced."

The central risk is safety laundering: a current dashboard render could
make stale or missing operational evidence look safe. This plan is scoped
to closing that risk by adding explicit backend evidence contracts and
wiring Mission Control to use them.

## Goals

- Expose source evidence timestamps for portfolio safety evidence.
- Expose Gate 3 criterion and report source evidence timestamps.
- Expose structured runtime decision details with source freshness.
- Keep read-model `generated_at_utc` as render context only.
- Preserve frontend conservative behavior when backend source evidence
  is absent.
- Add regression tests that fail if read-model timestamps are reused as
  source evidence.

## Non-Goals

- No change to live trading permissions.
- No promotion authority change for Gate 3.
- No attempt to fabricate missing historical evidence.
- No broad redesign of Portfolio, Risk Core, or Market Day Ops views.
- No removal of existing `/api/runtime-host/selection/latest`; the new
  decision endpoint should complement it.

## Proposed Backend Contracts

### Portfolio

Extend `PortfolioWorkspaceSnapshot` in `src/tradingx/types.py`:

```python
source_evidence_at_utc: datetime | None = None
account_position_source_at_utc: datetime | None = None
execution_journal_source_at_utc: datetime | None = None
closed_trade_source_at_utc: datetime | None = None
```

`source_evidence_at_utc` is the strict required-safety timestamp for
portfolio evidence. It must be tied to the account and position source
used for equity, buying power, and current exposure, not to any unrelated
portfolio-adjacent activity.

Derive it in `LocalWebReadModel.build_portfolio_workspace_snapshot()` from
the latest account/position source artifact, expected to be the latest
service-cycle account snapshot or a future broker/account snapshot. If
account freshness and position freshness become separate fields, use the
older of the two for `source_evidence_at_utc` so the UI fails closed.

Keep these as diagnostics only:

- latest OMS journal event `recorded_at_utc`
- latest `closed_trades` timestamp, where available

Return `None` when none of those artifacts exists. Do not use
`datetime.now()` or `PortfolioWorkspaceSnapshot.generated_at_utc`.

### Gate 3

Extend `Gate3CriterionSnapshot`:

```python
source_evidence_at_utc: datetime | None = None
```

Extend `Gate3ReadinessReport`:

```python
source_evidence_at_utc: datetime | None = None
oldest_required_source_evidence_at_utc: datetime | None = None
latest_source_evidence_at_utc: datetime | None = None
missing_source_criterion_ids: tuple[str, ...] = ()
```

Each Gate 3 criterion should carry the timestamp of the evidence it
summarizes:

- `duration_or_trade_count`: latest governed closed trade or service
  cycle.
- `p1_bug_incidents`: an evidence-of-absence timestamp from an explicit
  alert scan window, not report generation time. For a passing zero-P1
  state, use the scan window end only when the report records the alert
  categories, time range, and artifact source that were scanned. If no
  scan boundary is available, this criterion remains missing-source.
- `recovery_drill`: latest recovery drill timestamp.
- `smtp_alert_drill`: latest alert drill timestamp.
- `replay_slippage_divergence`: latest replay-slippage summary timestamp.
- realized slippage, hit-rate, Sharpe, and related governed criteria:
  latest underlying execution, closed-trade, or reference-evidence
  timestamp.

Gate 3 required safety evidence must not be satisfied by one fresh
criterion. Report-level fields should be interpreted as follows:

- `oldest_required_source_evidence_at_utc`: the oldest timestamp across
  required criteria, present only when every required criterion has a
  source timestamp.
- `latest_source_evidence_at_utc`: diagnostic only; never sufficient by
  itself for required safety evidence.
- `missing_source_criterion_ids`: required criteria with no source
  timestamp.
- `source_evidence_at_utc`: compatibility alias for
  `oldest_required_source_evidence_at_utc`, not latest freshness.

Mission Control should fail closed when any required criterion source is
missing or stale. The report must never fall back to
`Gate3ReadinessReport.generated_at_utc`.

### Runtime Decision Details

Add a `RuntimeDecisionDetail` dataclass and endpoint:

```text
GET /api/runtime-host/decision/latest
```

Required v1 response fields:

- `selection_id`
- `decision_source_at_utc`
- `decision`
- `decision_reason`
- `mode`
- `selected_symbol`
- `signal`
- `regime`
- `risk`
- `execution`
- `freshness`

`decision_source_at_utc` must be exactly the opportunity-selection
timestamp. Fresh heartbeat, runtime, exposure, activation, or OMS context
must not make an old selection look fresh.

Required nested v1 fields:

- `signal`: `available`, `symbol`, `final_score`, `base_signal`,
  `model_weight`, `regime_weight`, `liquidity_weight`.
- `regime`: `label`, `source`, `context_source_at_utc`.
- `risk`: `eligible`, `ineligibility_reason`, `threshold`,
  `threshold_gap`, `portfolio_overlap_penalty`.
- `execution`: `current_exposure`, `pending_order_count`,
  `latest_reject_reason`, `context_source_at_utc`.
- `freshness`: `decision_source_at_utc`,
  `runtime_context_source_at_utc`, `execution_context_source_at_utc`.

Selection-backed `no_trade` is valid decision evidence. Return `null`
only when there is no selection-backed decision record.

Nullability rules:

- For `selected` decisions, `signal.available` must be `true` and the
  score/weight fields must come from the selected ranked opportunity.
- For selection-backed `no_trade` with ranked opportunities, use the top
  ranked opportunity as the signal context and keep `available=true`.
- For selection-backed `no_trade` with no ranked opportunities, keep the
  decision detail valid but set `signal.available=false`; `symbol`,
  scores, weights, `threshold_gap`, and `portfolio_overlap_penalty` are
  `null`, not empty strings.
- `eligible` is `null` when no ranked opportunity exists; otherwise it
  mirrors the opportunity score.
- Contract tests must fail if required nested objects are empty objects
  or if unavailable numeric fields are represented as empty strings.

## Frontend Integration Plan

Update `webapp/src/types.ts`, `webapp/src/api.ts`, and
`webapp/src/control-center/state/DataContext.tsx` to consume the new
fields and endpoint.

Mission Control should use:

- `portfolio.source_evidence_at_utc` for required portfolio evidence.
- `gate3Readiness.oldest_required_source_evidence_at_utc` plus
  `missing_source_criterion_ids` and criterion-level timestamps for
  required gate evidence.
- `runtimeDecisionDetail.decision_source_at_utc` for required decision
  evidence.

Mission Control should use per-class freshness checks, even if the first
implementation gives each class the same default threshold. Gate evidence
must fail closed when any required Gate 3 criterion is missing or stale.

Existing render-context timestamps should remain visible in local cards
where useful, but they must not satisfy required safety evidence.

## Implementation Phases

### Phase 1 - Contract and Tests

- Add backend dataclass fields and the new decision-detail dataclass.
- Add contract tests for JSON serialization of the new fields.
- Add frontend TypeScript types and API function shape.
- Keep behavior conservative until read models populate the fields.

### Phase 2 - Portfolio Source Evidence

- Implement source timestamp derivation in the portfolio read model.
- Add unit tests for no artifacts, service-cycle account/position
  evidence, stale account/position evidence with fresh OMS activity, and
  mixed diagnostic evidence.
- Prove OMS journal and closed-trade timestamps do not satisfy required
  portfolio safety evidence.
- Wire Mission Control portfolio evidence to the new field.

### Phase 3 - Gate 3 Source Lineage

- Thread source timestamps through Gate 3 shared and governed criteria.
- Derive report-level required evidence from the oldest required
  criterion timestamp and missing criterion IDs.
- Handle legacy persisted `gate3_reports` without source timestamp
  fields by full regeneration when the underlying source artifacts are
  available. Do not overlay current timestamps onto old criterion
  statuses. A compatibility overlay is allowed only when each timestamp
  is proven from the report's own `evidence_refs` and matching criterion
  payload; otherwise legacy reports remain missing-source.
- Add tests proving report `generated_at_utc` does not satisfy source
  evidence when criterion source timestamps are absent.
- Add tests for legacy persisted Gate 3 reports without
  `source_evidence_at_utc`, including a stale legacy report with fresh
  current artifacts that must not look fresh without regeneration.
- Add tests for zero-P1 evidence-of-absence: scan-window-backed zero
  incidents can satisfy the source timestamp, while no scan boundary
  remains missing-source.
- Wire Mission Control gate evidence to the new field.

### Phase 4 - Runtime Decision Detail

- Implement `RuntimeDecisionDetail` builder on the read model.
- Add `/api/runtime-host/decision/latest`.
- Include structured signal, regime, risk, execution, mode, and
  freshness fields.
- Ensure `decision_source_at_utc` is selection-only and context
  timestamps are separate.
- Treat selection-backed `no_trade` as valid decision evidence.
- Wire Mission Control decision evidence to this endpoint.

### Phase 5 - End-to-End Verification

- Update frontend tests for source-backed portfolio, gate, and decision
  evidence.
- Run backend unit and contract tests touched by read-model changes.
- Run webapp tests, lint, and build.
- Update `docs/operator-ui-review-response-report.md` with closed gaps
  and any remaining backend limitations.

## Adversarial Review Questions

1. Are these the correct source artifacts for portfolio evidence, or
   should the portfolio timestamp require a stricter source such as
   broker/account snapshot only?
2. Are the proposed required Gate 3 fields enough, or should the backend
   also expose stale criterion IDs directly instead of leaving staleness
   calculation to Mission Control?
3. Does adding source timestamps to existing response shapes create a
   compatibility concern for existing consumers?
4. Are there any places where the frontend could still accidentally use
   `generated_at_utc` as evidence after this plan?
5. Are same-default per-class freshness thresholds acceptable for v1, or
   do portfolio, gate, heartbeat, and decision evidence need different
   initial thresholds?

## Acceptance Criteria

- Mission Control no longer reports portfolio, gate, or decision
  evidence missing when source-backed backend evidence exists and is
  fresh.
- Mission Control still reports evidence missing when only read-model
  timestamps exist.
- A fresh OMS event cannot satisfy required portfolio safety evidence
  when account/position evidence is stale.
- One fresh Gate 3 criterion cannot satisfy required gate evidence when
  another required criterion is stale or missing.
- A passing zero-P1 Gate 3 criterion has explicit evidence-of-absence
  from a scan boundary, or it remains missing-source.
- Legacy Gate 3 reports without source timestamps do not become fresh
  because newer source artifacts exist; they require regeneration or
  evidence-ref-proven compatibility timestamps.
- A fresh runtime heartbeat or OMS event cannot refresh an old runtime
  decision; only the opportunity-selection timestamp can.
- Selection-backed `no_trade` is valid decision evidence, including when
  no ranked opportunity exists; unavailable signal/risk numeric fields
  are `null`, not empty strings or empty objects.
- Backend tests prove source timestamps are derived only from persisted
  or runtime source artifacts.
- Frontend tests prove required safety evidence uses the new source
  fields and endpoint.
- Review report documents the closed gaps with verification commands.

## Primary Files

- `src/tradingx/types.py`
- `src/tradingx/web/readmodels.py`
- `src/tradingx/web/app.py`
- `src/tradingx/gate3.py`
- `tests/unit/test_gate3.py`
- `tests/unit/test_web_readmodels.py`
- `tests/contract/test_local_web_app_api_contract.py`
- `webapp/src/types.ts`
- `webapp/src/api.ts`
- `webapp/src/control-center/state/DataContext.tsx`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`
- `webapp/src/control-center/flavors/OperatorMissionControlModel.ts`
- `webapp/src/control-center/__tests__/ControlCenterApp.test.tsx`
- `webapp/src/control-center/flavors/__tests__/OperatorMissionControlFlavor.test.ts`
