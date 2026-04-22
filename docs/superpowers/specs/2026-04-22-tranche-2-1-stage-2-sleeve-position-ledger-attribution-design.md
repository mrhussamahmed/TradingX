---
id: DESIGN-0019
title: Tranche 2.1 Stage 2 sleeve position ledger attribution
version: 1.0.0
status: active
created: 2026-04-22
last_amended: 2026-04-22
supersedes: null
superseded_by: null
author_session: gpt-5-codex-2026-04-22
---

# DESIGN-0019: Tranche 2.1 Stage 2 sleeve position ledger attribution

## Status

Active on 2026-04-22. Follow-on design after
[DESIGN-0017](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md)
Stage 1 merged at `699fce3` and after the tranche 2.2 Stage 1
merge at `0a687ba`. The Stage 1 ledger foundation described here is
now the merged implementation target for the tranche-2.1 Stage 2
follow-up branch.

## Purpose

[DESIGN-0017 W10](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md#W10--stage-2-drift-pl-divergence-activation-follow-up-commit)
assumed Task 16 would be a small follow-up commit that simply
flips `pnl::<sleeve_id>` from pending to active once enough
multi-sleeve attribution data exists. Review of the merged
tranche 2.1 code showed the remaining blocker is not just time;
it is the attribution formula itself.

The current multi-sleeve close path in
[/src/tradingx/drift/attribution.py:114](/src/tradingx/drift/attribution.py:114)
derives each sleeve's `starting_equity`, `ending_equity`, and
`daily_return` from the same portfolio-level daily return. Every
live sleeve therefore receives the same `daily_return` on a given
day:

```python
portfolio_daily_return = (
    (close_portfolio_state.equity - open_portfolio_state.equity)
    / open_portfolio_state.equity
)
...
ending_equity = starting_equity * (Decimal("1") + portfolio_daily_return)
daily_return = portfolio_daily_return
```

That implementation was acceptable as a Stage 1 placeholder
because it preserved backward compatibility and got the
multi-sleeve runtime shipped safely. It is not acceptable for
Stage 2 activation because the drift monitor in
[/src/tradingx/drift/gateway.py:301](/src/tradingx/drift/gateway.py:301)
needs sleeve-specific return series, not one portfolio return
copied to every sleeve.

This design inserts the missing prerequisite: a sleeve-level
position ledger and bootstrap process that can:

1. assign existing live positions to sleeves without discarding
   them;
2. track future sleeve holdings and cash from attributed fills;
3. compute sleeve-specific daily returns from sleeve-owned
   positions and cash; and
4. feed those real sleeve return series into the already-shipped
   1.5 drift-monitoring path so Task 16 can activate safely in a
   later follow-up.

## Scope

This design covers the missing accounting layer between
multi-sleeve execution attribution and Stage 2 drift activation.

In scope:

1. **Automatic bootstrap for already-open positions.** Existing
   broker positions are assigned to sleeves automatically using
   recent attributed execution history first, with deterministic
   fallback only when history is absent.
2. **Persistent shared funding reserve.** Existing broker cash and
   any unresolved inventory are preserved in an explicit residual
   reserve that remains the durable holder of free broker cash,
   instead of being synthetically assigned to sleeves on day 1.
3. **Sleeve position ledger state.** Each sleeve gets its own
   persisted mini-account: cash balance, symbol quantities,
   weighted-average cost basis, and realized/unrealized P&L.
4. **Residual reserve state.** The reserve tracks inherited cash,
   unresolved positions, and the shared broker-cash funding layer
   used by later attributed buys and sells.
5. **Deterministic end-of-day ledger update.** The ledger is
   updated from persisted execution artifacts at session close,
   not by adding new live runtime state mutations intraday.
6. **Sleeve-specific daily return generation.** Daily return is
   computed from sleeve-owned cash plus sleeve-owned marked
   positions, not from the portfolio return proxy.
7. **Audit trail on bootstrap quality.** The bootstrap result
   records whether each symbol allocation came from strong
   evidence, rounding-only adjustment, blueprint fallback, or
   unresolved residual handling.
8. **Explicit gap handling for drift.** Any sleeve/day that cannot
   be attributed safely emits a gap artifact instead of silently
   disappearing from the live series.
9. **Compatibility with the existing drift stack.** The 1.5/2.1
   readers still consume `SleeveDailyAttributionRecord`, with
   small prerequisite hardening so gap days yield `pending`
   instead of a false verdict. Task 16 remains a separate
   activation change after this prerequisite lands and is
   observed.

Out of scope:

1. Task 16 itself — no `pnl::<sleeve_id>` activation in this
   design.
2. A manual operator mapping workflow for initial positions.
3. Tax-lot accounting, FIFO/LIFO bookkeeping, or realized-P&L
   reporting for compliance use.
4. Intraday sleeve NAV snapshots.
5. Rewriting broker reconciliation, execution persistence, or the
   portfolio planner.
6. A general-purpose treasury or cash-optimization subsystem
   beyond the deterministic shared-funding reserve introduced
   here.

## Relationship to prior tranche decisions

This design preserves the already-resolved tranche decisions and
narrows only the accounting prerequisite that was left implicit in
DESIGN-0017:

1. **DESIGN-0017 Stage 1 stands as shipped.** Multi-sleeve wiring,
   `sleeve_attributions`, decomposition persistence, fallback
   narrowing, and dashboard work are unchanged.
2. **Task 16 remains deferred.** This design does not reopen the
   two-stage rollout decision from BRIEF-0003 D5; it supplies the
   missing prerequisite so the later activation commit has real
   sleeve returns to work with.
3. **The drift monitor contract stays stable at the artifact
   boundary.**
   `StoreBackedAttributionRecordsReader.records_for_sleeve(...)`
   in [/src/tradingx/drift/gateway.py:277](/src/tradingx/drift/gateway.py:277)
   continues to read `SleeveDailyAttributionRecord.daily_return`
   values; the meaning of `daily_return` becomes correct rather
   than approximate. This design does allow a small prerequisite
   hardening around gap awareness before Task 16, but it does not
   replace the public live-return artifact type.

## Principles

### P1 — Evidence-first bootstrap, no silent proportional scaling

When the account already has open positions, the bootstrap MUST
assign those positions using actual sleeve-attributed trade
history first. The blueprint is a deterministic fallback, not the
primary source of truth. If historical evidence exists for a
symbol, the design MUST use it. Partial history that does not
reconcile may not be scaled up silently; it must either reconcile
within a tiny rounding tolerance or stay outside sleeve ownership
as unresolved residual inventory.

### P2 — Ownership survives activation changes until a trade changes it

Once the ledger bootstrap is established, an activation change
alone MUST NOT reassign already-open inventory. Existing sleeve
ownership continues across blueprint activation changes until new
attributed trades alter that ownership economically.

### P3 — Each sleeve is a mini-portfolio, plus one bounded residual reserve

Each sleeve ledger MUST track both positions and cash. A sleeve's
daily return is the return of that sleeve's own mini-portfolio,
not a share of the aggregate portfolio return.

Free broker cash and unresolved inherited inventory live in one
explicit residual reserve outside sleeves. That reserve persists
after bootstrap as the shared broker-cash funding layer for replay.
It is not a permanent treasury optimization subsystem; it is the
minimal accounting construct needed so a valid broker execution does
not become unreplayable just because free cash sat outside the
buying sleeve.

### P4 — Daily return comes from owned holdings, not target weights

`daily_return` MUST be derived from:

- sleeve opening cash;
- sleeve opening symbol quantities valued from the session-open
  portfolio state;
- attributed fills applied during the session; and
- sleeve closing cash plus sleeve closing symbol quantities valued
  from the session-close portfolio state.

Target weights and decomposition records are supporting evidence
for bootstrap fallback and auditability. They are not the P&L
source of truth.

### P5 — Accounting anomalies fail closed, with explicit gap artifacts

If the ledger encounters an attributed fill it cannot apply
safely — missing sleeve attribution, negative post-fill quantity,
or irreconcilable symbol ownership mismatch — the design MUST fail
closed for the affected sleeve/symbol, emit explicit operator
evidence, and write a day-keyed gap artifact. Silent
approximation and silent omission are both forbidden.

### P6 — Determinism requires durable inputs and explicit ordering

Given the same:

- initial bootstrap activation context;
- broker opening positions and cash;
- persisted execution history; and
- session open/close portfolio states,

the bootstrap and daily attribution outputs MUST be identical
across reruns. No UUID fallback, wall-clock ordering dependence,
or hidden randomization is allowed. Replay order MUST be explicit:
`filled_at_utc`, then `execution_id` as the stable tie-breaker.

### P7 — Task 16 stays a separate activation step

This design lands the accounting foundation only. The commit that
activates `pnl::<sleeve_id>` remains separate so rollback can still
target the monitor activation independently from the new ledger.

## Architecture

At a high level, the feature is an end-of-day sleeve accounting
pipeline:

```text
persisted session_open PortfolioState record
        +
latest ledger snapshot(s)
        +
latest residual reserve snapshot
        +
latest active blueprint activation
        +
execution artifacts from paper_loop store
        |
        v
bootstrap once or load opening ledger state
        |
        v
replay today's attributed executions into each sleeve ledger
        +
replay same executions into residual reserve transfers / reductions
        |
        v
mark each sleeve's remaining positions to the session_close PortfolioState
        |
        +--> write SleevePositionLedgerSnapshot(s)
        |
        +--> write ResidualReserveSnapshot
        |
        +--> write SleeveDailyAttributionRecord(s)
        |
        +--> write SleeveAttributionGapRecord(s) if needed
        |
        +--> later Task 16 reads these returns for pnl::<sleeve_id>
```

The important design choice is where the ledger lives:

- **Not in the live execution loop.** We do not add new mutable
  state to broker-facing trading code.
- **At the session-close attribution seam.** The end-of-day
  recorder is the right place to derive accounting, but the
  current seam does **not** yet have all durable inputs. This
  design therefore adds:
  - a persisted session-open portfolio-state record at preopen;
  - a typed execution-lifecycle reader from the `paper_loop`
    store; and
  - stable replay ordering by `filled_at_utc`, then
    `execution_id`.

That makes the ledger an accounting layer derived from persisted
facts, which is safer to reason about and easier to rerun for
debugging.

## Data model

### W1 — Bootstrap and ledger records

New persisted records:

```python
@dataclass(frozen=True)
class BootstrapPositionAllocation:
    sleeve_id: str
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    allocation_source: str    # history_exact | history_rounding_adjusted | blueprint_fallback
    confidence: str           # high | medium | low
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ResidualPositionAllocation:
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    reason: str               # unresolved_history | no_active_owner
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SleeveBootstrapAllocationRecord:
    bootstrap_id: str
    ledger_genesis_id: str
    bootstrapped_from_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    position_allocations: tuple[BootstrapPositionAllocation, ...]
    residual_cash_balance: Decimal
    residual_positions: tuple[ResidualPositionAllocation, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SleeveLedgerPosition:
    sleeve_id: str
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    realized_pnl_cumulative: Decimal


@dataclass(frozen=True)
class SleevePositionLedgerSnapshot:
    snapshot_id: str
    ledger_genesis_id: str
    active_blueprint_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    sleeve_id: str
    cash_balance: Decimal
    positions: tuple[SleeveLedgerPosition, ...]
    bootstrap_id: str
    # Analytical capital account for performance measurement.
    # Durable deployable broker cash remains in the residual reserve.


@dataclass(frozen=True)
class ResidualReserveSnapshot:
    snapshot_id: str
    ledger_genesis_id: str
    active_blueprint_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    cash_balance: Decimal
    positions: tuple[ResidualPositionAllocation, ...]
    bootstrap_id: str


@dataclass(frozen=True)
class SessionOpenPortfolioStateRecord:
    record_id: str
    trading_day: str
    recorded_at_utc: datetime
    portfolio_state: PortfolioState


@dataclass(frozen=True)
class SleeveAttributionGapRecord:
    gap_id: str
    sleeve_id: str
    trading_day: str
    recorded_at_utc: datetime
    severity: str
    reason: str
    evidence_refs: tuple[str, ...]
```

Existing record extended:

```python
@dataclass(frozen=True)
class SleeveDailyAttributionRecord:
    ...
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    cash_balance: Decimal | None = None
    calculation_mode: str | None = None      # active_sleeve_equity | sleeve_ledger_mark_to_market
    bootstrap_confidence: str | None = None  # high | medium | low | mixed
    ledger_genesis_id: str | None = None
```

Rationale:

1. `SleeveBootstrapAllocationRecord` is the one-time provenance
   record for how the system inherited existing positions and
   created the initial residual reserve.
2. `SleevePositionLedgerSnapshot` is the persisted state that lets
   the next session start from the prior close instead of replaying
   all history from zero every day.
3. `ResidualReserveSnapshot` keeps inherited broker truth that
   cannot safely be assigned to sleeves on day 1.
4. `SessionOpenPortfolioStateRecord` closes the current durability
   gap in the automation seam.
5. `SleeveAttributionGapRecord` prevents a missing day from being
   silently interpreted as a valid day-count shift.
6. `SleeveDailyAttributionRecord` remains the public drift-facing
   record so existing readers and dashboards do not need a new
   primary input type.

Persistence categories:

- `sleeve_bootstrap/`
- `sleeve_position_ledger/`
- existing `sleeve_daily_attribution/`
- existing `sleeve_decomposition/` when read as runtime state for
  sleeve/current-weight continuity

Canonical root for these DESIGN-0019 runtime-state categories:

- the top-level `runtime_store = FilesystemArtifactStore(artifact_root)`,
  not `paper_loop/`;
- this keeps bootstrap, reserve, decomposition, attribution, and drift
  readers on one shared runtime-root store, matching the current
  `SleeveAttributionRecorder`/drift-reader side in
  [/src/tradingx/automation.py:916](/src/tradingx/automation.py:916); and
- the existing decomposition writer in
  `PaperTradingService._write_sleeve_decomposition_record_if_available()`
  at [/src/tradingx/service.py:555](/src/tradingx/service.py:555)
  must be rehomed to that same runtime-root store instead of writing
  `SleeveDecompositionRecord` through `self._artifacts` when
  `self._artifacts` is still bound to `paper_store`.

Suggested filenames:

- `sleeve_bootstrap/{ledger_genesis_id}.json`
- `sleeve_position_ledger/{trading_day}__{snapshot_id}__{sleeve_id}.json`
- `residual_reserve/{trading_day}__{snapshot_id}.json`
- `session_open_portfolio_state/{trading_day}.json`
- `sleeve_attribution_gaps/{sleeve_id}__{trading_day}.json`
- existing attribution filename stays `{sleeve_id}__{trading_day}.json`

### W2 — Query helpers

`FilesystemArtifactStore` gains:

```python
def write_sleeve_bootstrap_allocation_record(
    self,
    record: SleeveBootstrapAllocationRecord,
) -> Path: ...

def write_sleeve_position_ledger_snapshot(
    self,
    record: SleevePositionLedgerSnapshot,
) -> Path: ...

def write_residual_reserve_snapshot(
    self,
    record: ResidualReserveSnapshot,
) -> Path: ...

def write_session_open_portfolio_state_record(
    self,
    record: SessionOpenPortfolioStateRecord,
) -> Path: ...

def write_sleeve_attribution_gap_record(
    self,
    record: SleeveAttributionGapRecord,
) -> Path: ...

def latest_sleeve_position_ledger_snapshot(
    self,
    *,
    sleeve_id: str,
) -> SleevePositionLedgerSnapshot | None: ...

def latest_residual_reserve_snapshot(self) -> ResidualReserveSnapshot | None: ...

def latest_sleeve_bootstrap_allocation(
    self,
) -> SleeveBootstrapAllocationRecord | None: ...

def read_session_open_portfolio_state_record(
    self,
    *,
    trading_day: str,
) -> SessionOpenPortfolioStateRecord | None: ...

def load_approved_weight_snapshot_by_snapshot_id(
    self,
    *,
    snapshot_id: str,
) -> ApprovedWeightSnapshot: ...

def list_execution_lifecycle_records(
    self,
    *,
    trading_day: str,
) -> tuple[ExecutionLifecycleRecord, ...]: ...

def list_sleeve_attribution_gap_records(
    self,
    *,
    sleeve_id: str,
) -> tuple[SleeveAttributionGapRecord, ...]: ...
```

The new execution query is required because the current store only
writes execution lifecycle records at
[/src/tradingx/persistence.py:324](/src/tradingx/persistence.py:324)
but does not expose a typed list/read helper for day-end replay.
The session-open record is required because the current automation
runner keeps the open `PortfolioState` only in memory at
[/src/tradingx/automation.py:301](/src/tradingx/automation.py:301).

Additional activation-time durability requirement:

- when `load_or_activate_blueprint(...)` captures
  `captured_snapshot_id` from an `ApprovedWeightSnapshot`, the same
  activation path MUST also persist that exact snapshot payload into
  `model_weight_snapshots/{snapshot_id}.json` if it is not already
  present;
- the concrete owner of that persistence/backfill step is
  `LocalActivationGateway`, because it is the current seam that owns
  both fresh blueprint activation creation and unchanged-activation
  reuse in [/src/tradingx/activation.py:117](/src/tradingx/activation.py:117);
- the canonical store root for these persisted snapshot payloads is
  the top-level `runtime_store = FilesystemArtifactStore(artifact_root)`
  used by `SleeveAttributionRecorder` and drift readers in
  [/src/tradingx/automation.py:856](/src/tradingx/automation.py:856)
  and [/src/tradingx/automation.py:916](/src/tradingx/automation.py:916),
  not the narrower `operator_store`;
- `LocalActivationGateway` therefore gains a second artifact-store
  dependency dedicated to this durability path, for example
  `runtime_snapshot_store: FilesystemArtifactStore`;
- in the market-day automation wiring, that dependency MUST be bound
  explicitly to the existing top-level `runtime_store`, while the
  gateway's existing `store=` dependency continues to point at
  `operator_store` for activation records;
- callers that do not have distinct roots may pass the same
  `FilesystemArtifactStore` object for both dependencies, but the
  interface must make the dual-root ownership explicit;
- if blueprint activation still writes other activation artifacts via
  `operator_store`, the snapshot payloads must be mirrored into
  `runtime_store/model_weight_snapshots/` as part of the same
  activation transaction;
- if `load_or_activate_blueprint(...)` is about to return an
  unchanged active activation from the early idempotent-reuse path,
  it MUST still run an `ensure_activation_snapshot_payloads(...)`
  backfill step before returning:
  - if a captured snapshot payload is already present in
    `runtime_store/model_weight_snapshots/`, reuse it;
  - else if the payload is present in another known artifact root,
    mirror it into `runtime_store`;
  - else if the current approved snapshot loaded by `strategy_id`
    has the same `snapshot_id` as the captured one, persist that
    payload into `runtime_store`;
  - else fail closed with an activation/bootstrap prerequisite error
    rather than silently losing deterministic fallback;
- bootstrap fallback MUST resolve captured snapshots from that
  `runtime_store` payload store by `snapshot_id`, not by reloading current
  approved YAML through `strategy_id`.

Without this, `captured_snapshot_id` is only an identifier, not a
durable reproducibility anchor.

## Bootstrap design

### W3 — Automatic bootstrap for existing positions

Bootstrap runs only when all of the following are true:

1. a blueprint activation is active;
2. no prior `ledger_genesis_id` exists; and
3. the session-open portfolio state contains positions and/or cash.

The algorithm is symbol-by-symbol.

#### Step 1: Gather broker truth

From the session-open `PortfolioState`, read:

- current symbols held;
- current broker quantities;
- current broker `average_entry_price`;
- current broker market value; and
- total broker cash.

#### Step 2: Gather sleeve evidence

For each symbol, aggregate historical sleeve ownership from
persisted `ExecutionLifecycleRecord.sleeve_attributions` for that
symbol:

- buy fills add quantity to the attributed sleeve;
- sell/reduce fills subtract quantity from the attributed sleeve.

This produces a net attributed open quantity per sleeve.

#### Step 3: Choose allocation source

For each symbol:

1. **`history_exact`**
   - if the net attributed quantity across sleeves matches the
     current broker quantity within tolerance, assign those exact
     quantities;
   - confidence = `high`.
2. **`history_rounding_adjusted`**
   - if attributed history differs from broker quantity only by a
     de minimis rounding tolerance, assign the broker quantity with
     the smallest deterministic correction needed to match broker
     truth;
   - confidence = `medium`.
3. **`blueprint_fallback`**
   - if there is no usable attributed history at all, assign by the
     active blueprint activation's captured snapshots, not by
     current approved YAML:
     - resolve the weight snapshots from
       `BlueprintActivationRecord.sleeve_activation_bindings[*].captured_snapshot_id`;
     - those snapshot payloads must have been persisted at
       activation time into `model_weight_snapshots/`;
     - if only one sleeve owns that symbol in those captured
       snapshots, give it 100%;
     - if multiple sleeves own it, split by their relative target
       weights for that symbol;
   - confidence = `low`.
4. **`residual_unowned`**
   - if history exists but does not reconcile beyond rounding
     tolerance, or if no currently-active sleeve owns the symbol at
     all, do not assign the position to a sleeve;
   - keep it in the residual reserve instead;
   - confidence = `none`.

Average cost rule:

- if history reconstruction yields a usable average cost, keep it;
- otherwise use the broker `average_entry_price` for that symbol
  and apply it to each split quantity.

#### Step 4: Initialize the residual reserve

All existing broker cash starts in the residual reserve, not inside
any sleeve. This preserves broker truth without inventing sleeve
cash ownership on day 1, and it also establishes the reserve as the
durable shared-cash source for future replay funding.

If unresolved inherited positions remain after Step 3, those
positions also live in the residual reserve until future economic
events close them or create a safe ownership transition.

#### Step 5: Persist bootstrap result

Write one `SleeveBootstrapAllocationRecord` capturing:

- each symbol's sleeve quantities;
- each symbol's source and confidence;
- the residual cash balance;
- any residual unresolved positions; and
- evidence references to execution records when history was used.

### W4 — Bootstrap determinism and activation boundary

Bootstrap creates a one-time `ledger_genesis_id`, not a
re-bootstrap-per-activation rule.
That means:

1. if the same bootstrap inputs rerun before the first ledger is
   persisted, the same bootstrap result is reused;
2. once the ledger exists, later blueprint activation changes do
   not reassign already-open inventory; and
3. future attributed trades under the new activation are what
   change sleeve ownership economically.

Ledger snapshots may still record the currently-active
`blueprint_activation_id` for audit, but that field is descriptive,
not identity-defining.

## Ongoing ledger design

### W5 — Apply attributed fills into the sleeve ledger

Once bootstrap or the previous close snapshot establishes opening
state, the recorder replays the current trading day's execution
lifecycle records into that state in strict order:

1. ascending `filled_at_utc`;
2. `execution_id` tie-breaker.

Cost basis method: **weighted average cost**.

Reserved owner-id contract:

- the dataclass field shapes introduced in DESIGN-0017 remain the
  same (`sleeve_attributions`, `entry_sleeve_attributions`,
  `exit_sleeve_attributions`);
- for DESIGN-0019, the allowed owner-id set widens to:
  - known `sleeve_id`s, and
  - `__residual_reserve__` for reserve-domain executions;
- reserve-domain executions therefore remain representable in the
  existing tuple fields without introducing a second execution
  artifact type.

Reserve-domain production path:

- `RuntimePortfolioPlanner` already owns the runtime trade-intent seam
  through `plan_for_service(...)`;
- the current code only gives that planner one `artifact_store`
  dependency in
  [/src/tradingx/runtime_portfolio.py:104](/src/tradingx/runtime_portfolio.py:104);
- DESIGN-0019 makes the runtime-root dependency explicit by adding a
  dedicated `runtime_state_store: FilesystemArtifactStore` to
  `RuntimePortfolioPlanner` for:
  - `latest_sleeve_decomposition_record()`; and
  - `latest_residual_reserve_snapshot()`;
- in `build_default_paper_service()`, that dependency MUST be bound to
  the same top-level `runtime_store` used by
  `SleeveAttributionRecorder`, not to `paper_store`;
- `PaperTradingService` likewise needs a parallel
  `runtime_state_store: FilesystemArtifactStore` seam so
  `_write_sleeve_decomposition_record_if_available()` writes
  `SleeveDecompositionRecord` into `runtime_store` rather than the
  paper-loop artifact root;
- `paper_store` remains the home for paper-loop cycle artifacts such as
  `runtime_portfolio_plan` snapshots, but not for DESIGN-0019 ledger or
  reserve state;
- DESIGN-0019 adds one narrow reserve-liquidation pre-pass inside the
  blueprint runtime path:
  - read `latest_residual_reserve_snapshot()` from
    `runtime_state_store`;
  - if residual inventory exists for symbol `z`, synthesize a
    reserve-liquidation `RuntimePortfolioTrade` for `z` before any
    sleeve-domain trade for that symbol;
  - build the corresponding `TradeIntent` with
    `candidate_id="residual-reserve-bootstrap"` and
    `sleeve_attributions=((\"__residual_reserve__\", Decimal(\"1\")),)`;
  - prepend those reserve-domain intents ahead of normal sleeve-domain
    intents in deterministic symbol order; and
  - suppress sleeve-domain trades for `z` while residual-reserve
    quantity for `z` remains non-zero;
- `controller.py` then remains shape-compatible because it already
  copies `trade_intent.sleeve_attributions` into
  `ExecutionLifecycleRecord` without needing a second execution schema.

For a buy:

1. attributed quantity per sleeve =
   `filled_qty * attribution_fraction`;
2. attributed buy notional is funded from the residual reserve as
   an explicit capital contribution into the sleeve at the fill
   timestamp;
3. the sleeve's analytical cash balance is updated for performance
   accounting, but insufficient sleeve cash never blocks replay of a
   broker-valid buy;
4. sleeve quantity increases; and
5. average cost updates by weighted average.

For a sell/reduce:

1. if the execution is sleeve-domain
   (`sleeve_attributions` contains only sleeve ids):
   - attributed quantity per sleeve =
     `filled_qty * attribution_fraction`;
   - sleeve quantity decreases;
   - realized P&L is booked using the sleeve's weighted-average
     cost;
   - attributed sale proceeds are distributed from the sleeve back
     to the residual reserve at the fill timestamp as an explicit
     capital distribution;
2. if the execution is reserve-domain
   (`sleeve_attributions == ((\"__residual_reserve__\", Decimal(\"1\")),)`):
   - residual reserve quantity decreases;
   - residual reserve cash increases by sale proceeds; and
   - no sleeve realized P&L is booked for that execution.

Residual reserve behavior:

- unresolved inherited positions remain in the residual reserve
  until future sells reduce them or future economic events allow a
  safe ownership transition;
- a symbol may be in exactly one ownership domain at a time for
  accounting purposes:
  - sleeve-owned, or
  - residual-reserve-owned,
  but never both;
- if residual unresolved inventory exists for symbol `z`, any
  execution for `z` must be classified consistently to the reserve
  domain until residual reserve inventory for `z` is zero;
- if a sleeve-domain execution arrives for symbol `z` while reserve
  inventory for `z` is still non-zero, replay MUST fail closed with
  a `SleeveAttributionGapRecord`;
- reserve cash is the durable holder of free broker cash across the
  life of the ledger, not just at bootstrap;
- reserve cash decreases only when explicitly transferred into a
  sleeve to fund attributed buys;
- proceeds from reducing residual unresolved inventory stay in the
  residual reserve cash balance when the execution is classified to
  the residual reserve domain;
- attributed sale proceeds also return to the residual reserve;
- reserve cash is not automatically reallocated by blueprint
  percentages; and
- a broker-valid buy is never rejected merely because another sleeve
  previously realized the cash.

Operational consequence:

- residual-reserve-owned symbols are not merely representable on disk;
  the runtime actively emits reserve-domain liquidation intents for
  them until residual quantity reaches zero;
- because those intents use
  `candidate_id="residual-reserve-bootstrap"` and
  `sleeve_attributions=((\"__residual_reserve__\", Decimal(\"1\")),)`,
  reserve inventory unwinds through the same persisted
  `TradeIntent -> ExecutionLifecycleRecord -> ClosedTradeRecord` path as
  normal sleeve trades; and
- because both the planner and recorder now read/write reserve and
  decomposition state from the same `runtime_store` root, the unwind
  path cannot miss residual inventory merely because it was written
  under `paper_loop`; and
- Task 16's "unresolved reserve positions are zero" precondition is
  therefore a reachable runtime state, not a manual cleanup
  requirement.

Why weighted average cost:

- deterministic and simple;
- sufficient for drift attribution;
- avoids introducing full tax-lot semantics into a narrow
  monitoring prerequisite.

### W6 — Fail-closed ledger invariants

The ledger MUST refuse to fabricate ownership when core invariants
break.

Invariants:

1. every replayed execution must have non-empty attribution tuples;
2. every attribution owner id must be either a known `sleeve_id` or
   `__residual_reserve__`;
3. attribution fractions must sum to 1.0 within tolerance;
4. no sleeve position may go negative beyond tolerance;
5. no symbol may be simultaneously sleeve-owned and
   residual-reserve-owned during replay; if that condition occurs,
   the day fails closed for that symbol;
6. per-symbol sleeve quantities plus residual-reserve quantity must
   sum to the broker quantity within tolerance after bootstrap and
   after replay; and
7. sleeve cash plus marked sleeve positions plus residual reserve
   cash plus marked residual positions must sum to broker portfolio
   equity within tolerance at open and close.

Failure behavior:

1. emit an operator-visible alert or evidence record naming the
   sleeve/symbol and invariant that failed;
2. write a `SleeveAttributionGapRecord` for that sleeve/day; and
3. do not silently replace missing facts with guessed ownership.

This is stricter than the current portfolio-return proxy by design.
Once Task 16 is active, wrong sleeve returns are more dangerous than
missing sleeve returns, and missing sleeve returns must be visible
as gaps rather than silently absent days.

## Daily attribution calculation

### W7 — Compute real sleeve daily returns from sleeve-owned holdings

At session close:

1. load opening sleeve ledger state and opening residual reserve;
2. replay the day's executions into each sleeve ledger and reserve;
3. allocate session-open portfolio market values to sleeves by
   opening sleeve quantities;
4. allocate session-close portfolio market values to sleeves by
   closing sleeve quantities, with a zero-quantity branch for fully
   liquidated symbols;
5. compute sleeve opening equity and closing equity;
6. build the sleeve's ordered signed external cash-flow series
   against the residual reserve for the session; and
7. persist `SleeveDailyAttributionRecord`.

Formulas:

```text
opening_equity(s) =
    opening_cash(s)
    + sum over symbols z of opening_market_value(s, z)

closing_equity(s) =
    closing_cash(s)
    + sum over symbols z of closing_market_value(s, z)

daily_return(s) =
    modified_dietz(
        opening_equity(s),
        closing_equity(s),
        ordered_signed_external_cash_flows(s)
    )
```

Where:

```text
opening_market_value(s, z) =
    broker_open_market_value(z)
    * opening_sleeve_quantity(s, z) / broker_open_quantity(z)

closing_market_value(s, z) =
    0, if broker_close_quantity(z) == 0
    else broker_close_market_value(z)
         * closing_sleeve_quantity(s, z) / broker_close_quantity(z)
```

This keeps sleeve valuations anchored to the broker's actual open
and close market values while still using the sleeve ledger as the
ownership source of truth. The Modified Dietz adjustment is needed
because residual-reserve cash can move both into and out of a sleeve
mid-session without inventing day-0 sleeve cash ownership. The
implementation MUST treat these as an ordered tuple of signed cash
flows, not as one netted amount:

- reserve -> sleeve funding for buys = positive external flow into
  the sleeve;
- sleeve -> reserve sale distributions = negative external flow out
  of the sleeve.

Each flow is weighted independently by its `filled_at_utc` position
between the persisted session-open and session-close timestamps.
Sell-then-buy and buy-then-sell days therefore remain distinct; the
implementation may not collapse intraday opposing flows into one net
cash-flow figure before weighting.

The resulting `SleeveDailyAttributionRecord` writes:

- `starting_equity`
- `ending_equity`
- `daily_return`
- `realized_pnl`
- `unrealized_pnl`
- `cash_balance`
- `calculation_mode="sleeve_ledger_mark_to_market"`
- `bootstrap_confidence`

`per_symbol_open_weight` and `per_symbol_close_weight` remain, but
are now derived from sleeve-owned marked values divided by sleeve
opening/closing equity, not from aggregate portfolio fractions.

## Drift and Task 16 boundary

### W8 — Keep the public drift contract stable

The already-shipped drift readers keep their current contract at the
artifact boundary:

- `StoreBackedAttributionRecordsReader.records_for_sleeve(...)`
  still returns `SleeveDailyAttributionRecord`s.
- `DriftAlarmGateway._pnl_verdicts()` still consumes the
  `daily_return` tuple from those records.

What changes is the truthfulness of the numbers:

- today: all sleeves read the same daily return on the same day;
- after this design: each sleeve reads the return of its own
  cash-plus-holdings ledger.

Additional prerequisite hardening before Task 16:

1. `compute_live_vs_backtest_pnl_divergence(...)` stays pending if
   any `SleeveAttributionGapRecord` exists for the sleeve inside the
   live rolling window;
2. `StoreBackedAttributionRecordsReader` windowing must be
   gap-aware by `trading_day`, not just `recorded_at_utc`; and
3. `SleeveDailyReturnsReader.live_daily_returns(...)` and any
   `LIVE_DAILY_RETURNS`-based `SleeveRuntimeController` path must
   treat any gap in the requested window as insufficient history
   rather than a shorter valid series; and
4. gap days are therefore explicit pending/insufficient-history
   states, not silent count-shifts in the live series.

Task 16 remains the later commit that:

1. confirms enough new ledger-based records exist for both sleeves;
2. confirms unresolved residual reserve positions are zero for the
   active sleeves' monitoring window;
3. confirms residual reserve cash is below a concrete non-blocking
   threshold for the same window:
   - recommended default = max(5% of broker equity, the notional of
     one minimum-sized sleeve trade);
4. recalibrates thresholds if needed; and
5. flips `pnl::<sleeve_id>` from pending to active.

## Not touched

The following remain untouched by this design:

- `TradeIntent`, `ExecutionLifecycleRecord`, and
  `ClosedTradeRecord` attribution field shapes as introduced in
  DESIGN-0017 Stage 1. (This design widens the allowed owner-id
  values to include `__residual_reserve__`, but does not add new
  attribution fields.)
- The activation-state semantics from DESIGN-0017. (This design adds a
  snapshot-payload durability/backfill seam to `LocalActivationGateway`,
  but does not change what makes an activation active or superseded.)
- CPCV/PBO infrastructure from DESIGN-0018.
- Gate 2 robustness evidence packaging.
- Runtime blueprint fallback narrowing semantics.
- Strategy evaluation logic and candidate validation.

## Acceptance criteria

1. **Existing positions are preserved.** Turning on the new sleeve
   ledger with an account that already holds positions does not
   discard them or require manual operator mapping.
2. **Bootstrap is one-time.** Activation changes alone do not
   reassign already-open inventory after ledger genesis.
3. **Bootstrap is deterministic.** Re-running bootstrap with the
   same genesis inputs, broker opening state, and execution
   evidence produces identical allocation records.
4. **Cash is preserved, not invented.** Existing broker cash begins
   in the residual reserve and is not synthetically split across
   sleeves on day 1.
5. **Ledger ownership is conserved.** For every symbol, sleeve
   quantities plus residual-reserve quantity sum to the broker
   quantity at open and close within tolerance.
6. **Equity is conserved.** Sum of sleeve equities plus residual
   reserve equals broker portfolio equity within tolerance at open
   and close.
7. **Sleeves can diverge.** Two sleeves holding different symbols or
   trading differently can produce different `daily_return` values
   on the same trading day.
8. **Weak bootstrap is visible.** Every bootstrapped symbol records
   `allocation_source` and `confidence`, and that confidence is
   surfaced into the daily attribution output.
9. **Snapshot-pinned fallback is reproducible.** If blueprint
   fallback is used, rerunning bootstrap after approved YAML edits
   still resolves the same captured snapshot payloads and produces
   the same fallback allocation.
10. **Idempotent reuse still backfills snapshots.** Reusing an
    unchanged active blueprint still ensures any missing captured
    snapshot payloads are mirrored into `runtime_store` before
    bootstrap fallback can run; deterministic fallback never depends
    on forcing a fresh activation.
11. **Reserve inventory has a runtime exit path.** A symbol owned by
    `__residual_reserve__` causes the runtime planner to emit
    deterministic reserve-domain sell intents until residual quantity
    is zero, rather than leaving that inventory operationally
    stranded.
12. **Planner/recorder store roots are unified.** The planner's reserve
    and decomposition reads use the same `runtime_store` root that the
    recorder uses for ledger and attribution artifacts, so reserve
    inventory cannot be hidden by a `paper_loop`/runtime-root mismatch.
13. **Decomposition continuity is written to that same root.** The live
    `SleeveDecompositionRecord` writer is migrated off `paper_store` and
    into `runtime_store`, so sleeve/current-weight continuity cannot
    split across roots even before Task 16.
14. **Anomalies fail closed.** Missing sleeve attribution, negative
    inventory, or irreconcilable symbol ownership emit explicit
    gap artifacts and do not fabricate a valid daily return.
15. **Drift readers remain compatible.** Existing drift readers and
    dashboards can read the new attribution records without
    changing their primary input type, and gap days force
    `pending` rather than a false verdict.
16. **Live Sharpe readers are gap-aware.** Any
    `LIVE_DAILY_RETURNS`-based sleeve Sharpe consumer treats gap
    days as insufficient history rather than a shorter valid
    return series.
17. **Task 16 remains separate.** No monitor activation is coupled
    to the ledger merge; rollback can still target the activation
    step independently.

## Decisions resolved

### D1 — Bootstrap style

**Decision:** automatic bootstrap, evidence-first, with residual
reserve fallback when ownership cannot be assigned safely.

Rejected alternatives:

- manual mapping — safer in theory, but the operator explicitly
  rejected a manual bootstrap workflow for the first version;
- blueprint-only split — too approximate when real attributed
  execution history exists.

### D2 — Existing cash handling

**Decision:** keep broker free cash in an explicit residual reserve
that persists after bootstrap and funds future attributed economic
events.

Rejected alternatives:

- split by blueprint budgets — contradicted DESIGN-0017 narrowed
  blueprint semantics and invented sleeve cash ownership without
  evidence;
- proportional to bootstrapped position size — creates a circular
  dependency between position reconstruction and cash assignment.

### D3 — Cost basis method

**Decision:** weighted average cost.

Rejected alternative:

- FIFO/LIFO — more complex than needed for drift attribution and
  would widen the scope into tax-lot accounting.

### D4 — Activation-boundary rule

**Decision:** bootstrap is one-time ledger genesis; activation
changes do not trigger rebootstrap.

Rejected alternative:

- rebootstrap on every `blueprint_activation_id` change — could
  rewrite live ownership without a trade.

### D5 — Valuation source for daily return

**Decision:** value opening and closing positions using the session
open/close `PortfolioState` market values.

Rejected alternatives:

- close-only mark-to-market with portfolio-return proxy for the open
  side — repeats the current flaw;
- separate quote sourcing in the attribution layer — duplicates
  already persisted broker truth.

### D6 — Failure posture

**Decision:** fail closed on unattributed or irreconcilable fills,
with explicit day-keyed gap artifacts and Task 16 reader hardening.

Rejected alternative:

- make up ownership using latest target weights — unsafe once the
  result feeds the drift monitor.

### D7 — Partial-history handling

**Decision:** no `history_scaled` mode beyond a tiny
rounding-adjustment tolerance; unresolved partial history stays in
the residual reserve.

Rejected alternative:

- proportional scaling of partial history — deterministic but can
  silently assign the wrong sleeve owner.

### D8 — Sequencing

**Decision:** this design lands before Task 16 activation and does
not itself flip `pnl::<sleeve_id>`.

Rejected alternative:

- fold the ledger and the monitor activation into one commit — weak
  rollback story and harder diagnosis if drift thresholds misbehave.

## References

- [DESIGN-0017 Tranche 2.1 multi-sleeve live runtime wiring](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md)
- [BRIEF-0003 Tranche 2 planning brief](/docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md)
- [DESIGN-0016 Tranche 1.5 live drift monitoring](/docs/superpowers/specs/2026-04-21-tranche-1-5-live-drift-monitoring-design.md)
- Current close-path proxy implementation:
  [/src/tradingx/drift/attribution.py:114](/src/tradingx/drift/attribution.py:114)
- Current drift reader contract:
  [/src/tradingx/drift/gateway.py:277](/src/tradingx/drift/gateway.py:277)
- Current persisted sleeve attribution type:
  [/src/tradingx/types.py:579](/src/tradingx/types.py:579)
- Current execution attribution type:
  [/src/tradingx/types.py:436](/src/tradingx/types.py:436)
- Current closed-trade attribution type:
  [/src/tradingx/types.py:456](/src/tradingx/types.py:456)
