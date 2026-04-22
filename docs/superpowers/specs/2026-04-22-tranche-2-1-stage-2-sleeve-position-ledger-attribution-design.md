---
id: DESIGN-0019
title: Tranche 2.1 Stage 2 sleeve position ledger attribution
version: 0.1.0
status: draft
created: 2026-04-22
last_amended: 2026-04-22
supersedes: null
superseded_by: null
author_session: gpt-5-codex-2026-04-22
---

# DESIGN-0019: Tranche 2.1 Stage 2 sleeve position ledger attribution

## Status

Draft on 2026-04-22. Follow-on design after
[DESIGN-0017](/docs/superpowers/specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md)
Stage 1 merged at `699fce3` and after the tranche 2.2 Stage 1
merge at `0a687ba`. Pending user review before implementation
planning.

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
   recent attributed execution history first, with blueprint-based
   fallback only when history is incomplete.
2. **Existing-cash allocation at bootstrap.** Shared account cash
   is split across sleeves using the current blueprint budget
   percentages.
3. **Sleeve position ledger state.** Each sleeve gets its own
   persisted mini-account: cash balance, symbol quantities,
   weighted-average cost basis, and realized/unrealized P&L.
4. **Deterministic end-of-day ledger update.** The ledger is
   updated from persisted execution artifacts at session close,
   not by adding new live runtime state mutations intraday.
5. **Sleeve-specific daily return generation.** Daily return is
   computed from sleeve-owned cash plus sleeve-owned marked
   positions, not from the portfolio return proxy.
6. **Audit trail on bootstrap quality.** The bootstrap result
   records whether each symbol allocation came from strong
   evidence, scaled evidence, or blueprint fallback.
7. **Compatibility with the existing drift stack.** The 1.5/2.1
   readers still consume `SleeveDailyAttributionRecord`; Task 16
   remains a separate activation change after this prerequisite
   lands and is observed.

Out of scope:

1. Task 16 itself — no `pnl::<sleeve_id>` activation in this
   design.
2. A manual operator mapping workflow for initial positions.
3. Tax-lot accounting, FIFO/LIFO bookkeeping, or realized-P&L
   reporting for compliance use.
4. Intraday sleeve NAV snapshots.
5. Rewriting broker reconciliation, execution persistence, or the
   portfolio planner.
6. A shared cash-pool abstraction outside sleeves.

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
3. **The drift monitor contract stays stable.**
   `StoreBackedAttributionRecordsReader.records_for_sleeve(...)`
   in [/src/tradingx/drift/gateway.py:277](/src/tradingx/drift/gateway.py:277)
   continues to read `SleeveDailyAttributionRecord.daily_return`
   values; the meaning of `daily_return` becomes correct rather
   than approximate.

## Principles

### P1 — Evidence-first bootstrap, blueprint fallback only when needed

When the account already has open positions, the bootstrap MUST
assign those positions using actual sleeve-attributed trade
history first. The blueprint is a deterministic fallback, not the
primary source of truth. If historical evidence exists for a
symbol, the design MUST use it.

### P2 — Each sleeve is a mini-portfolio

Each sleeve ledger MUST track both positions and cash. A sleeve's
daily return is the return of that sleeve's own mini-portfolio,
not a share of the aggregate portfolio return.

### P3 — Daily return comes from owned holdings, not target weights

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

### P4 — Accounting anomalies fail closed

If the ledger encounters an attributed fill it cannot apply
safely — missing sleeve attribution, negative post-fill quantity,
or irreconcilable symbol ownership mismatch — the design MUST fail
closed for the affected sleeve/symbol and emit explicit operator
evidence. Silent approximation is forbidden.

### P5 — Determinism beats convenience

Given the same:

- active blueprint activation;
- broker opening positions and cash;
- persisted execution history; and
- session open/close portfolio states,

the bootstrap and daily attribution outputs MUST be identical
across reruns. No UUID fallback, wall-clock ordering dependence,
or hidden randomization is allowed.

### P6 — Task 16 stays a separate activation step

