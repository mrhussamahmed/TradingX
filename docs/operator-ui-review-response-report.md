# Operator UI Review Response Report

Date: 2026-04-28
Status: ready for reviewer re-check

## Summary

Mission Control was updated so read-model timestamps and placeholder
labels cannot create false safety confidence. The safety verdict remains
evidence-first: missing required evidence keeps the posture stale or
missing, while known risk conditions such as failing gates still escalate
the verdict.

## Findings Addressed

### 1. Snapshot timestamps can make stale evidence look current

Status: fixed.

Required safety evidence no longer uses `commandCenter.generated_at_utc`
or `portfolio.generated_at_utc`. Command-center and portfolio timestamps
are still displayed as read-model context in their own cards, but they do
not satisfy the required safety evidence ledger.

Relevant code:

- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`
- `webapp/src/control-center/flavors/OperatorMissionControlModel.ts`

Regression coverage:

- `deriveGateEvidenceTimestamp` returns `null` for command-center
  read-model timestamps even when gate labels exist.
- Required portfolio evidence is passed as `null` until the backend
  exposes a source evidence timestamp.

### 2. Missing decisions are counted as decision evidence

Status: fixed.

Decision evidence now requires both:

- `runtimeSelection.selection_id`
- `runtimeSelection.generated_at_utc`

Placeholder labels such as `No decision yet`, `awaiting`, `pending`, and
`unavailable` return no decision evidence.

Regression coverage:

- Model test proves placeholder no-decision labels do not count.
- Model test proves real opportunity selection timestamps count.

### 3. Gate 3 failures do not affect the safety verdict

Status: fixed.

Mission Control now derives a combined gate tone from command-center gate
labels plus Gate 3 criteria. Failing or degraded Gate 3 criteria feed the
central safety verdict and attention queue.

Regression coverage:

- Model test proves failing Gate 3 criteria produce a risk gate tone.

### 4. Placeholder decisions still drive UI confidence

Status: fixed.

The visible UI now uses the same `decisionEvidenceAt` value as required
safety evidence:

- Decision card
- Missing-decision attention item
- Missing-evidence ledger
- Required safety evidence

When only the backend placeholder exists, Mission Control renders:

- `No decision evidence`
- `Missing selection-backed decision evidence`
- `No structured trade decision is available`

Regression coverage:

- App test renders Mission Control with `No decision yet` and verifies
  the missing-evidence UI remains visible.

### 5. Gate 3 freshness can still be read-time generated

Status: fixed in frontend safety model.

Gate 3 criteria still affect verdict severity, but
`gate3Readiness.generated_at_utc` no longer satisfies required gate
freshness. Until the backend exposes a persisted/source timestamp for
Gate 3 calculation lineage, required gate evidence remains missing.

Regression coverage:

- Model test proves Gate 3 report `generated_at_utc` does not satisfy
  gate freshness, even when criteria exist.

### 6. Pending Gate 3 criteria are treated as passing

Status: fixed.

Gate status aggregation now requires every status to explicitly match a
passing status such as `pass`, `ok`, `good`, `ready`, or `complete`
before returning a green gate tone. Pending, incomplete, unknown, or
unrecognized Gate 3 criteria now produce a watch tone and keep the gate
attention item visible.

Regression coverage:

- Model test proves a pending Gate 3 criterion produces a watch gate
  tone instead of a good tone.
- Model test proves `incomplete` and `not_ready` do not match passing
  statuses by substring.

### 7. Missing-evidence ledger omits required gate evidence

Status: fixed.

The Evidence Trust Ledger no longer maintains a separate missing-evidence
counter. Its missing-evidence row now uses the same
`requiredSafetyEvidence.missing` and `requiredSafetyEvidence.staleClasses`
values as the Evidence Freshness card.

Regression coverage:

- App test proves the required safety evidence gap string appears in
  both the freshness card and the ledger row.

## Verification Commands

```bash
npm --prefix webapp test
npm --prefix webapp run lint -- --quiet
npm --prefix webapp run build
```

Latest local result:

- `npm --prefix webapp test`: passed, 87 tests.
- `npm --prefix webapp run lint -- --quiet`: passed.
- `npm --prefix webapp run build`: passed.

Expected build note: Vite still reports the existing chunk-size warning.
This warning is unchanged and not introduced by the Mission Control
review fixes.

## Remaining Backend Gaps

- No source timestamp for portfolio safety evidence.
- No source timestamp for Gate 3 criteria lineage that is independent of
  report read time.
- No structured decision-detail endpoint with signal, regime, risk,
  execution, mode, and freshness fields.

The UI now labels these as missing or unavailable rather than treating
read-model freshness as source evidence.
