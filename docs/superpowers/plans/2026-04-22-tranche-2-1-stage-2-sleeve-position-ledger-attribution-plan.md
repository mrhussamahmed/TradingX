# Tranche 2.1 Stage 2 Sleeve Position Ledger Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute
[DESIGN-0019](../specs/2026-04-22-tranche-2-1-stage-2-sleeve-position-ledger-attribution-design.md)
— replace the current portfolio-return proxy in the tranche-2.1
close path with a real sleeve-level accounting layer that:

1. bootstraps already-open broker positions without discarding them;
2. persists sleeve ledger state plus a residual reserve;
3. computes sleeve-specific daily returns from sleeve-owned cash and
   holdings;
4. hardens the drift and live-Sharpe readers around explicit gap
   artifacts; and
5. leaves [Task 16 from DESIGN-0017](../specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md#W10--stage-2-drift-pl-divergence-activation-follow-up-commit)
   as a later single-commit activation.

**Stage 1 (Tasks 1–11)** ships only the accounting foundation.
At Stage 1 merge:

- the runtime still writes and reads the same public
  `SleeveDailyAttributionRecord` artifact family;
- `pnl::<sleeve_id>` remains pending;
- no drift threshold is activated or tightened;
- already-open broker inventory is preserved through bootstrap; and
- the new runtime state is durable, rerunnable, and explicit about
  gaps.

**Stage 2 (Task 12)** remains the deferred activation commit: it
flips `pnl::<sleeve_id>` active only after the new ledger has
accrued enough history and the reserve/gap preconditions are green.

## Review-sensitive locks

These are the specific seams that repeatedly produced adversarial
review findings. The implementation plan treats them as
non-negotiable:

1. **Activation durability owner:** `LocalActivationGateway` owns
   snapshot-payload persistence and idempotent backfill, and must
   receive both `operator_store` and `runtime_snapshot_store`.
2. **Runtime-state root:** bootstrap, residual reserve, sleeve
   ledger, sleeve decomposition, sleeve attribution, and gap
   artifacts all live under the top-level `runtime_store`, not
   `paper_loop/`.
3. **Decomposition continuity writer:** the existing
   `PaperTradingService._write_sleeve_decomposition_record_if_available`
   writer must move to the same runtime-root store the planner
   reads from.
4. **Reserve-domain runtime path:** reserve inventory must have a
   real planner-driven sell path using
   `candidate_id="residual-reserve-bootstrap"` and
   `("__residual_reserve__", 1)` attribution, not just a ledger-side
   serialization convention.
5. **Close-path durability:** session-open state and execution
   artifacts must be replayable after restart; in-memory-only open
   state is insufficient.
6. **Gap posture:** both the drift P&L divergence path and the
   `LIVE_DAILY_RETURNS` Sharpe-gate path must treat gaps as pending /
   insufficient history, never as silent shortened series.

## Architecture

The implementation stays additive and keeps the accounting logic
isolated from broker-facing order placement:

- new record types live in `src/tradingx/types.py`;
- filesystem persistence stays in `src/tradingx/persistence.py`;
- pure bootstrap/replay/valuation logic moves into a new
  `src/tradingx/drift/sleeve_ledger.py` helper module;
- `SleeveAttributionRecorder` becomes the close-path orchestrator
  that loads opening state, replays executions, writes ledger and
  reserve snapshots, and emits daily attribution plus gap records;
- `LocalActivationGateway` gets the dual-store snapshot-durability
  seam;
- `RuntimePortfolioPlanner` and `PaperTradingService` get a
  dedicated `runtime_state_store` seam so decomposition continuity
  and reserve-liquidation reads/writes share the same root; and
- Task 12 later reuses these artifacts without changing their
  public shape.

This does **not** rewrite the broker controller, sleeves, cost
model, or validation stack. It also does **not** add intraday
mutable ledger state to the live service loop; ledger truth is
still derived at close from persisted facts.

## Tech Stack

Python 3.11. `Decimal` at all numeric boundaries. `dataclasses`
for record types. Existing `FilesystemArtifactStore`. Existing
`pytest` + `uv run` workflow. No new runtime dependencies.
Modified Dietz math is implemented in pure Python inside the new
ledger helper module.

---

## Scope

Implements DESIGN-0019 §W1–§W8 in this order:

1. **W1** — new bootstrap / ledger / reserve / gap dataclasses plus
   `SleeveDailyAttributionRecord` extension.
2. **W2** — persistence helpers, snapshot-by-id loading, typed
   execution-lifecycle listing, and new artifact categories.
3. **Activation durability seam** — dual-store
   `LocalActivationGateway` and `ensure_activation_snapshot_payloads`
   on unchanged activation reuse.
4. **Runtime-state root unification** — dedicated
   `runtime_state_store` seams in planner + service and migration of
   the decomposition writer off `paper_store`.
5. **Session-open durability** — persist and reload
   `SessionOpenPortfolioStateRecord` at preopen/close.
6. **W3 + W4** — bootstrap engine and one-time ledger genesis.
7. **W5 + W6 + W7** — replay engine, reserve handling, invariants,
   Modified Dietz return computation, and close-path integration in
   `SleeveAttributionRecorder`.
8. **Reserve-domain runtime path** — planner emits reserve-domain
   liquidation intents until residual inventory is zero.
9. **W8 drift/live-return hardening** — gap-aware attribution
   windows, P&L divergence pending logic, and live-Sharpe
   insufficient-history behavior.
10. **Integration + closing pass** — end-to-end market-day test,
    operator-evidence categories, DESIGN-0019 status bump to active,
    full regression sweep.
11. **Task 12 [deferred]** — activate `pnl::<sleeve_id>` after the
    new ledger has matured and reserve/gap preconditions are green.

Out of scope in this plan:

- manual position mapping;
- FIFO/LIFO tax lots;
- intraday NAV snapshots;
- changing Gate 1 / Gate 2 / CPCV behavior;
- changing the public shape of `TradeIntent`,
  `ExecutionLifecycleRecord`, or `ClosedTradeRecord`;
- activating `pnl::<sleeve_id>` in Stage 1.

## File structure

### New files

- `src/tradingx/drift/sleeve_ledger.py`
  - pure bootstrap/replay/valuation/gap helpers:
    `build_bootstrap_allocation(...)`,
    `apply_execution_replay(...)`,
    `compute_modified_dietz_return(...)`,
    and small deterministic helper functions.
- `tests/unit/test_sleeve_ledger_bootstrap.py`
- `tests/unit/test_sleeve_ledger_replay.py`
- `tests/unit/test_sleeve_ledger_daily_returns.py`
- `tests/unit/test_activation_snapshot_payloads.py`
- `tests/unit/test_runtime_state_store_roots.py`
- `tests/unit/test_residual_reserve_trade_intents.py`
- `tests/unit/test_drift_gap_awareness.py`
- `tests/integration/test_stage2_sleeve_position_ledger_close.py`
- `tests/integration/test_stage2_residual_reserve_liquidation.py`

### Modified files

- `src/tradingx/types.py`
- `src/tradingx/persistence.py`
- `src/tradingx/activation.py`
- `src/tradingx/automation.py`
- `src/tradingx/service.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/__main__.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/drift/attribution.py`
- `src/tradingx/drift/gateway.py`
- `src/tradingx/drift/live_returns_source.py`
- `src/tradingx/drift/pnl_divergence.py`
- `docs/superpowers/specs/2026-04-22-tranche-2-1-stage-2-sleeve-position-ledger-attribution-design.md`
- `docs/INDEX.md`

### Untouched (intentional)

- `src/tradingx/controller.py`
  - expected to remain schema-compatible because it already copies
    `trade_intent.sleeve_attributions` straight through.
- `src/tradingx/execution.py`
  - reserve-domain owner ids should flow through existing
    attribution-threading behavior.
- `src/tradingx/validation.py`, `src/tradingx/pbo.py`,
  tranche-2.2 CPCV artifacts.
- sleeves, cost model, and broker client integrations.

---

## Task 1 — Record shapes and backwards-compatible schema extension

**Files:**
- modify `src/tradingx/types.py`
- create `tests/unit/test_sleeve_ledger_bootstrap.py`
- create `tests/unit/test_sleeve_ledger_daily_returns.py`

- [ ] **Step 1: Write failing tests**
  - assert the new dataclasses exist and are frozen:
    `BootstrapPositionAllocation`,
    `ResidualPositionAllocation`,
    `SleeveBootstrapAllocationRecord`,
    `SleeveLedgerPosition`,
    `SleevePositionLedgerSnapshot`,
    `ResidualReserveSnapshot`,
    `SessionOpenPortfolioStateRecord`,
    `SleeveAttributionGapRecord`
  - assert `SleeveDailyAttributionRecord` still deserializes legacy
    payloads with all new fields defaulting to `None`
  - assert `TradeIntent` / `ExecutionLifecycleRecord` /
    `ClosedTradeRecord` shapes remain unchanged

- [ ] **Step 2: Implement**
  - add the new dataclasses exactly as named in DESIGN-0019
  - extend `SleeveDailyAttributionRecord` with:
    `realized_pnl`, `unrealized_pnl`, `cash_balance`,
    `calculation_mode`, `bootstrap_confidence`, `ledger_genesis_id`
  - do **not** add new attribution fields to trade/execution/closed
    trade dataclasses

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_sleeve_ledger_bootstrap.py tests/unit/test_sleeve_ledger_daily_returns.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(types): add DESIGN-0019 ledger record shapes"`

---

## Task 2 — Persistence helpers and runtime-state categories

**Files:**
- modify `src/tradingx/persistence.py`
- update tests from Task 1 and add category round-trip assertions

- [ ] **Step 1: Write failing tests**
  - writer/reader round-trip for:
    - `SleeveBootstrapAllocationRecord`
    - `SleevePositionLedgerSnapshot`
    - `ResidualReserveSnapshot`
    - `SessionOpenPortfolioStateRecord`
    - `SleeveAttributionGapRecord`
  - `list_execution_lifecycle_records(trading_day=...)` returns typed
    records sorted by `filled_at_utc`, then `execution_id`
  - `load_approved_weight_snapshot_by_snapshot_id(snapshot_id=...)`
    returns the exact persisted payload
  - operator evidence report includes the new categories

- [ ] **Step 2: Implement**
  - add writers/readers/list helpers to `FilesystemArtifactStore`
  - register categories:
    - `sleeve_bootstrap`
    - `sleeve_position_ledger`
    - `residual_reserve`
    - `session_open_portfolio_state`
    - `sleeve_attribution_gaps`
  - keep `sleeve_decomposition` and `sleeve_daily_attribution`
    existing categories intact

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_sleeve_ledger_bootstrap.py tests/unit/test_sleeve_ledger_daily_returns.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(persistence): add DESIGN-0019 runtime-state helpers"`

---

## Task 3 — Activation snapshot durability and unchanged-reuse backfill

**Files:**
- modify `src/tradingx/activation.py`
- modify `src/tradingx/automation.py`
- modify `src/tradingx/service.py`
- modify `src/tradingx/web/runtime.py`
- modify `src/tradingx/__main__.py`
- create `tests/unit/test_activation_snapshot_payloads.py`

- [ ] **Step 1: Write failing tests**
  - `LocalActivationGateway` writes captured snapshot payloads into the
    dedicated runtime snapshot store during fresh blueprint activation
  - unchanged `load_or_activate_blueprint(...)` reuse still runs
    `ensure_activation_snapshot_payloads(...)`
  - reuse succeeds when payload already exists in `runtime_store`
  - reuse fails closed when the captured snapshot id exists on the
    activation record but no matching payload can be reconstructed
  - activation wiring in `build_default_market_day_automation_runner`
    passes both `operator_store` and `runtime_store`
  - activation wiring in `build_default_paper_service()` also passes
    both `operator_store` and `runtime_store`, so the live
    `service_builder=lambda: build_default_paper_service(config)` path
    does not regress to a single-store gateway
  - `build_runtime_host_paper_service()` passes the dual-store gateway
    into `LiveOpportunitySelector`, so the runtime-host paper-service
    path does not regress
  - `build_default_local_web_components()` passes a dual-store gateway
    into `LocalRuntimeHostManager`, so the web/runtime-host manager path
    does not regress
  - the CLI/runtime entrypoints in `src/tradingx/__main__.py`
    (`runtime-plan`, `runtime-start`) also instantiate dual-store
    gateways instead of keeping a hidden single-store constructor

- [ ] **Step 2: Implement**
  - add optional `runtime_snapshot_store` to `LocalActivationGateway`
  - persist strategy snapshots and captured sleeve snapshots into that
    store by `snapshot_id`
  - add an internal
    `ensure_activation_snapshot_payloads(active_activation, blueprint)`
    helper used on unchanged reuse
  - update both construction paths that instantiate
    `LocalActivationGateway`:
    - `build_default_market_day_automation_runner(...)`
    - `build_default_paper_service(...)`
    - `build_runtime_host_paper_service(...)`
    - `build_default_local_web_components(...)`
    - `src/tradingx/__main__.py` runtime CLI entrypoints
  - keep activation-status semantics unchanged

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_activation_snapshot_payloads.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(activation): backfill captured snapshot payloads"`

---

## Task 4 — Runtime-state store unification and decomposition writer migration

**Files:**
- modify `src/tradingx/runtime_portfolio.py`
- modify `src/tradingx/service.py`
- create `tests/unit/test_runtime_state_store_roots.py`

- [ ] **Step 1: Write failing tests**
  - planner continuity reads use `runtime_state_store`, not the old
    `artifact_store=paper_store` path
  - `PaperTradingService._write_sleeve_decomposition_record_if_available`
    writes `SleeveDecompositionRecord` to the runtime-root store
  - `build_default_paper_service()` binds the same `runtime_store` to:
    - planner continuity reads
    - decomposition continuity writes
  - paper-loop artifacts such as `runtime_portfolio_plan` still remain
    under `paper_store`

- [ ] **Step 2: Implement**
  - add optional `runtime_state_store` to `RuntimePortfolioPlanner`
    and read decomposition continuity from:
    `runtime_state_store or artifact_store`
  - add optional `runtime_state_store` to `PaperTradingService`
    and route decomposition writes there
  - bind both from `build_default_paper_service(config)`
  - keep existing public constructor call sites backward compatible by
    making the new seam additive

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_runtime_state_store_roots.py tests/unit/test_runtime_portfolio.py tests/unit/test_service.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(runtime): unify DESIGN-0019 runtime-state roots"`

---

## Task 5 — Session-open durability and ordered execution replay inputs

**Files:**
- modify `src/tradingx/automation.py`
- extend tests from Tasks 2 and 4
- integration test scaffolding in `tests/integration/test_stage2_sleeve_position_ledger_close.py`

- [ ] **Step 1: Write failing tests**
  - preopen persists `SessionOpenPortfolioStateRecord` into
    `runtime_store`
  - close path prefers the persisted open-state record when present
  - close path can still use the in-memory open state within the same
    process
  - execution-lifecycle list helper is ordered by `filled_at_utc`,
    then `execution_id`, not filesystem iteration order

- [ ] **Step 2: Implement**
  - add a runtime-root store seam to `MarketDayAutomationRunner`
  - persist session-open state during `_execute_preopen()`
  - teach `_execute_close()` / `SleeveAttributionRecorder` to load the
    persisted record when needed
  - make replay ordering explicit and reusable

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_runtime_state_store_roots.py tests/integration/test_stage2_sleeve_position_ledger_close.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(automation): persist session-open state for ledger replay"`

---

## Task 6 — Pure bootstrap engine

**Files:**
- create `src/tradingx/drift/sleeve_ledger.py`
- expand `tests/unit/test_sleeve_ledger_bootstrap.py`

- [ ] **Step 1: Write failing tests**
  - `history_exact` assigns quantities from attributed execution history
  - `history_rounding_adjusted` only applies de minimis deterministic
    correction
  - `blueprint_fallback` uses captured snapshot payloads loaded by
    `snapshot_id`, not current strategy YAML
  - unresolved or no-owner symbols stay in residual reserve
  - bootstrap is one-time: activation changes after ledger genesis do
    not reassign existing inventory
  - existing broker cash starts fully in residual reserve

- [ ] **Step 2: Implement**
  - add pure bootstrap helpers that take:
    - active `BlueprintActivationRecord`
    - resolved captured snapshots
    - session-open `PortfolioState`
    - historical `ExecutionLifecycleRecord`s
  - emit:
    - `SleeveBootstrapAllocationRecord`
    - initial `SleevePositionLedgerSnapshot`s
    - initial `ResidualReserveSnapshot`
  - keep history scaling forbidden beyond tiny rounding-only
    adjustment

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_sleeve_ledger_bootstrap.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(drift): add sleeve ledger bootstrap engine"`

---

## Task 7 — Pure replay engine, invariants, and Modified Dietz daily return

**Files:**
- modify `src/tradingx/drift/sleeve_ledger.py`
- expand `tests/unit/test_sleeve_ledger_replay.py`
- expand `tests/unit/test_sleeve_ledger_daily_returns.py`

- [ ] **Step 1: Write failing tests**
  - weighted-average-cost replay for buys and sleeve-domain sells
  - reserve-domain sell reduces reserve quantity and books no sleeve
    realized P&L
  - reserve->sleeve buy funding is positive external flow
  - sleeve->reserve sale proceeds are negative external flow
  - Modified Dietz uses individually weighted signed flows; it does not
    net intraday offsetting flows before weighting
  - fully liquidated symbols take the explicit zero-quantity close
    branch
  - invariant failures emit `SleeveAttributionGapRecord` instead of
    fabricated ownership

- [ ] **Step 2: Implement**
  - add deterministic replay helpers in `sleeve_ledger.py`
  - add Modified Dietz helper
  - add invariant evaluation that returns explicit gap records and
    prevents false daily returns
  - keep the logic pure and reusable by both unit and integration
    tests

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_sleeve_ledger_replay.py tests/unit/test_sleeve_ledger_daily_returns.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(drift): add replay and daily return ledger math"`

---

## Task 8 — Close-path integration in `SleeveAttributionRecorder`

**Files:**
- modify `src/tradingx/drift/attribution.py`
- modify `src/tradingx/automation.py`
- expand `tests/integration/test_stage2_sleeve_position_ledger_close.py`

- [ ] **Step 1: Write failing tests**
  - when decomposition exists, close-path attribution writes:
    - updated sleeve ledger snapshots
    - updated residual reserve snapshot
    - new `SleeveDailyAttributionRecord`s with
      `calculation_mode="sleeve_ledger_mark_to_market"`
    - gap records when replay fails closed
  - when no blueprint / no decomposition exists, legacy single-sleeve
    behavior still works
  - a restart-safe close run can reconstruct results from persisted
    session-open state and persisted execution artifacts

- [ ] **Step 2: Implement**
  - keep `SleeveAttributionRecorder` as the close-path orchestrator,
    but delegate math/bootstrap/replay to `sleeve_ledger.py`
  - load opening state from:
    1. existing ledger snapshots if they exist
    2. otherwise bootstrap from current activation + session-open state
  - write ledger, reserve, attribution, and gap artifacts to
    `runtime_store`

- [ ] **Step 3: Verify**
  - `uv run pytest tests/integration/test_stage2_sleeve_position_ledger_close.py tests/unit/test_sleeve_ledger_bootstrap.py tests/unit/test_sleeve_ledger_replay.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(drift): integrate sleeve ledger into close-path attribution"`

---

## Task 9 — Reserve-domain runtime intent generation

**Files:**
- modify `src/tradingx/runtime_portfolio.py`
- possibly extend `src/tradingx/service.py` only where ordering needs a
  tighter assertion
- create `tests/unit/test_residual_reserve_trade_intents.py`
- create `tests/integration/test_stage2_residual_reserve_liquidation.py`

- [ ] **Step 1: Write failing tests**
  - if residual inventory exists for symbol `z`, planner emits a
    reserve-domain sell intent before any sleeve-domain intent for `z`
  - reserve-domain intent uses:
    - `candidate_id="residual-reserve-bootstrap"`
    - `sleeve_attributions=(( "__residual_reserve__", Decimal("1") ),)`
  - sleeve-domain intents for `z` are suppressed while reserve quantity
    remains non-zero
  - reserve-domain candidate id survives decision-snapshot and
    execution-record persistence without registry lookup
  - once reserve quantity reaches zero, normal sleeve-domain planning
    for `z` resumes

- [ ] **Step 2: Implement**
  - add `latest_residual_reserve_snapshot()` consumption to the
    blueprint runtime path
  - synthesize reserve-liquidation `RuntimePortfolioTrade`s and
    `TradeIntent`s in deterministic symbol order
  - keep existing sleeve-domain attribution logic unchanged for normal
    symbols

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_residual_reserve_trade_intents.py tests/integration/test_stage2_residual_reserve_liquidation.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(runtime): emit reserve-domain liquidation intents"`

---

## Task 10 — Gap-aware drift and live-Sharpe consumers

**Files:**
- modify `src/tradingx/drift/gateway.py`
- modify `src/tradingx/drift/live_returns_source.py`
- modify `src/tradingx/drift/pnl_divergence.py`
- create `tests/unit/test_drift_gap_awareness.py`

- [ ] **Step 1: Write failing tests**
  - if any `SleeveAttributionGapRecord` exists in the live window,
    `DriftAlarmGateway._pnl_verdicts()` produces `pending`
  - `StoreBackedAttributionRecordsReader` windows attribution records
    by `trading_day` and exposes gap awareness for the same window
  - `SleeveDailyReturnsReader.live_daily_returns(...)` returns `()`
    when a gap exists inside the requested window
  - no-gap windows continue to produce normal ordered return tuples

- [ ] **Step 2: Implement**
  - keep the public artifact contract stable:
    `records_for_sleeve(...)` still returns
    `SleeveDailyAttributionRecord`s
  - add explicit gap-window helper(s) on the reader side
  - gate `DriftAlarmGateway._pnl_verdicts()` on those gap helpers
  - gate `SleeveDailyReturnsReader` the same way
  - keep `compute_live_vs_backtest_pnl_divergence(...)` math
    compatible with contiguous no-gap windows

- [ ] **Step 3: Verify**
  - `uv run pytest tests/unit/test_drift_gap_awareness.py tests/unit/test_drift_gateway.py -q`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(drift): harden gap-aware live return consumers"`

---

## Task 11 — End-to-end sweep and documentation close-out

**Files:**
- modify `docs/superpowers/specs/2026-04-22-tranche-2-1-stage-2-sleeve-position-ledger-attribution-design.md`
- modify `docs/INDEX.md`
- expand integration tests as needed

- [ ] **Step 1: Final end-to-end test**
  - one integration drill covering:
    - preopen session-open persistence
    - bootstrap on existing inventory
    - runtime close replay into ledger + reserve
    - reserve-domain liquidation on subsequent heartbeat(s)
    - gap-aware drift pending behavior when forced mismatch is injected

- [ ] **Step 2: Documentation close-out**
  - flip DESIGN-0019 from draft to `1.0.0 active`
  - update `docs/INDEX.md` row for DESIGN-0019 accordingly
  - do **not** touch Task 12 activation wording yet

- [ ] **Step 3: Full verification**
  - `uv run ruff check src/tradingx tests`
  - `uv run mypy src/tradingx`
  - `uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py`
  - `python3 scripts/check_index.py`
  - `./scripts/validate`

- [ ] **Step 4: Commit**
  - `git commit -m "feat(drift): land Stage 1 sleeve ledger attribution"`

---

## Task 12 [Deferred] — Activate `pnl::<sleeve_id>`

This remains a separate follow-up commit after Stage 1 has shipped
and the new ledger has accrued enough evidence.

**Preconditions before execution:**

1. both active sleeves have enough ledger-based records to satisfy the
   live rolling window used by the monitor;
2. unresolved residual reserve **positions** are zero across the
   activation window;
3. residual reserve **cash** is below the non-blocking threshold from
   DESIGN-0019:
   - recommended default:
     `max(5% of broker equity, notional of one minimum-sized sleeve trade)`;
4. no `SleeveAttributionGapRecord` exists inside the monitor window for
   either active sleeve; and
5. recalibration, if needed, has completed before the threshold flip.

**Task 12 implementation scope:**

- wire Task-10 gap-aware readers into the active monitor path;
- confirm the new ledger output is stable in paper evidence;
- flip `pnl::<sleeve_id>` from pending to active;
- update any user-facing gate narrative that still says the monitor is
  pending; and
- land as a single isolated commit so rollback can target activation
  without removing the ledger foundation.

---

## Tightness checklist before implementation starts

The implementer should not begin coding until the following are all
true in this plan:

- there is exactly one owner for each contentious seam:
  - activation snapshot backfill -> `LocalActivationGateway`
  - decomposition continuity writer -> `PaperTradingService`
  - reserve-domain liquidator -> `RuntimePortfolioPlanner`
  - close-path accounting orchestrator -> `SleeveAttributionRecorder`
  - gap-aware P&L/live-Sharpe behavior -> drift reader layer
- every cross-root store interaction names the concrete root
  (`runtime_store`, `paper_store`, `operator_store`, `validation_store`)
- every deferred item is pushed to Task 12 rather than left vague in
  Stage 1
- every risky seam has at least one direct unit or integration test
  named in the plan
- no task assumes a store root, candidate id, or fallback source that
  is not spelled out above