This design lands the accounting foundation only. The commit that
activates `pnl::<sleeve_id>` remains separate so rollback can still
target the monitor activation independently from the new ledger.

## Architecture

At a high level, the feature is an end-of-day sleeve accounting
pipeline:

```text
session_open PortfolioState
        +
latest blueprint activation
        +
existing execution/closed-trade artifacts
        +
latest sleeve ledger snapshot (if any)
        |
        v
bootstrap or load sleeve opening ledger
        |
        v
replay today's attributed executions into each sleeve ledger
        |
        v
mark each sleeve's remaining positions to the session_close PortfolioState
        |
        +--> write SleevePositionLedgerSnapshot(s)
        |
        +--> write SleeveDailyAttributionRecord(s)
        |
        +--> later Task 16 reads these returns for pnl::<sleeve_id>
```

The important design choice is where the ledger lives:

- **Not in the live execution loop.** We do not add new mutable
  state to broker-facing trading code.
- **At the session-close attribution seam.** The end-of-day
  recorder already has:
  - session-open portfolio state,
  - session-close portfolio state,
  - persisted execution artifacts, and
  - persisted sleeve attribution fractions.

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
    allocation_source: str    # history_exact | history_scaled | blueprint_fallback
    confidence: str           # high | medium | low
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SleeveBootstrapAllocationRecord:
    bootstrap_id: str
    blueprint_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    cash_by_sleeve: tuple[tuple[str, Decimal], ...]
    position_allocations: tuple[BootstrapPositionAllocation, ...]
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
    blueprint_activation_id: str
    trading_day: str
    recorded_at_utc: datetime
    sleeve_id: str
    cash_balance: Decimal
    positions: tuple[SleeveLedgerPosition, ...]
    bootstrap_id: str
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
```

Rationale:

1. `SleeveBootstrapAllocationRecord` is the one-time provenance
   record for how the system inherited existing positions and cash.
2. `SleevePositionLedgerSnapshot` is the persisted state that lets
   the next session start from the prior close instead of replaying
   all history from zero every day.
3. `SleeveDailyAttributionRecord` remains the public drift-facing
   record so existing readers and dashboards do not need a new
   primary input type.

Persistence categories:

- `sleeve_bootstrap/`
- `sleeve_position_ledger/`
- existing `sleeve_daily_attribution/`

Suggested filenames:

- `sleeve_bootstrap/{blueprint_activation_id}__{trading_day}.json`
- `sleeve_position_ledger/{trading_day}__{sleeve_id}.json`
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

def latest_sleeve_position_ledger_snapshot(
    self,
    *,
    sleeve_id: str,
    blueprint_activation_id: str,
) -> SleevePositionLedgerSnapshot | None: ...

def latest_sleeve_bootstrap_allocation(
    self,
    *,
    blueprint_activation_id: str,
) -> SleeveBootstrapAllocationRecord | None: ...

def list_execution_lifecycle_records(
    self,
    *,
    trading_day: str,
) -> tuple[ExecutionLifecycleRecord, ...]: ...
```

The new execution query is required because the current store only
writes execution lifecycle records at
[/src/tradingx/persistence.py:324](/src/tradingx/persistence.py:324)
but does not expose a typed list/read helper for day-end replay.

## Bootstrap design

### W3 — Automatic bootstrap for existing positions

Bootstrap runs only when all of the following are true:

1. a blueprint activation is active;
2. no ledger snapshot exists yet for the active
   `blueprint_activation_id`; and
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
2. **`history_scaled`**
   - if attributed history exists but does not fully match the
     broker quantity, preserve the sleeve proportions from history
     and scale them to the broker quantity;
   - confidence = `medium`.
3. **`blueprint_fallback`**
   - if there is no usable attributed history, assign by the
     current blueprint:
     - if only one sleeve owns that symbol in the referenced
       snapshots, give it 100%;
     - if multiple sleeves own it, split by their relative target
       weights for that symbol;
   - confidence = `low`.

Average cost rule:

- if history reconstruction yields a usable average cost, keep it;
- otherwise use the broker `average_entry_price` for that symbol
  and apply it to each split quantity.

