# Tranche 2.1 Task 16 P&L Monitor Activation Plan

> **For agentic workers:** keep this commit narrow. This is an
> activation follow-up, not another ledger refactor. The target is one
> small reviewable branch that turns `pnl::<sleeve_id>` into a real
> ledger-backed monitor for both sleeves without reopening DESIGN-0019.

**Goal:** execute Task 16 from
[DESIGN-0017](../specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md#W10--stage-2-drift-pl-divergence-activation-follow-up-commit)
and Task 12 from
[the ledger plan](./2026-04-22-tranche-2-1-stage-2-sleeve-position-ledger-attribution-plan.md):

1. keep the merged sleeve-ledger foundation as-is;
2. treat `pnl::<sleeve_id>` as an **active** drift monitor for both
   shipped sleeves;
3. keep `pending` only for real runtime blockers
   (insufficient live days, gap days, unresolved reserve positions,
   reserve cash above threshold, or incomplete equity reconstruction);
4. surface the resulting severity in the dashboard from
   `drift_monitor_verdicts`, not from alert side effects; and
5. avoid any manual soak prerequisite in code. Evidence can continue
   accumulating after merge; the monitor simply stays pending until its
   own prerequisites clear.

## Activation contract

Task 16 **does not** mean “force real verdicts on day 1.” It means:

- the runtime now considers `pnl::<sleeve_id>` part of the live drift
  stack for both sleeves;
- when the ledger window is clean, the gateway emits
  `info` / `warning` / `critical` verdicts from real live-vs-backtest
  divergence math; and
- when the window is not clean, the gateway emits `pending` with an
  explicit blocker reason instead of pretending the monitor is still
  unimplemented.

This keeps development complete **now** while still remaining
fail-closed in production data windows that are not ready yet.

## Review-sensitive locks

These are the seams most likely to create review churn. Treat them as
non-negotiable:

1. **No threshold retuning in this commit.** Task 16 activates the
   ledger-backed monitor using the already-shipped
   `DriftThresholds`. If threshold recalibration is needed later, that
   is a separate tuning commit with fresh evidence.
2. **No new store root.** All Task 16 reads come from the top-level
   `runtime_store`, matching the merged ledger design.
3. **No second activation-specific reader seam.** Reserve readiness
   lives on the existing `StoreBackedAttributionRecordsReader`, because
   it already owns the runtime-root attribution/gap read path.
4. **Dashboard severity must come from verdict records, not
   `operator_alerts`.** Alert-based severity loses `info` verdicts and
   silently shows `pending` when the monitor is actually healthy.
5. **`ArtifactBackedDriftAlarmStateReader.has_alarm(...)` stays
   critical-only.** Task 16 may extend it with read-only helpers, but
   must not change its sleeve-halt semantics.
6. **Reserve blockers are hard pending states.** If unresolved reserve
   positions exist anywhere inside the P&L monitor window, or reserve
   cash exceeds the activation threshold inside that window,
   `pnl::<sleeve_id>` stays pending.
7. **Pending aggregation for the dashboard is explicit.** Per-sleeve
   dashboard severity for the latest verdict batch uses:
   `critical > warning > pending > info`. This avoids the current
   alert-driven ambiguity.
8. **Reserve-cash threshold is concrete in code.** Use:
   `max(5% of broker equity, PortfolioConstructionConfig.min_trade_notional)`.
   For each reserve snapshot day, reconstruct broker equity as:
   `sum(active-sleeve ending_equity for that trading_day) + residual reserve cash + residual reserve market_value`.
9. **Incomplete equity reconstruction is a blocker.** If the runtime
   cannot reconstruct broker equity for a reserve snapshot day inside
   the window, the monitor stays pending rather than underestimating the
   reserve-cash threshold.

## Scope

This plan is intentionally smaller than DESIGN-0019. It activates a
monitor that now has trustworthy sleeve returns; it does **not** reopen
ledger bootstrap, replay, gap semantics, or runtime-state-root work.

### In scope

- reserve-aware activation gating inside the drift P&L verdict path;
- typed runtime-store reads needed to evaluate reserve readiness across
  the monitor window;
- dashboard drift severity derived from the latest persisted verdict
  batch instead of alert side effects;
- direct unit/integration coverage that proves both sleeves now produce
  real `pnl::<sleeve_id>` verdicts when clean; and
- explicit regression coverage for pending blocker reasons.

### Out of scope

- new ledger artifacts or schema changes;
- modified `SleeveDailyReturnsReader` or live-Sharpe gate semantics
  beyond the already-merged gap hardening;
- threshold tuning or recalibration;
- operator soak / paper-session validation as a code prerequisite;
- CPCV / PBO work; and
- UI redesign beyond correcting the drift severity source.

## Modified files

- `src/tradingx/drift/gateway.py`
- `src/tradingx/persistence.py`
- `src/tradingx/web/readmodels.py`
- `tests/unit/test_drift_gateway.py`
- `tests/unit/test_dashboard_two_sleeve_view.py`
- `tests/integration/test_drift_end_to_end.py`

No `INDEX.md` change is needed. Plan files under
`docs/superpowers/plans/` are not frontmatter-indexed.

## Implementation shape

Task 16 is one narrow production change with three moving parts:

1. **Gateway activation blockers**
   `StoreBackedAttributionRecordsReader` grows a reserve-readiness
   helper that the gateway can query before computing
   `compute_live_vs_backtest_pnl_divergence(...)`.

2. **Typed reserve window reads**
   Persistence grows the smallest typed read helper needed to evaluate
   residual reserve snapshots across the same rolling window the P&L
   monitor uses.

3. **Verdict-backed dashboard severity**
   The workspace readmodel stops inferring drift state from alerts and
   instead summarizes the latest persisted verdict batch.

That is the whole activation. No other subsystem should move.

---

## Task 1 — Reserve-aware P&L activation blockers

**Goal:** make `pnl::<sleeve_id>` truly active by encoding the
remaining DESIGN-0019 preconditions directly into the live gateway.

### Files

- `src/tradingx/drift/gateway.py`
- `src/tradingx/persistence.py`
- `tests/unit/test_drift_gateway.py`

### TDD steps

- [ ] Add failing tests in `tests/unit/test_drift_gateway.py` for:
  - both sleeves emit non-`pending` `pnl::<sleeve_id>` verdicts when
    given 30+ clean ledger-based daily returns plus matching backtest
    series;
  - unresolved reserve positions inside the 60-day P&L window force
    `pnl::<sleeve_id>` to stay `pending` for both sleeves;
  - reserve cash above threshold inside the window forces
    `pnl::<sleeve_id>` to stay `pending`;
  - missing daily attribution needed to reconstruct broker equity for a
    reserve snapshot day forces `pnl::<sleeve_id>` to stay `pending`.
- [ ] Verify those tests fail against current `main`.
- [ ] Add the smallest typed reserve reader in `src/tradingx/persistence.py`:
  `list_residual_reserve_snapshots() -> tuple[ResidualReserveSnapshot, ...]`.
- [ ] Extend `StoreBackedAttributionRecordsReader` in
  `src/tradingx/drift/gateway.py` with a reserve-readiness helper for
  the P&L window. It must:
  - inspect residual reserve snapshots whose `trading_day` falls inside
    `window_days`;
  - block if any snapshot still has unresolved reserve positions;
  - reconstruct broker equity day-by-day from same-day
    `SleeveDailyAttributionRecord.ending_equity` for the active sleeves
    plus reserve cash and reserve market value;
  - block if equity reconstruction is incomplete for any reserve
    snapshot day; and
  - block if reserve cash exceeds
    `max(5% of broker equity, PortfolioConstructionConfig.min_trade_notional)`.
- [ ] Wire `_pnl_verdicts()` to call the helper before
  `compute_live_vs_backtest_pnl_divergence(...)`.
  If blockers exist, emit `pending` with explicit details and skip the
  divergence calculation.
- [ ] Keep existing insufficient-live-days and gap behavior intact.
- [ ] Re-run the Task 1 test slice until green.

### Lock

Do **not** create a separate `PnlActivationReadinessReader` constructor
seam. The existing store-backed attribution reader already owns the
runtime-root artifacts this logic needs.

---

## Task 2 — Verdict-backed dashboard severity

**Goal:** make the operator dashboard reflect the actual latest drift
batch, including `info`, instead of using warning/critical alerts as a
proxy.

### Files

- `src/tradingx/drift/gateway.py`
- `src/tradingx/web/readmodels.py`
- `tests/unit/test_dashboard_two_sleeve_view.py`
- `tests/unit/test_drift_gateway.py`

### TDD steps

- [ ] Add failing tests in `tests/unit/test_dashboard_two_sleeve_view.py`
  for:
  - clean latest verdict batch -> active sleeves show `info`, not
    `pending`;
  - mixed latest batch (`ks::...=info`, `pnl::...=pending`) ->
    dashboard severity aggregates to `pending`;
  - any `critical` verdict in the latest batch dominates the sleeve’s
    displayed severity.
- [ ] Verify the tests fail while the readmodel still parses
  `operator_alerts`.
- [ ] Extend `ArtifactBackedDriftAlarmStateReader` or an adjacent helper
  in `src/tradingx/drift/gateway.py` with a read-only latest-batch
  severity map:
  - use only the latest persisted verdict batch by `recorded_at_utc`;
  - group by `sleeve_id`;
  - ignore portfolio-level records where `sleeve_id is None`; and
  - aggregate by precedence:
    `critical > warning > pending > info`.
- [ ] Keep `has_alarm(...)` unchanged: it still answers only
  “is there a latest-batch critical for this sleeve?”
- [ ] Replace `_latest_drift_severity_by_sleeve()` in
  `src/tradingx/web/readmodels.py` so it reads latest verdict batch
  severity instead of alert summaries.
- [ ] Re-run Task 2 tests until green.

### Lock

This task is not allowed to derive sleeve severity from
`operator_alerts`. Alerts are delivery artifacts, not authoritative
state.

---

## Task 3 — End-to-end P&L activation regression

**Goal:** prove the gateway now produces real `pnl::<sleeve_id>`
verdicts for both sleeves inside a realistic verdict batch.

### Files

- `tests/integration/test_drift_end_to_end.py`
- `tests/unit/test_drift_gateway.py`

### TDD steps

- [ ] Extend `tests/integration/test_drift_end_to_end.py` with 30+
  daily attribution records and matching backtest series for both
  sleeves.
- [ ] Assert the refreshed verdict batch includes:
  - `pnl::trend-following-v1`
  - `pnl::vol-target-v1`
  and that neither verdict is `pending` when the window is clean.
- [ ] Keep existing regression expectations for PSI / KS / execution
  verdicts.
- [ ] Add one explicit unit regression in
  `tests/unit/test_drift_gateway.py` that confirms the latest batch can
  still contain `pending` P&L verdicts for valid blocker reasons while
  the monitor remains “implemented.”
- [ ] Re-run Task 3 tests until green.

### Lock

The activation commit should prove both sleeves can produce real P&L
verdicts, but it must also preserve `pending` as the correct outcome
for blocker windows.

---

## Task 4 — Verification and handoff

### Required verification

- [ ] `uv run ruff check src/tradingx tests`
- [ ] `uv run mypy src/tradingx`
- [ ] `uv run pytest -q tests/unit/test_drift_gateway.py tests/unit/test_dashboard_two_sleeve_view.py tests/integration/test_drift_end_to_end.py`
- [ ] `uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py`
- [ ] `python3 scripts/check_index.py`
- [ ] `./scripts/validate`

### Commit

- [ ] Commit once with a message in this shape:
  `feat(drift): activate pnl::<sleeve_id> monitor with ledger-backed readiness gating`

### Reviewer handoff

The implementation report should call out:

1. where reserve blockers now live;
2. the exact reserve-cash threshold formula used;
3. the dashboard severity aggregation rule;
4. confirmation that `has_alarm(...)` stayed critical-only; and
5. which tests prove real non-pending P&L verdicts for both sleeves.

---

## Expected outcome

After this plan lands:

- the drift stack treats `pnl::<sleeve_id>` as a real monitor for both
  sleeves;
- a clean ledger window produces real `info` / `warning` / `critical`
  P&L verdicts for both sleeves;
- blocker windows still produce explicit `pending` verdicts instead of
  silent false confidence;
- the dashboard shows the latest per-sleeve drift state from persisted
  verdicts rather than alert side effects; and
- no additional soak-only development step remains before this feature
  is considered implemented.
