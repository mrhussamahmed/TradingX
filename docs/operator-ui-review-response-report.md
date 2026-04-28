# Operator UI Backend Gap Review Response Report

Date: 2026-04-28
Status: ready for adversarial re-check

## Summary

The approved backend gap plan has been implemented. Mission Control now
uses source-backed backend evidence for portfolio, Gate 3, and runtime
decision freshness instead of render timestamps. The UI still fails
closed when source evidence is absent, incomplete, stale, or
structurally inconsistent.

Source plan:

- `docs/operator-ui-backend-gap-plan.md`
- `docs/operator-ui-backend-gap-implementation-plan.md`

## Closed Backend Gaps

### 1. Portfolio Source Evidence

Status: fixed.

Closing code path:

- `src/tradingx/types.py`
- `src/tradingx/web/readmodels.py`
- `webapp/src/types.ts`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`

`PortfolioWorkspaceSnapshot` now exposes source evidence timestamps:

- `source_evidence_at_utc`
- `account_position_source_at_utc`
- `execution_journal_source_at_utc`
- `closed_trade_source_at_utc`

Required Mission Control portfolio evidence uses
`portfolio.source_evidence_at_utc`. OMS journal and closed-trade
timestamps remain diagnostic only.

Safety behavior:

- No account/position evidence leaves required portfolio evidence
  missing.
- One-sided split evidence leaves required portfolio evidence missing.
- Split account/position evidence uses the older timestamp.
- Service cycle `completed_at_utc` is not used as source evidence when
  explicit account/position source timestamps are absent.
- Fresh OMS or closed-trade activity cannot refresh stale or missing
  account/position evidence.

Regression coverage:

- `tests/unit/test_web_readmodels.py`
- `webapp/src/control-center/flavors/__tests__/OperatorMissionControlFlavor.test.ts`

### 2. Gate 3 Source Lineage

Status: fixed.

Closing code path:

- `src/tradingx/types.py`
- `src/tradingx/gate3.py`
- `src/tradingx/web/readmodels.py`
- `webapp/src/types.ts`
- `webapp/src/control-center/flavors/OperatorMissionControlModel.ts`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`

Gate 3 criteria now carry source lineage:

- criterion-level `source_evidence_at_utc`
- criterion-level `required`
- report-level `required_criterion_ids`
- report-level `missing_source_criterion_ids`
- report-level `oldest_required_source_evidence_at_utc`
- report-level `latest_source_evidence_at_utc`
- report-level `source_evidence_at_utc` as the oldest-required alias

Mission Control uses the backend-exposed required set and the oldest
required source timestamp. `latest_source_evidence_at_utc` is diagnostic
only.

Safety behavior:

- One fresh criterion cannot satisfy required Gate 3 evidence when
  another required criterion is missing.
- Optional diagnostic criteria do not satisfy or block required Gate 3
  evidence.
- Zero-P1 evidence requires an explicit scan-window evidence boundary.
- `generated_at_utc` and current read time do not satisfy source
  evidence.
- Persisted Gate 3 reports preserve report-level and criterion-level
  source lineage on readback.
- Legacy persisted reports without source timestamps remain
  missing-source unless regenerated or proven from their own evidence.

Regression coverage:

- `tests/unit/test_gate3.py`
- `tests/unit/test_web_readmodels.py`
- `webapp/src/control-center/flavors/__tests__/OperatorMissionControlFlavor.test.ts`

### 3. Runtime Decision Detail

Status: fixed.

Closing code path:

- `src/tradingx/types.py`
- `src/tradingx/web/readmodels.py`
- `src/tradingx/web/app.py`
- `webapp/src/types.ts`
- `webapp/src/api.ts`
- `webapp/src/control-center/state/DataContext.tsx`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`

The backend now exposes:

```text
GET /api/runtime-host/decision/latest
```

The endpoint returns structured signal, regime, risk, execution, mode,
and freshness details. Required decision evidence uses
`RuntimeDecisionDetail.decision_source_at_utc`, which is exactly the
opportunity selection timestamp.

Safety behavior:

- No selection returns `null`.
- Fresh heartbeat, runtime context, activation, exposure, or OMS context
  cannot refresh an old decision.
- Selection-backed `no_trade` is valid decision evidence.
- `no_trade` with no ranked opportunities uses explicit null numeric
  fields and `signal.available=false`.
- Missing activation keeps threshold and threshold gap unknown instead of
  inventing a zero threshold.
- `selected` decisions whose `selected_symbol` is absent from ranked
  opportunities return a deterministic structured inconsistency instead
  of falling back to the top-ranked opportunity.

Regression coverage:

- `tests/unit/test_types.py`
- `tests/unit/test_web_readmodels.py`
- `tests/contract/test_local_web_app_api_contract.py`
- `webapp/src/control-center/__tests__/ControlCenterApp.test.tsx`
- `webapp/src/control-center/flavors/__tests__/OperatorMissionControlFlavor.test.ts`

### 4. Mission Control Evidence Wiring

Status: fixed.

Closing code path:

- `webapp/src/control-center/flavors/OperatorMissionControlModel.ts`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`
- `webapp/src/control-center/state/DataContext.tsx`

Mission Control required safety evidence now consumes:

- heartbeat source evidence from the existing heartbeat path
- Gate 3 oldest required source evidence plus missing required criteria
- portfolio source evidence from `portfolio.source_evidence_at_utc`
- runtime decision evidence from
  `runtimeDecisionDetail.decision_source_at_utc`

The Evidence Freshness card and Evidence Trust Ledger share the same
`RequiredSafetyEvidence` derivation.

Regression coverage:

- model tests prove render timestamps do not satisfy required evidence
- app tests prove the decision endpoint is fetched and missing fallback
  remains conservative
- UI tests prove missing gate, portfolio, and decision source evidence
  remain visible

## Verification Commands

```bash
.venv/bin/python -m pytest tests/unit/test_types.py tests/unit/test_web_readmodels.py tests/unit/test_gate3.py tests/contract/test_local_web_app_api_contract.py tests/unit/test_web_app.py
npm --prefix webapp test
npm --prefix webapp run lint -- --quiet
npm --prefix webapp run build
git diff --check
```

Latest local result:

- `.venv/bin/python -m pytest ...`: passed, 95 tests, 13 warnings.
- `npm --prefix webapp test`: passed, 93 tests.
- `npm --prefix webapp run lint -- --quiet`: passed.
- `npm --prefix webapp run build`: passed.
- `git diff --check`: passed.

Expected build note: Vite still reports the existing chunk-size warning.
This warning is unchanged by the backend evidence work.

## Remaining Limitations

- Portfolio required source evidence currently derives from explicit
  account/position source timestamps on service-cycle snapshots. A
  future broker-native account/position artifact can replace or tighten
  that source without changing the Mission Control contract.
- Gate 3 legacy persisted reports without source fields still fail
  closed unless regenerated or backed by their own evidence references.
- Runtime decision detail is read-only and complements
  `/api/runtime-host/selection/latest`; it does not change trading
  permissions or Gate 3 promotion authority.