#### Step 4: Split existing cash

Account cash at bootstrap is split by current blueprint sleeve
budget percentages. Cash is not reconstructed from history in this
first design because broker cash is shared and historical cash
provenance is not recorded per sleeve today.

Example:

- blueprint budgets: trend 60%, vol 40%
- broker cash: `10,000`
- bootstrap cash:
  - trend `6,000`
  - vol `4,000`

#### Step 5: Persist bootstrap result

Write one `SleeveBootstrapAllocationRecord` capturing:

- each symbol's sleeve quantities;
- each symbol's source and confidence;
- the cash split;
- evidence references to execution records when history was used.

### W4 — Bootstrap determinism and activation boundary

Bootstrap is keyed to `blueprint_activation_id`, not just date.
That means:

1. if the same activation reruns on the same opening positions, the
   same bootstrap result is reused;
2. if a new blueprint activation becomes active, a new bootstrap is
   allowed because sleeve ownership semantics may have changed; and
3. ledger snapshots and bootstrap records remain audit-linked to the
   same activation boundary that DESIGN-0017 already made the source
   of truth for runtime state.

## Ongoing ledger design

### W5 — Apply attributed fills into the sleeve ledger

Once bootstrap or the previous close snapshot establishes opening
state, the recorder replays the current trading day's execution
lifecycle records into that state.

Cost basis method: **weighted average cost**.

For a buy:

1. attributed quantity per sleeve =
   `filled_qty * attribution_fraction`;
2. sleeve cash decreases by attributed notional;
3. sleeve quantity increases;
4. average cost updates by weighted average.

For a sell/reduce:

1. attributed quantity per sleeve =
   `filled_qty * attribution_fraction`;
2. sleeve cash increases by attributed proceeds;
3. sleeve quantity decreases;
4. realized P&L is booked using the sleeve's weighted-average cost.

Why weighted average cost:

- deterministic and simple;
- sufficient for drift attribution;
- avoids introducing full tax-lot semantics into a narrow
  monitoring prerequisite.

### W6 — Fail-closed ledger invariants

The ledger MUST refuse to fabricate ownership when core invariants
break.

Invariants:

1. every replayed execution must have non-empty `sleeve_attributions`;
2. attribution fractions must sum to 1.0 within tolerance;
3. no sleeve position may go negative beyond tolerance;
4. per-symbol sleeve quantities must sum to the broker quantity
   within tolerance after bootstrap and after replay; and
5. sleeve cash plus marked sleeve positions must sum to the broker
   portfolio equity within tolerance at open and close.

Failure behavior:

1. emit an operator-visible alert or evidence record naming the
   sleeve/symbol and invariant that failed;
2. skip writing the affected sleeve's daily attribution record for
   that day; and
3. do not silently replace missing facts with guessed ownership.

This is stricter than the current portfolio-return proxy by design.
Once Task 16 is active, wrong sleeve returns are more dangerous than
missing sleeve returns.

## Daily attribution calculation

### W7 — Compute real sleeve daily returns from sleeve-owned holdings

At session close:

1. load opening sleeve ledger state;
2. replay the day's executions into each sleeve ledger;
3. allocate session-open portfolio market values to sleeves by
   opening sleeve quantities;
4. allocate session-close portfolio market values to sleeves by
   closing sleeve quantities;
5. compute sleeve opening equity and closing equity; and
6. persist `SleeveDailyAttributionRecord`.

Formulas:

```text
opening_equity(s) =
    opening_cash(s)
    + sum over symbols z of opening_market_value(s, z)

closing_equity(s) =
    closing_cash(s)
    + sum over symbols z of closing_market_value(s, z)

daily_return(s) =
    (closing_equity(s) - opening_equity(s)) / opening_equity(s)
```

Where:

```text
opening_market_value(s, z) =
    broker_open_market_value(z)
    * opening_sleeve_quantity(s, z) / broker_open_quantity(z)

closing_market_value(s, z) =
    broker_close_market_value(z)
    * closing_sleeve_quantity(s, z) / broker_close_quantity(z)
```

This keeps sleeve valuations anchored to the broker's actual open
and close market values while still using the sleeve ledger as the
ownership source of truth.

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

The already-shipped drift readers keep their current contract:

- `StoreBackedAttributionRecordsReader.records_for_sleeve(...)`
  still returns `SleeveDailyAttributionRecord`s.
- `DriftAlarmGateway._pnl_verdicts()` still consumes the
  `daily_return` tuple from those records.

What changes is the truthfulness of the numbers:

- today: all sleeves read the same daily return on the same day;
- after this design: each sleeve reads the return of its own
  cash-plus-holdings ledger.

Task 16 remains the later commit that:

1. confirms enough new ledger-based records exist for both sleeves;
2. recalibrates thresholds if needed; and
3. flips `pnl::<sleeve_id>` from pending to active.

## Not touched

The following remain untouched by this design:

- `TradeIntent`, `ExecutionLifecycleRecord`, and
  `ClosedTradeRecord` attribution fields as introduced in
  DESIGN-0017 Stage 1.
- CPCV/PBO infrastructure from DESIGN-0018.
- Gate 2 robustness evidence packaging.
- Runtime blueprint activation and fallback narrowing semantics.
- Strategy evaluation logic and candidate validation.

## Acceptance criteria

1. **Existing positions are preserved.** Turning on the new sleeve
   ledger with an account that already holds positions does not
   discard them or require manual operator mapping.
2. **Bootstrap is deterministic.** Re-running bootstrap with the
   same activation, broker opening state, and execution evidence
   produces identical allocation records.
3. **Cash is fully allocated.** Bootstrap cash across sleeves sums
   exactly to broker cash within Decimal tolerance.
4. **Ledger ownership is conserved.** For every symbol, sleeve
   quantities sum to the broker quantity at open and close within
   tolerance.
5. **Equity is conserved.** Sum of sleeve opening equities equals
   portfolio opening equity within tolerance, and same for close.
6. **Sleeves can diverge.** Two sleeves holding different symbols or
   trading differently can produce different `daily_return` values
   on the same trading day.
7. **Weak bootstrap is visible.** Every bootstrapped symbol records
   `allocation_source` and `confidence`, and that confidence is
   surfaced into the daily attribution output.
8. **Anomalies fail closed.** Missing sleeve attribution, negative
   inventory, or irreconcilable symbol ownership prevent a fake
   daily attribution record from being written for the affected
   sleeve/day.
9. **Drift readers remain compatible.** Existing drift readers and
   dashboards can read the new attribution records without changing
   their primary input type.
10. **Task 16 remains separate.** No monitor activation is coupled to
    the ledger merge; rollback can still target the activation step
    independently.

## Decisions resolved

### D1 — Bootstrap style

**Decision:** automatic bootstrap, evidence-first, blueprint
fallback.

Rejected alternatives:

- manual mapping — safer in theory, but the operator explicitly
  rejected a manual bootstrap workflow for the first version;
- blueprint-only split — too approximate when real attributed
  execution history exists.

### D2 — Existing cash split

**Decision:** split existing broker cash by current blueprint budget
percentages.

Rejected alternatives:

- proportional to bootstrapped position size — creates a circular
  dependency between position reconstruction and cash assignment;
- shared cash pool — adds a second accounting system and weakens the
  "each sleeve is a mini-portfolio" model.

### D3 — Cost basis method

**Decision:** weighted average cost.

Rejected alternative:

- FIFO/LIFO — more complex than needed for drift attribution and
  would widen the scope into tax-lot accounting.

### D4 — Valuation source for daily return

**Decision:** value opening and closing positions using the session
open/close `PortfolioState` market values.

Rejected alternatives:

- close-only mark-to-market with portfolio-return proxy for the open
  side — repeats the current flaw;
- separate quote sourcing in the attribution layer — duplicates
  already persisted broker truth.

### D5 — Failure posture

**Decision:** fail closed on unattributed or irreconcilable fills.

Rejected alternative:

- make up ownership using latest target weights — unsafe once the
  result feeds the drift monitor.

### D6 — Sequencing

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
