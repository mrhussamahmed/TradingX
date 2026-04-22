# Tranche 2.1 Multi-Sleeve Live Runtime Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute [DESIGN-0017](../specs/2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-design.md) — wire tranche 1.4's `PortfolioBlueprint` into live execution so both shipped sleeves (`trend-following-v1`, `vol-target-v1`) run concurrently in paper under a single blueprint, with operator sign-off at the blueprint level, per-sleeve target-weight persistence, sleeve-attribution fractions threaded through intents and executions, artifact regeneration on activation change, single-sleeve fallback/rollback, and a two-sleeve operator dashboard. Stage 2 (Task 16) is a separate follow-up commit that flips the 1.5 drift P&L-divergence monitor from pending to active.

**Architecture:** Extend existing tranche-1 artifacts with minimal additive changes — `SleeveRiskBudget.strategy_id` field, `RuntimePortfolioPlan.per_sleeve_target_weights` field, `sleeve_attributions` fields on `TradeIntent` / `ExecutionLifecycleRecord` / `ClosedTradeRecord`. New `BlueprintActivationRecord` + `SleeveDecompositionRecord` types. New `portfolio/live_construction.py` for per-cycle composition that shares `_combine_sleeve_weights` with 1.4's batch path (§P1). New `portfolio/fallback.py` for the blueprint-narrowing primitive. No changes to the execution engine, cost model, sleeves, throttles, or hard halt.

**Tech Stack:** Python 3.11, `Decimal` at module boundaries, `pandas` where the existing code already uses it, `pytest` for tests, existing `uv run` invocations. No new runtime dependencies.

---

## Scope

Implements DESIGN-0017 §W1–§W10 in this order:

1. **W1** — `SleeveTargetWeights` + `RuntimePortfolioPlan.per_sleeve_target_weights` field.
2. **W2** — `SleeveRiskBudget.strategy_id` + `effective_strategy_id` helper; `BlueprintActivationRecord` + `BlueprintSleeveBinding` types + persistence; `LocalActivationGateway` blueprint methods.
3. **W3** — Extract `_combine_sleeve_weights` from 1.4's `construction.py`; add `build_portfolio_cycle_target_weights` in `live_construction.py` with live-vs-batch parity regression.
4. **W4** — `SleeveDecompositionRecord` persistence + service-loop sidecar write.
5. **W5** — `sleeve_attributions` / `entry_sleeve_attributions` / `exit_sleeve_attributions` fields threaded through intent + execution + closed-trade records; `runtime_portfolio.py` populates fractions from the decomposition.
6. **W6** — Activation-change detection keyed on `activation_id`; force-rebuild paths on the 1.5 reference-snapshot and backtest-reference writers; `recalibrate_drift_reference` pending-file integration.
7. **W7** — `narrow_blueprint_on_sleeve_failure` primitive; service-loop invocation after 3-cycle persistence of a structural termination; `blueprint_narrowed` event emission.
8. **W8** — Operator dashboard two-sleeve rows + `BlueprintActivationRecord` header; legacy single-strategy layout preserved when no blueprint is active.
9. **W9** — Stage 1 closing pass (regression + INDEX bump + BRIEF-0003 / GATES-0001 unchanged).
10. **W10** — Stage 2 follow-up commit flipping drift `pnl::<sleeve_id>` monitor from pending to active once attribution accumulates.

Tranche-1 outcomes (Gate 1 criteria, drift monitors at narrowed 1.5 scope, tranche-1 closure) remain unchanged through Stage 1. Stage 2's commit activates multi-sleeve P&L divergence without touching any other criterion.

## File structure

### New files

- `src/tradingx/portfolio/live_construction.py` — `build_portfolio_cycle_target_weights` + shared `_combine_sleeve_weights` usage.
- `src/tradingx/portfolio/blueprint_activation.py` — `BlueprintActivationRecord` reader/writer helpers (types live on `types.py`; this module holds the activation-gateway path).
- `src/tradingx/portfolio/fallback.py` — `narrow_blueprint_on_sleeve_failure` + `BlueprintExhaustionError`.
- `tests/unit/test_sleeve_target_weights.py`
- `tests/unit/test_blueprint_activation.py`
- `tests/unit/test_portfolio_live_construction.py`
- `tests/unit/test_sleeve_decomposition_record.py`
- `tests/unit/test_sleeve_attributions_threading.py`
- `tests/unit/test_drift_artifact_regeneration.py`
- `tests/unit/test_blueprint_fallback.py`
- `tests/unit/test_dashboard_two_sleeve_view.py` (exact filename matches existing dashboard test convention).
- `tests/integration/test_two_sleeve_paper_cycle.py`
- `tests/integration/test_fallback_drill.py`
- `tests/integration/test_activation_change_regeneration.py`

### Modified files

- `src/tradingx/types.py` — add `SleeveTargetWeights`, `BlueprintActivationRecord`, `BlueprintSleeveBinding`, `SleeveDecompositionRecord`; add `sleeve_attributions`, `entry_sleeve_attributions`, `exit_sleeve_attributions`, `per_sleeve_target_weights` fields; all defaults preserve serialization compatibility.
- `src/tradingx/portfolio/blueprint.py` — additive `strategy_id: str | None = None` on `SleeveRiskBudget`; `effective_strategy_id(budget)` helper.
- `src/tradingx/portfolio/construction.py` — extract `_combine_sleeve_weights` (pure function) so batch + live share one implementation.
- `src/tradingx/runtime_portfolio.py` — `RuntimePortfolioPlanner.plan` emits sleeve decomposition when a blueprint is active; `_trade_intent_for_plan_item` populates `sleeve_attributions` fractions.
- `src/tradingx/activation.py` — `LocalActivationGateway.load_or_activate_blueprint` / `get_active_blueprint_activation` / `supersede_active_blueprint`.
- `src/tradingx/service.py` — per-cycle call to `build_portfolio_cycle_target_weights` when a blueprint is active; persist `SleeveDecompositionRecord` sidecar; detect structural-failure persistence and invoke the fallback primitive.
- `src/tradingx/persistence.py` — writers + readers for `BlueprintActivationRecord` and `SleeveDecompositionRecord`; update intent + execution + closed-trade writers to accept the new `sleeve_attributions` fields.
- `src/tradingx/drift/attribution.py` — when a `SleeveDecompositionRecord` exists for the session, prefer decomposition-based attribution.
- `src/tradingx/drift/reference.py` — add `force_rebuild=True` code path on the build helper.
- `src/tradingx/drift/backtest_reference.py` — add `force_rebuild=True` path on the writer.
- `src/tradingx/drift/gateway.py` — Task 16 (Stage 2) only: fixture + threshold tightening. No Stage 1 code change.
- `src/tradingx/automation.py` — activation-change detection on `build_default_market_day_automation_runner` keyed on `activation_id`; reads the shipped 1.5 operator-control audit marker at `{config.runtime.data_root}/control/drift_reference_recalibration.json` (the same control-store root the shipped `OperatorControlStore` uses at service.py/controller.py/supervisor.py construction sites) to detect operator-triggered recalibrations — no changes to `operator_control.py`, no path mismatch between writers and reader (Codex round-1 + round-2 plan P1 fixes).
- Operator dashboard modules (exact files depend on existing layout; see Task 14 for implementer-convention note).
- Test files listed above + updates to existing `tests/unit/test_runtime_portfolio.py`, `tests/unit/test_service.py`, `tests/unit/test_activation.py`, `tests/unit/test_automation.py`.

### Untouched (intentional)

- `src/tradingx/backtest.py`, `src/tradingx/costs.py`, `src/tradingx/sleeves/*` — engine + cost primitives + sleeve definitions unchanged.
- `src/tradingx/portfolio/hard_halt.py`, `src/tradingx/portfolio/throttle.py`, `src/tradingx/portfolio/sleeve_runtime.py` — halt + throttles + sleeve-runtime controller unchanged.
- `src/tradingx/validation.py` — Gate 1 logic unchanged.
- `src/tradingx/operator_control.py` — unchanged. The 1.5
  audit marker written by `recalibrate_drift_reference` is
  reused as the regeneration-trigger source; no new
  constructor parameter is threaded through the four
  production construction sites (service.py, controller.py,
  supervisor.py, automation.py). Codex round-1 plan P1 fix.
- `config/strategy/weights/<strategy_id>.yaml` — approved-weight YAMLs untouched; operator review flow unchanged.

---

## W1 — `RuntimePortfolioPlan` sleeve decomposition

### Task 1: `SleeveTargetWeights` + `per_sleeve_target_weights` field

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/runtime_portfolio.py`
- Modify: `tests/unit/test_runtime_portfolio.py`
- Create: `tests/unit/test_sleeve_target_weights.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_sleeve_target_weights.py`:

```python
from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from tradingx.types import RuntimePortfolioPlan, SleeveTargetWeights


def test_sleeve_target_weights_is_frozen():
    entry = SleeveTargetWeights(
        sleeve_id="trend-following-v1",
        target_weights_by_symbol=(("SPY", Decimal("0.4")),),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.sleeve_id = "x"  # type: ignore[misc]


def test_runtime_portfolio_plan_per_sleeve_defaults_to_empty_tuple():
    # Existing call sites construct RuntimePortfolioPlan with
    # positional / keyword fields that match the tranche-1.4
    # shape. The new field must default so those constructors
    # do not break. Construct the minimal-required plan from
    # the fixtures your existing test_runtime_portfolio.py uses;
    # the exact signature depends on that module — match it.
    plan = _make_minimal_plan()  # helper defined in the existing test module
    assert plan.per_sleeve_target_weights == ()


def test_runtime_portfolio_plan_accepts_per_sleeve_target_weights():
    plan = _make_minimal_plan_with_decomposition(
        per_sleeve_target_weights=(
            SleeveTargetWeights(
                sleeve_id="trend-following-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.3")),),
            ),
            SleeveTargetWeights(
                sleeve_id="vol-target-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.2")),),
            ),
        ),
    )
    assert len(plan.per_sleeve_target_weights) == 2


def test_decomposition_sums_to_aggregate_within_tolerance(
    sample_two_sleeve_plan,
):
    # Per §P4 aggregate invariant: for each symbol, the sum of
    # per-sleeve contributions equals the aggregate plan's
    # target weight for that symbol (within Decimal("1e-9")).
    plan = sample_two_sleeve_plan
    aggregate_weights_by_symbol = _aggregate_weights_by_symbol(plan)
    decomposition_sums_by_symbol = _decomposition_sums_by_symbol(plan)
    for symbol, aggregate in aggregate_weights_by_symbol.items():
        decomposition_sum = decomposition_sums_by_symbol.get(
            symbol, Decimal("0")
        )
        assert abs(aggregate - decomposition_sum) < Decimal("1e-9")


def test_legacy_single_strategy_plan_has_empty_decomposition(
    sample_legacy_plan,
):
    assert sample_legacy_plan.per_sleeve_target_weights == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sleeve_target_weights.py -v`

Expected: FAIL on `ImportError` for `SleeveTargetWeights` or on the missing field.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`:

```python
@dataclass(frozen=True)
class SleeveTargetWeights:
    sleeve_id: str
    # Portfolio-equity-space weights per symbol this sleeve
    # contributed at the cycle (post-budget-scaling,
    # post-throttle). Ordered by ascending symbol for
    # deterministic serialization.
    target_weights_by_symbol: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True)
class RuntimePortfolioPlan:
    # ...existing fields unchanged...
    per_sleeve_target_weights: tuple[SleeveTargetWeights, ...] = ()
```

Add `SleeveTargetWeights` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sleeve_target_weights.py tests/unit/test_runtime_portfolio.py -v`

Expected: all pass. Existing `test_runtime_portfolio.py` tests continue to pass because the new field has a default.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py tests/unit/test_sleeve_target_weights.py tests/unit/test_runtime_portfolio.py
git commit -m "feat(types): add SleeveTargetWeights + per_sleeve_target_weights field"
```

---

## W2 — Blueprint activation

### Task 2: `SleeveRiskBudget.strategy_id` + `effective_strategy_id` helper

**Files:**
- Modify: `src/tradingx/portfolio/blueprint.py`
- Modify: `tests/unit/test_portfolio_blueprint.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_portfolio_blueprint.py`:

```python
def test_sleeve_risk_budget_strategy_id_defaults_to_none():
    from tradingx.portfolio.blueprint import SleeveRiskBudget
    budget = SleeveRiskBudget(
        sleeve_id="trend-following-v1",
        budget_fraction_of_equity=Decimal("0.5"),
        max_correlation_with_other_sleeves=Decimal("0.85"),
    )
    assert budget.strategy_id is None


def test_sleeve_risk_budget_accepts_explicit_strategy_id():
    from tradingx.portfolio.blueprint import SleeveRiskBudget
    budget = SleeveRiskBudget(
        sleeve_id="trend-following-v1",
        budget_fraction_of_equity=Decimal("0.5"),
        max_correlation_with_other_sleeves=Decimal("0.85"),
        strategy_id="trend-following-v1-paper",
    )
    assert budget.strategy_id == "trend-following-v1-paper"


def test_effective_strategy_id_falls_back_to_sleeve_id_when_none():
    from tradingx.portfolio.blueprint import (
        SleeveRiskBudget,
        effective_strategy_id,
    )
    budget = SleeveRiskBudget(
        sleeve_id="trend-following-v1",
        budget_fraction_of_equity=Decimal("0.5"),
        max_correlation_with_other_sleeves=Decimal("0.85"),
    )
    assert effective_strategy_id(budget) == "trend-following-v1"


def test_effective_strategy_id_honors_explicit_field():
    from tradingx.portfolio.blueprint import (
        SleeveRiskBudget,
        effective_strategy_id,
    )
    budget = SleeveRiskBudget(
        sleeve_id="trend-following-v1",
        budget_fraction_of_equity=Decimal("0.5"),
        max_correlation_with_other_sleeves=Decimal("0.85"),
        strategy_id="explicit-paper-v1",
    )
    assert effective_strategy_id(budget) == "explicit-paper-v1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_blueprint.py -k "effective_strategy_id or strategy_id" -v`

Expected: FAIL — field doesn't exist; helper doesn't exist.

- [ ] **Step 3: Implement**

In `src/tradingx/portfolio/blueprint.py`:

```python
@dataclass(frozen=True)
class SleeveRiskBudget:
    sleeve_id: str
    budget_fraction_of_equity: Decimal
    max_correlation_with_other_sleeves: Decimal
    strategy_id: str | None = None


def effective_strategy_id(budget: SleeveRiskBudget) -> str:
    """Resolve the strategy_id a SleeveRiskBudget binds to.

    Fallback rule: if `budget.strategy_id` is None (the
    default for both shipped sleeves where sleeve_id IS the
    strategy_id), return `budget.sleeve_id`.
    """
    return budget.strategy_id or budget.sleeve_id
```

Add `effective_strategy_id` to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_portfolio_blueprint.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/blueprint.py tests/unit/test_portfolio_blueprint.py
git commit -m "feat(blueprint): add SleeveRiskBudget.strategy_id + effective_strategy_id helper"
```

### Task 3: `BlueprintActivationRecord` + `BlueprintSleeveBinding` types + persistence

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/persistence.py`
- Create: `tests/unit/test_blueprint_activation_persistence.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_blueprint_activation_persistence.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import BlueprintActivationRecord, BlueprintSleeveBinding


def _record(activation_id: str = "act-1") -> BlueprintActivationRecord:
    return BlueprintActivationRecord(
        activation_id=activation_id,
        blueprint_id="bp-default-v1",
        sleeve_activation_bindings=(
            BlueprintSleeveBinding(
                sleeve_id="trend-following-v1",
                strategy_id="trend-following-v1",
                captured_snapshot_id="snap-trend-v1-2026-04-22",
            ),
            BlueprintSleeveBinding(
                sleeve_id="vol-target-v1",
                strategy_id="vol-target-v1",
                captured_snapshot_id="snap-vol-v1-2026-04-22",
            ),
        ),
        status="active",
        approved_at_utc=datetime(2026, 4, 22, 14, 0, tzinfo=UTC),
        approved_by="operator:hussam",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-default-v1.yaml"),
    )


def test_blueprint_activation_record_roundtrip(tmp_path: Path):
    store = FilesystemArtifactStore(tmp_path)
    record = _record()
    path = store.write_blueprint_activation_record(record)
    assert path.exists()
    loaded = store.load_blueprint_activation_record(
        activation_id=record.activation_id,
    )
    assert loaded == record


def test_list_blueprint_activation_records_returns_all(tmp_path: Path):
    store = FilesystemArtifactStore(tmp_path)
    store.write_blueprint_activation_record(_record("act-a"))
    store.write_blueprint_activation_record(_record("act-b"))
    records = store.list_blueprint_activation_records()
    ids = {record.activation_id for record in records}
    assert ids == {"act-a", "act-b"}


def test_missing_blueprint_activation_record_returns_none(tmp_path: Path):
    store = FilesystemArtifactStore(tmp_path)
    assert store.load_blueprint_activation_record(activation_id="nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_blueprint_activation_persistence.py -v`

Expected: FAIL on ImportError for the dataclass or AttributeError for the store methods.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`:

```python
@dataclass(frozen=True)
class BlueprintSleeveBinding:
    sleeve_id: str
    strategy_id: str
    captured_snapshot_id: str


@dataclass(frozen=True)
class BlueprintActivationRecord:
    activation_id: str
    blueprint_id: str
    sleeve_activation_bindings: tuple[BlueprintSleeveBinding, ...]
    status: str  # "active" | "superseded" | "halted"
    approved_at_utc: datetime
    approved_by: str
    source_blueprint_path: Path
    superseded_at_utc: datetime | None = None
    supersedes_activation_id: str | None = None
```

Add both to `__all__`.

In `src/tradingx/persistence.py`, add on `FilesystemArtifactStore`:

```python
def write_blueprint_activation_record(
    self,
    record: BlueprintActivationRecord,
) -> Path:
    return self._write_json(
        "blueprint_activation",
        f"{record.activation_id}.json",
        record,
    )

def load_blueprint_activation_record(
    self,
    *,
    activation_id: str,
) -> BlueprintActivationRecord | None:
    path = self._root_dir / "blueprint_activation" / f"{activation_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return self._deserialize_blueprint_activation_record(payload)

def list_blueprint_activation_records(
    self,
) -> tuple[BlueprintActivationRecord, ...]:
    directory = self._root_dir / "blueprint_activation"
    if not directory.exists():
        return ()
    records: list[BlueprintActivationRecord] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(self._deserialize_blueprint_activation_record(payload))
    return tuple(records)

def _deserialize_blueprint_activation_record(
    self,
    payload: dict[str, Any],
) -> BlueprintActivationRecord:
    return BlueprintActivationRecord(
        activation_id=str(payload["activation_id"]),
        blueprint_id=str(payload["blueprint_id"]),
        sleeve_activation_bindings=tuple(
            BlueprintSleeveBinding(
                sleeve_id=str(entry["sleeve_id"]),
                strategy_id=str(entry["strategy_id"]),
                captured_snapshot_id=str(entry["captured_snapshot_id"]),
            )
            for entry in payload["sleeve_activation_bindings"]
        ),
        status=str(payload["status"]),
        approved_at_utc=datetime.fromisoformat(str(payload["approved_at_utc"])),
        approved_by=str(payload["approved_by"]),
        source_blueprint_path=Path(str(payload["source_blueprint_path"])),
        superseded_at_utc=(
            datetime.fromisoformat(str(payload["superseded_at_utc"]))
            if payload.get("superseded_at_utc") is not None
            else None
        ),
        supersedes_activation_id=payload.get("supersedes_activation_id"),
    )
```

Add `Path` + `BlueprintActivationRecord` + `BlueprintSleeveBinding` to the imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_blueprint_activation_persistence.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py src/tradingx/persistence.py tests/unit/test_blueprint_activation_persistence.py
git commit -m "feat(types): add BlueprintActivationRecord + BlueprintSleeveBinding + persistence"
```

### Task 4: `LocalActivationGateway` blueprint methods

**Files:**
- Modify: `src/tradingx/activation.py`
- Create: `tests/unit/test_blueprint_activation_gateway.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_blueprint_activation_gateway.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.activation import LocalActivationGateway
from tradingx.persistence import FilesystemArtifactStore
from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.types import ApprovedWeightSnapshot
from tradingx.weights import ApprovedWeightSnapshotStore


def _snapshot(strategy_id: str, snapshot_id: str) -> ApprovedWeightSnapshot:
    return ApprovedWeightSnapshot(
        snapshot_id=snapshot_id,
        strategy_id=strategy_id,
        status="active",
        generated_at_utc=datetime(2026, 4, 22, tzinfo=UTC),
        minimum_supporting_trades=0,
        weights={"SPY": Decimal("1.0")},
    )


class _StubSnapshotStore:
    def __init__(self, snapshots: dict[str, ApprovedWeightSnapshot]) -> None:
        self._snapshots = snapshots

    def load_by_strategy_id(self, strategy_id: str) -> ApprovedWeightSnapshot:
        if strategy_id not in self._snapshots:
            from tradingx.weights import ApprovedWeightSnapshotNotFoundError
            raise ApprovedWeightSnapshotNotFoundError(strategy_id)
        return self._snapshots[strategy_id]


def _blueprint(
    strategy_overrides: dict[str, str] | None = None,
) -> PortfolioBlueprint:
    overrides = strategy_overrides or {}
    return PortfolioBlueprint(
        blueprint_id="bp-test-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
                strategy_id=overrides.get("trend-following-v1"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
                strategy_id=overrides.get("vol-target-v1"),
            ),
        ),
    )


def _gateway(tmp_path: Path, snapshot_store) -> LocalActivationGateway:
    operator_store = FilesystemArtifactStore(tmp_path)
    # Gateway constructor shape depends on the existing module; match
    # the shipped signature. The test harness may need to inject the
    # stub snapshot store into the existing gateway via its _snapshot_store
    # seam (whatever shape that seam takes — match activation.py's pattern).
    gateway = LocalActivationGateway(
        store=operator_store,
        strategy_id_validator=lambda _: True,
        snapshot_store=snapshot_store,
    )
    return gateway


def test_activate_blueprint_fresh_writes_record(tmp_path: Path):
    snapshots = {
        "trend-following-v1": _snapshot(
            "trend-following-v1", "snap-trend-1"
        ),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    }
    gateway = _gateway(tmp_path, _StubSnapshotStore(snapshots))

    record = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )

    assert record.status == "active"
    assert record.blueprint_id == "bp-test-v1"
    assert len(record.sleeve_activation_bindings) == 2
    bindings_by_sleeve = {
        binding.sleeve_id: binding
        for binding in record.sleeve_activation_bindings
    }
    assert bindings_by_sleeve["trend-following-v1"].captured_snapshot_id == "snap-trend-1"
    assert bindings_by_sleeve["vol-target-v1"].captured_snapshot_id == "snap-vol-1"


def test_activate_blueprint_idempotent_when_snapshots_unchanged(tmp_path: Path):
    store = _StubSnapshotStore({
        "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-1"),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    })
    gateway = _gateway(tmp_path, store)
    record_a = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )
    record_b = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )
    assert record_a.activation_id == record_b.activation_id


def test_activate_blueprint_new_activation_id_when_snapshot_changes(
    tmp_path: Path,
):
    """Round-2 P1 regression: YAML-edit produces a new
    captured_snapshot_id for the same blueprint_id, and the
    activation must get a fresh activation_id so W6's
    regeneration trigger can fire."""
    snapshot_v1 = {
        "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-v1"),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    }
    gateway = _gateway(tmp_path, _StubSnapshotStore(snapshot_v1))
    record_v1 = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )

    # Simulate an operator YAML edit by swapping the store's
    # backing snapshot for trend-following-v1.
    snapshot_v2 = {
        "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-v2"),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    }
    gateway._snapshot_store = _StubSnapshotStore(snapshot_v2)  # type: ignore[attr-defined]

    record_v2 = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("config/portfolio/blueprints/bp-test-v1.yaml"),
    )

    assert record_v1.activation_id != record_v2.activation_id
    trend_binding = next(
        b
        for b in record_v2.sleeve_activation_bindings
        if b.sleeve_id == "trend-following-v1"
    )
    assert trend_binding.captured_snapshot_id == "snap-trend-v2"


def test_activate_blueprint_missing_snapshot_raises_validation_error(
    tmp_path: Path,
):
    gateway = _gateway(tmp_path, _StubSnapshotStore({}))
    from tradingx.activation import BlueprintActivationValidationError

    with pytest.raises(BlueprintActivationValidationError):
        gateway.load_or_activate_blueprint(
            blueprint=_blueprint(),
            operator_identifier="operator:test",
            source_blueprint_path=Path("bp.yaml"),
        )
    assert gateway.get_active_blueprint_activation() is None


def test_get_active_blueprint_activation_returns_none_when_no_active_record(
    tmp_path: Path,
):
    gateway = _gateway(tmp_path, _StubSnapshotStore({}))
    assert gateway.get_active_blueprint_activation() is None


def test_supersede_active_blueprint_updates_predecessor(tmp_path: Path):
    store = _StubSnapshotStore({
        "trend-following-v1": _snapshot("trend-following-v1", "snap-trend-1"),
        "vol-target-v1": _snapshot("vol-target-v1", "snap-vol-1"),
    })
    gateway = _gateway(tmp_path, store)
    original = gateway.load_or_activate_blueprint(
        blueprint=_blueprint(),
        operator_identifier="operator:test",
        source_blueprint_path=Path("bp.yaml"),
    )
    narrowed_blueprint = PortfolioBlueprint(
        blueprint_id="bp-narrowed-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    narrowed = gateway.load_or_activate_blueprint(
        blueprint=narrowed_blueprint,
        operator_identifier="operator:test",
        source_blueprint_path=Path("bp-narrowed.yaml"),
    )
    # Before supersede, both are 'active' in separate records.
    # Callers perform the supersede explicitly; this test pins
    # the atomic transition.
    updated_predecessor = gateway.supersede_active_blueprint(
        new_activation=narrowed,
        now=datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
    )
    assert updated_predecessor.status == "superseded"
    assert updated_predecessor.superseded_at_utc is not None
    assert updated_predecessor.activation_id == original.activation_id
    # Only one record should now be active.
    active = gateway.get_active_blueprint_activation()
    assert active is not None
    assert active.activation_id == narrowed.activation_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_blueprint_activation_gateway.py -v`

Expected: FAIL on missing `load_or_activate_blueprint` / `get_active_blueprint_activation` / `supersede_active_blueprint` / `BlueprintActivationValidationError`.

- [ ] **Step 3: Implement**

In `src/tradingx/activation.py`:

```python
import uuid

from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    SleeveRiskBudget,
    effective_strategy_id,
)
from tradingx.types import (
    ApprovedWeightSnapshot,
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
)
from tradingx.weights import ApprovedWeightSnapshotNotFoundError


class BlueprintActivationValidationError(ValueError):
    """Raised when a blueprint's bindings cannot be resolved
    against the approved-weight store at activation time.
    """


class LocalActivationGateway:
    # ...existing __init__ + methods unchanged. Add a
    # `snapshot_store` parameter if not already present — the
    # existing ApprovedWeightSnapshotStore is injectable.

    def load_or_activate_blueprint(
        self,
        *,
        blueprint: PortfolioBlueprint,
        operator_identifier: str,
        source_blueprint_path: Path,
    ) -> BlueprintActivationRecord:
        # Resolve each bound strategy's current snapshot.
        bindings: list[BlueprintSleeveBinding] = []
        for budget in blueprint.sleeve_budgets:
            strategy_id = effective_strategy_id(budget)
            try:
                snapshot = self._snapshot_store.load_by_strategy_id(strategy_id)
            except ApprovedWeightSnapshotNotFoundError as exc:
                raise BlueprintActivationValidationError(
                    f"strategy_id {strategy_id!r} bound to sleeve "
                    f"{budget.sleeve_id!r} has no approved-weight snapshot"
                ) from exc
            bindings.append(
                BlueprintSleeveBinding(
                    sleeve_id=budget.sleeve_id,
                    strategy_id=strategy_id,
                    captured_snapshot_id=snapshot.snapshot_id,
                )
            )

        # Idempotency: if an active record exists with the same
        # blueprint_id AND identical bindings, return it unchanged.
        active = self.get_active_blueprint_activation()
        if active is not None:
            if (
                active.blueprint_id == blueprint.blueprint_id
                and tuple(active.sleeve_activation_bindings)
                == tuple(bindings)
            ):
                return active

        record = BlueprintActivationRecord(
            activation_id=f"activation-{uuid.uuid4()}",
            blueprint_id=blueprint.blueprint_id,
            sleeve_activation_bindings=tuple(bindings),
            status="active",
            approved_at_utc=self._now(),
            approved_by=operator_identifier,
            source_blueprint_path=source_blueprint_path,
        )
        self._store.write_blueprint_activation_record(record)
        return record

    def get_active_blueprint_activation(
        self,
    ) -> BlueprintActivationRecord | None:
        records = self._store.list_blueprint_activation_records()
        active = tuple(
            record for record in records if record.status == "active"
        )
        if not active:
            return None
        # Return the latest by approved_at_utc.
        return max(active, key=lambda r: r.approved_at_utc)

    def supersede_active_blueprint(
        self,
        *,
        new_activation: BlueprintActivationRecord,
        now: datetime,
    ) -> BlueprintActivationRecord:
        predecessor = self.get_active_blueprint_activation()
        if predecessor is None or predecessor.activation_id == new_activation.activation_id:
            return new_activation
        updated = dataclasses.replace(
            predecessor,
            status="superseded",
            superseded_at_utc=now,
        )
        self._store.write_blueprint_activation_record(updated)
        return updated

    def _now(self) -> datetime:
        return self._now_provider() if self._now_provider else datetime.now(UTC)
```

Add `_snapshot_store` as a new constructor parameter. Add `BlueprintActivationValidationError` to `__all__`.

If the existing `LocalActivationGateway.__init__` does not already accept a `snapshot_store` kwarg, add it (defaulting to `ApprovedWeightSnapshotStore()` if unspecified, matching the existing module's injection pattern).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_blueprint_activation_gateway.py tests/unit/test_activation.py -v`

Expected: all pass. Existing `test_activation.py` tests continue to pass because the new methods and `snapshot_store` parameter are additive.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/activation.py tests/unit/test_blueprint_activation_gateway.py
git commit -m "feat(activation): add blueprint-as-a-unit activation methods on LocalActivationGateway"
```

---

## W3 — Live portfolio construction per-cycle

### Task 5: Extract `_combine_sleeve_weights` helper

**Files:**
- Modify: `src/tradingx/portfolio/construction.py`
- Modify: `tests/unit/test_portfolio_construction.py` (regression)

**Extraction must preserve 1.4's full cap stack (Codex round-1
plan P1 fix).** The shipped batch path in
[construction.py](/src/tradingx/portfolio/construction.py)
applies THREE stages of caps, not two:

1. Per-sleeve budget scaling (multiply each sleeve's row by
   `budget_fraction_of_equity`).
2. **Per-symbol strictest-holder correlation cap** via
   [`_apply_symbol_overlap_caps`](/src/tradingx/portfolio/construction.py:105)
   — for every symbol held by ≥ 2 sleeves, the cap is
   `max_gross_exposure × min(budget.max_correlation_with_other_sleeves
   for budget in symbol_holders)`. Each symbol can have a
   different cap because the "strictest holder" set differs.
3. Row-level **gross cap** (sum of abs) AND **net cap** (abs
   of sum) via
   [`_apply_row_caps`](/src/tradingx/portfolio/construction.py:131),
   applied as uniform multiplicative scaling across the row.

A single `max_correlation` scalar and a missing net cap would
silently relax the composition and change portfolio math. The
extracted helper accepts the full blueprint (which carries all
three pieces of cap state) and replicates all three stages.

- [ ] **Step 1: Write failing regression**

Add to `tests/unit/test_portfolio_construction.py`:

```python
def test_combine_sleeve_weights_applies_per_symbol_strictest_holder_correlation_cap():
    """Regression from the round-1 plan P1 fix. Each symbol
    held by multiple sleeves is capped by the strictest of
    those sleeves' correlation caps; other symbols see their
    own (possibly different) cap.
    """
    from tradingx.portfolio.blueprint import (
        PortfolioBlueprint,
        SleeveRiskBudget,
    )
    from tradingx.portfolio.construction import _combine_sleeve_weights

    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("0.50"),
            ),
            SleeveRiskBudget(
                sleeve_id="b",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
        max_gross_exposure=Decimal("1.0"),
        max_net_exposure=Decimal("1.0"),
    )
    contributions = {
        "a": {"SPY": Decimal("0.8"), "IWM": Decimal("0.4")},
        "b": {"SPY": Decimal("0.6")},  # overlaps on SPY only
    }
    result = _combine_sleeve_weights(
        blueprint=blueprint,
        contributions=contributions,
    )
    # SPY is overlap-held → cap = max_gross * min(0.50, 0.85) = 0.50.
    # IWM is single-holder → no per-symbol cap applies.
    assert result["SPY"] <= Decimal("0.50") + Decimal("1e-9")
    assert result["IWM"] <= Decimal("0.40") + Decimal("1e-9")


def test_combine_sleeve_weights_applies_row_gross_cap():
    """Gross cap binds when all weights are same-sign and their
    absolute sum exceeds max_gross_exposure."""
    from tradingx.portfolio.blueprint import (
        PortfolioBlueprint,
        SleeveRiskBudget,
    )
    from tradingx.portfolio.construction import _combine_sleeve_weights

    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
        max_gross_exposure=Decimal("1.0"),
        max_net_exposure=Decimal("1.0"),
    )
    contributions = {
        "a": {"SPY": Decimal("0.6"), "QQQ": Decimal("0.6")},
    }
    result = _combine_sleeve_weights(
        blueprint=blueprint,
        contributions=contributions,
    )
    # Raw sum = 1.2; gross cap scales proportionally so
    # sum(abs) == 1.0.
    gross = sum(abs(weight) for weight in result.values())
    assert abs(gross - Decimal("1.0")) < Decimal("1e-9")


def test_combine_sleeve_weights_applies_row_net_cap_when_gross_does_not_bind():
    """Codex round-2 plan P2 fix: isolate net-cap behavior.
    Long/short offsetting weights where sum(abs) <=
    max_gross_exposure but |sum| > max_net_exposure. A helper
    that enforced only the gross cap would leave the net
    unconstrained; the shipped 1.4 math applies both. This test
    fails if the net cap is missing.
    """
    from tradingx.portfolio.blueprint import (
        PortfolioBlueprint,
        SleeveRiskBudget,
    )
    from tradingx.portfolio.construction import _combine_sleeve_weights

    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("1.0"),
            ),
        ),
        # Gross cap is slack — 0.6 + 0.4 = 1.0 within 1.2.
        # Net cap is the binding constraint — 0.6 + (-0.4) = 0.2
        # within 0.1 would require scaling.
        max_gross_exposure=Decimal("1.2"),
        max_net_exposure=Decimal("0.1"),
    )
    contributions = {
        "a": {"SPY": Decimal("0.6"), "HEDGE": Decimal("-0.4")},
    }
    result = _combine_sleeve_weights(
        blueprint=blueprint,
        contributions=contributions,
    )
    # Net = sum(signed_weights) = 0.2 raw → must scale to <= 0.1.
    net = abs(sum(result.values(), start=Decimal("0")))
    assert net <= Decimal("0.1") + Decimal("1e-9")
    # Gross was not binding, so the gross invariant still holds.
    gross = sum(abs(weight) for weight in result.values())
    assert gross <= Decimal("1.2") + Decimal("1e-9")
    # And the scaling was uniform: the ratio between the two
    # weights is preserved after the net cap applies.
    ratio_raw = Decimal("0.6") / Decimal("0.4")
    ratio_scaled = abs(result["SPY"]) / abs(result["HEDGE"])
    assert abs(ratio_raw - ratio_scaled) < Decimal("1e-9")


def test_combine_sleeve_weights_is_pure():
    from tradingx.portfolio.blueprint import (
        PortfolioBlueprint,
        SleeveRiskBudget,
    )
    from tradingx.portfolio.construction import _combine_sleeve_weights

    blueprint = PortfolioBlueprint(
        blueprint_id="bp",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="a",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="b",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    contributions = {
        "a": {"SPY": Decimal("0.4"), "QQQ": Decimal("0.2")},
        "b": {"SPY": Decimal("0.2")},
    }
    first = _combine_sleeve_weights(
        blueprint=blueprint, contributions=contributions,
    )
    second = _combine_sleeve_weights(
        blueprint=blueprint, contributions=contributions,
    )
    assert first == second
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_portfolio_construction.py -k combine_sleeve_weights -v`

Expected: FAIL on ImportError (private helper not yet extracted).

- [ ] **Step 3: Implement**

In `src/tradingx/portfolio/construction.py`, extract the
weight-combination logic from `build_portfolio_target_weight_history`
into a pure helper that consumes the full blueprint so all
three cap stages apply identically to batch and live:

```python
def _combine_sleeve_weights(
    *,
    blueprint: PortfolioBlueprint,
    contributions: dict[str, dict[str, Decimal]],
) -> dict[str, Decimal]:
    """Compose per-sleeve contributions into portfolio-equity-
    space weights.

    Three stages, in this order (stage ordering is load-bearing
    for parity with the shipped batch path):

    1. Per-sleeve budget scaling — multiply each sleeve's
       contributions by its budget_fraction_of_equity.
    2. Per-symbol strictest-holder correlation cap — for each
       symbol held by >= 2 sleeves, cap its combined weight at
       max_gross_exposure * min(holder.max_correlation_with_other_sleeves
       for holder in sleeves_holding_this_symbol). Different
       symbols can have different caps.
    3. Row-level gross cap AND net cap — uniform multiplicative
       scaling so sum(|weights|) <= max_gross_exposure AND
       |sum(weights)| <= max_net_exposure. Both caps apply.

    Pure function. Shared by build_portfolio_target_weight_history
    (batch) and build_portfolio_cycle_target_weights (live).
    The sleeve-id iteration order is deterministic
    (sorted(contributions.keys())) so serialization is
    reproducible.
    """
    # Port the existing logic from
    # build_portfolio_target_weight_history + _apply_symbol_overlap_caps
    # + _apply_row_caps. Reuse those helpers internally rather
    # than re-implementing — the extraction should be
    # mechanical, not a rewrite.
```

Refactor `build_portfolio_target_weight_history` to call `_combine_sleeve_weights(blueprint=..., contributions=...)` for each bar. The pre-existing batch integration tests in 1.4 MUST continue to pass unchanged — that's the canary for the extraction being faithful.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_portfolio_construction.py -v`

Expected: all pass, including the pre-existing 1.4 regression tests.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/construction.py tests/unit/test_portfolio_construction.py
git commit -m "refactor(portfolio): extract _combine_sleeve_weights for batch/live parity"
```

### Task 6: `build_portfolio_cycle_target_weights` with live-vs-batch parity

**Files:**
- Create: `src/tradingx/portfolio/live_construction.py`
- Create: `tests/unit/test_portfolio_live_construction.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_portfolio_live_construction.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.construction import (
    build_portfolio_target_weight_history,
)
from tradingx.portfolio.live_construction import (
    build_portfolio_cycle_target_weights,
)
from tradingx.sleeves.trend import TrendSleeve
from tradingx.sleeves.vol_managed_beta import VolManagedBetaSleeve
from tradingx.types import SleeveTargetWeights

# Reuse the existing _bars / _regimes fixtures from test_portfolio_construction.py
# via conftest or inline import; match the existing harness.


def test_cycle_and_batch_parity_element_wise(
    sample_bars,
    sample_regimes,
    sample_blueprint,
):
    """§P1 regression: live per-cycle construction must produce
    the same aggregate target weights as 1.4's batch path when
    run bar-by-bar across a canned window.
    """
    # Batch reference.
    sleeves = (
        TrendSleeve(allowed_instruments=("SPY", "QQQ")),
        VolManagedBetaSleeve(),
    )
    batch_frame = build_portfolio_target_weight_history(
        sleeves,
        blueprint=sample_blueprint,
        bars_by_symbol=sample_bars,
        regime_snapshots_by_date=sample_regimes,
    )

    # Cycle path: invoke build_portfolio_cycle_target_weights
    # bar-by-bar, accumulate into a DataFrame.
    cycle_rows = []
    # Use the same fixture conventions the existing batch test
    # uses for building per-bar contexts.
    for timestamp in batch_frame.index:
        context_by_sleeve_id = _build_per_sleeve_contexts(
            sleeves, sample_bars, sample_regimes, timestamp,
        )
        sleeves_by_id = {sleeve.sleeve_id: sleeve for sleeve in sleeves}
        aggregate, _decomposition = build_portfolio_cycle_target_weights(
            blueprint=sample_blueprint,
            sleeves_by_id=sleeves_by_id,
            context_by_sleeve_id=context_by_sleeve_id,
        )
        cycle_rows.append(aggregate)
    cycle_frame = _rows_to_frame(cycle_rows, index=batch_frame.index)

    # Element-wise tolerance — Decimal-to-float conversion may
    # introduce 1e-9-level noise.
    for column in batch_frame.columns:
        assert (
            (batch_frame[column] - cycle_frame[column]).abs().max()
            < 1e-9
        )


def test_cycle_returns_decomposition_per_sleeve(
    sample_blueprint,
    sample_single_bar_context_trend,
    sample_single_bar_context_vol,
):
    sleeves_by_id = {
        "trend-following-v1": TrendSleeve(allowed_instruments=("SPY",)),
        "vol-target-v1": VolManagedBetaSleeve(),
    }
    aggregate, decomposition = build_portfolio_cycle_target_weights(
        blueprint=sample_blueprint,
        sleeves_by_id=sleeves_by_id,
        context_by_sleeve_id={
            "trend-following-v1": sample_single_bar_context_trend,
            "vol-target-v1": sample_single_bar_context_vol,
        },
    )
    sleeve_ids = {entry.sleeve_id for entry in decomposition}
    assert sleeve_ids == {"trend-following-v1", "vol-target-v1"}


def test_cycle_aggregate_equals_sum_of_decomposition_within_tolerance(
    sample_blueprint,
    sample_single_bar_context_trend,
    sample_single_bar_context_vol,
):
    sleeves_by_id = {
        "trend-following-v1": TrendSleeve(allowed_instruments=("SPY",)),
        "vol-target-v1": VolManagedBetaSleeve(),
    }
    aggregate, decomposition = build_portfolio_cycle_target_weights(
        blueprint=sample_blueprint,
        sleeves_by_id=sleeves_by_id,
        context_by_sleeve_id={
            "trend-following-v1": sample_single_bar_context_trend,
            "vol-target-v1": sample_single_bar_context_vol,
        },
    )
    # For each symbol in the aggregate, sum of decomposition
    # entries matches the aggregate (post-cap-scaling).
    for symbol, weight in aggregate.items():
        decomposition_sum = sum(
            (
                (dict(entry.target_weights_by_symbol).get(
                    symbol, Decimal("0"),
                ))
                for entry in decomposition
            ),
            start=Decimal("0"),
        )
        assert abs(weight - decomposition_sum) < Decimal("1e-9")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_portfolio_live_construction.py -v`

Expected: FAIL on ImportError for `build_portfolio_cycle_target_weights`.

- [ ] **Step 3: Implement**

Create `src/tradingx/portfolio/live_construction.py`:

```python
"""Per-cycle live portfolio composition per DESIGN-0017 W3."""

from __future__ import annotations

from decimal import Decimal

from tradingx.portfolio.blueprint import (
    PortfolioBlueprint,
    effective_strategy_id,
)
from tradingx.portfolio.construction import _combine_sleeve_weights
from tradingx.sleeves.base import SleeveProtocol
from tradingx.types import SleeveContext, SleeveTargetWeights


def build_portfolio_cycle_target_weights(
    *,
    blueprint: PortfolioBlueprint,
    sleeves_by_id: dict[str, SleeveProtocol],
    context_by_sleeve_id: dict[str, SleeveContext],
) -> tuple[dict[str, Decimal], tuple[SleeveTargetWeights, ...]]:
    """For a single cycle, invoke each sleeve's plan_for_bar to
    get its target weights, then combine via
    _combine_sleeve_weights to produce the aggregate plus a
    per-sleeve decomposition.

    Returns (aggregate_weights, decomposition). Aggregate is
    executed by the service loop; decomposition is persisted
    as SleeveDecompositionRecord in W4.
    """
    budget_by_sleeve_id = {
        budget.sleeve_id: budget.budget_fraction_of_equity
        for budget in blueprint.sleeve_budgets
    }
    contributions: dict[str, dict[str, Decimal]] = {}
    for sleeve_id, sleeve in sleeves_by_id.items():
        context = context_by_sleeve_id[sleeve_id]
        trades = sleeve.plan_for_bar(context)
        contributions[sleeve_id] = {
            trade.symbol: trade.target_weight_of_sleeve_budget
            for trade in trades
            if trade.target_weight_of_sleeve_budget > Decimal("0")
        }

    # Single composition primitive shared with the batch path.
    # _combine_sleeve_weights consumes the whole blueprint so
    # per-symbol strictest-holder correlation caps + row-level
    # gross + net caps all apply identically to live and batch
    # (Codex round-1 plan P1 fix).
    aggregate = _combine_sleeve_weights(
        blueprint=blueprint,
        contributions=contributions,
    )

    # Build the decomposition: each sleeve's contribution AFTER
    # the same cap scaling the aggregate saw (so the
    # decomposition is in portfolio-equity-space per §P4 and
    # sums to the aggregate within tolerance).
    decomposition_entries: list[SleeveTargetWeights] = []
    for sleeve_id in sorted(sleeves_by_id):
        budget_fraction = budget_by_sleeve_id[sleeve_id]
        sleeve_contrib_scaled = {
            symbol: raw_weight * budget_fraction
            for symbol, raw_weight in contributions.get(
                sleeve_id, {}
            ).items()
        }
        # Apply the same per-symbol cap proportional scaling
        # that _combine_sleeve_weights applied to the aggregate:
        # if the aggregate weight was capped, each sleeve's
        # contribution shares the cap proportionally.
        scaled = _rescale_to_aggregate(
            sleeve_contribution=sleeve_contrib_scaled,
            all_contributions_scaled={
                other_id: {
                    symbol: contributions.get(other_id, {}).get(
                        symbol, Decimal("0")
                    )
                    * budget_by_sleeve_id[other_id]
                    for symbol in aggregate
                }
                for other_id in sleeves_by_id
            },
            aggregate=aggregate,
        )
        decomposition_entries.append(
            SleeveTargetWeights(
                sleeve_id=sleeve_id,
                target_weights_by_symbol=tuple(
                    sorted(
                        (symbol, weight)
                        for symbol, weight in scaled.items()
                        if weight > Decimal("0")
                    )
                ),
            )
        )

    return aggregate, tuple(decomposition_entries)


def _rescale_to_aggregate(
    *,
    sleeve_contribution: dict[str, Decimal],
    all_contributions_scaled: dict[str, dict[str, Decimal]],
    aggregate: dict[str, Decimal],
) -> dict[str, Decimal]:
    """Proportionally scale a single sleeve's contribution by
    the aggregate/raw-sum ratio on each symbol, so the final
    per-sleeve entries sum to the aggregate within tolerance.
    """
    result: dict[str, Decimal] = {}
    for symbol, sleeve_raw in sleeve_contribution.items():
        raw_sum = sum(
            (
                per_sleeve_map.get(symbol, Decimal("0"))
                for per_sleeve_map in all_contributions_scaled.values()
            ),
            start=Decimal("0"),
        )
        aggregate_weight = aggregate.get(symbol, Decimal("0"))
        if raw_sum <= Decimal("0"):
            result[symbol] = Decimal("0")
            continue
        scale = aggregate_weight / raw_sum
        result[symbol] = sleeve_raw * scale
    return result


__all__ = ("build_portfolio_cycle_target_weights",)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_portfolio_live_construction.py tests/unit/test_portfolio_construction.py -v`

Expected: all pass. The `test_cycle_and_batch_parity_element_wise` regression is the §P1 load-bearing test.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/live_construction.py tests/unit/test_portfolio_live_construction.py
git commit -m "feat(portfolio): add build_portfolio_cycle_target_weights with batch parity"
```

---

## W4 — Per-sleeve target-weight persistence

### Task 7: `SleeveDecompositionRecord` type + persistence

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/persistence.py`
- Create: `tests/unit/test_sleeve_decomposition_record.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_sleeve_decomposition_record.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import (
    SleeveDecompositionRecord,
    SleeveTargetWeights,
)


def _record(decomposition_id: str = "decomp-1") -> SleeveDecompositionRecord:
    return SleeveDecompositionRecord(
        decomposition_id=decomposition_id,
        cycle_id="cycle-2026-04-22-1430",
        trading_day="2026-04-22",
        recorded_at_utc=datetime(2026, 4, 22, 20, 0, tzinfo=UTC),
        blueprint_activation_id="activation-x",
        per_sleeve_target_weights=(
            SleeveTargetWeights(
                sleeve_id="trend-following-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.4")),),
            ),
            SleeveTargetWeights(
                sleeve_id="vol-target-v1",
                target_weights_by_symbol=(("SPY", Decimal("0.2")),),
            ),
        ),
    )


def test_sleeve_decomposition_record_roundtrip(tmp_path: Path):
    store = FilesystemArtifactStore(tmp_path)
    record = _record()
    store.write_sleeve_decomposition_record(record)
    records = store.list_sleeve_decomposition_records(
        trading_day="2026-04-22",
    )
    assert record in records


def test_list_sleeve_decomposition_filters_by_day(tmp_path: Path):
    store = FilesystemArtifactStore(tmp_path)
    same_day = _record("decomp-a")
    different_day = SleeveDecompositionRecord(
        **{**_record().__dict__, "decomposition_id": "decomp-b",
           "trading_day": "2026-04-23",
           "cycle_id": "cycle-2026-04-23-1430"},
    )
    store.write_sleeve_decomposition_record(same_day)
    store.write_sleeve_decomposition_record(different_day)
    records = store.list_sleeve_decomposition_records(
        trading_day="2026-04-22",
    )
    assert records == (same_day,)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_sleeve_decomposition_record.py -v`

Expected: FAIL on missing types / store methods.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`:

```python
@dataclass(frozen=True)
class SleeveDecompositionRecord:
    decomposition_id: str
    cycle_id: str
    trading_day: str
    recorded_at_utc: datetime
    blueprint_activation_id: str
    per_sleeve_target_weights: tuple[SleeveTargetWeights, ...]
```

Add to `__all__`.

In `src/tradingx/persistence.py`:

```python
def write_sleeve_decomposition_record(
    self,
    record: SleeveDecompositionRecord,
) -> Path:
    return self._write_json(
        "sleeve_decomposition",
        f"{record.trading_day}__{record.decomposition_id}.json",
        record,
    )


def list_sleeve_decomposition_records(
    self,
    *,
    trading_day: str,
) -> tuple[SleeveDecompositionRecord, ...]:
    directory = self._root_dir / "sleeve_decomposition"
    if not directory.exists():
        return ()
    records: list[SleeveDecompositionRecord] = []
    for path in sorted(directory.glob(f"{trading_day}__*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(self._deserialize_sleeve_decomposition_record(payload))
    return tuple(records)


def _deserialize_sleeve_decomposition_record(
    self,
    payload: dict[str, Any],
) -> SleeveDecompositionRecord:
    return SleeveDecompositionRecord(
        decomposition_id=str(payload["decomposition_id"]),
        cycle_id=str(payload["cycle_id"]),
        trading_day=str(payload["trading_day"]),
        recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
        blueprint_activation_id=str(payload["blueprint_activation_id"]),
        per_sleeve_target_weights=tuple(
            SleeveTargetWeights(
                sleeve_id=str(entry["sleeve_id"]),
                target_weights_by_symbol=tuple(
                    (str(pair[0]), Decimal(str(pair[1])))
                    for pair in entry["target_weights_by_symbol"]
                ),
            )
            for entry in payload["per_sleeve_target_weights"]
        ),
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_sleeve_decomposition_record.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py src/tradingx/persistence.py tests/unit/test_sleeve_decomposition_record.py
git commit -m "feat(types): add SleeveDecompositionRecord + persistence"
```

### Task 8: Service-loop sidecar write

**Files:**
- Modify: `src/tradingx/service.py`
- Modify: `src/tradingx/runtime_portfolio.py` (plan populates `per_sleeve_target_weights` when blueprint-active)
- Modify: `tests/unit/test_service.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_service.py`:

```python
def test_service_cycle_writes_decomposition_sidecar_when_blueprint_active(
    service_two_sleeve_blueprint_fixture,
):
    """Blueprint active, two-sleeve cycle → one
    SleeveDecompositionRecord per cycle with both entries.
    The record's cycle_id matches the aggregate plan's
    cycle_id so downstream consumers can join them.
    """
    fixture = service_two_sleeve_blueprint_fixture
    fixture.service.run_one_cycle()

    plans = fixture.operator_store.list_runtime_portfolio_plans()
    assert len(plans) == 1
    plan = plans[0]

    decompositions = fixture.operator_store.list_sleeve_decomposition_records(
        trading_day=plan.trading_day,
    )
    assert len(decompositions) == 1
    record = decompositions[0]
    assert record.cycle_id == plan.cycle_id
    assert {entry.sleeve_id for entry in record.per_sleeve_target_weights} == {
        "trend-following-v1",
        "vol-target-v1",
    }


def test_service_cycle_skips_decomposition_sidecar_in_legacy_mode(
    service_single_strategy_fixture,
):
    fixture = service_single_strategy_fixture
    fixture.service.run_one_cycle()
    decompositions = fixture.operator_store.list_sleeve_decomposition_records(
        trading_day=fixture.trading_day,
    )
    assert decompositions == ()
```

Match the existing `test_service.py` fixture style for both harnesses.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_service.py -k "decomposition" -v`

Expected: FAIL — the service loop does not yet write the sidecar.

- [ ] **Step 3: Implement**

In `src/tradingx/runtime_portfolio.py`:

- `RuntimePortfolioPlanner.plan` accepts an optional `blueprint: PortfolioBlueprint | None = None` kwarg. When present, invoke `build_portfolio_cycle_target_weights` to produce the aggregate + decomposition. Use the decomposition to populate `plan.per_sleeve_target_weights`.

In `src/tradingx/service.py`:

- Inside the per-cycle loop, after calling `RuntimePortfolioPlanner.plan(...)`, check if the plan has a non-empty `per_sleeve_target_weights`. If so, build a `SleeveDecompositionRecord` with the same `cycle_id` and invoke `self._operator_store.write_sleeve_decomposition_record(record)`.
- Obtain the `blueprint_activation_id` from the injected `LocalActivationGateway.get_active_blueprint_activation()` — cache the latest active id at the start of each cycle so the record links to the correct activation.
- If the gateway returns `None` (legacy single-strategy mode), the decomposition is empty and no sidecar is written.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_service.py tests/unit/test_runtime_portfolio.py -v`

Expected: all pass. Existing service/runtime-portfolio tests continue to pass because the blueprint path is gated on a non-None activation.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/service.py src/tradingx/runtime_portfolio.py tests/unit/test_service.py
git commit -m "feat(service): write SleeveDecompositionRecord sidecar per cycle when blueprint active"
```

---

## W5 — Attribution fractions threading

### Task 9: `sleeve_attributions` fields on intent/execution/closed-trade

**Files:**
- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/persistence.py`
- Modify: `tests/unit/test_types.py`
- Modify: existing deserializer tests in the persistence test module.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_types.py`:

```python
def test_trade_intent_sleeve_attributions_defaults_to_empty_tuple():
    intent = _make_minimal_trade_intent()  # existing fixture
    assert intent.sleeve_attributions == ()


def test_trade_intent_accepts_sleeve_attributions():
    intent = _make_trade_intent(
        sleeve_attributions=(
            ("trend-following-v1", Decimal("0.6")),
            ("vol-target-v1", Decimal("0.4")),
        ),
    )
    assert intent.sleeve_attributions == (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )


def test_execution_lifecycle_record_sleeve_attributions_default_empty():
    record = _make_minimal_execution_record()
    assert record.sleeve_attributions == ()


def test_closed_trade_record_entry_and_exit_attributions_default_empty():
    record = _make_minimal_closed_trade_record()
    assert record.entry_sleeve_attributions == ()
    assert record.exit_sleeve_attributions == ()


def test_closed_trade_record_accepts_both_attribution_fields():
    record = _make_closed_trade_record(
        entry_sleeve_attributions=(("trend-following-v1", Decimal("1")),),
        exit_sleeve_attributions=(
            ("trend-following-v1", Decimal("0.6")),
            ("vol-target-v1", Decimal("0.4")),
        ),
    )
    assert record.entry_sleeve_attributions == (
        ("trend-following-v1", Decimal("1")),
    )
    assert record.exit_sleeve_attributions == (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_types.py -k "sleeve_attributions or entry_sleeve_attributions" -v`

Expected: FAIL — fields don't exist.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`, extend the three dataclasses:

```python
@dataclass(frozen=True)
class TradeIntent:
    # ...existing fields...
    sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()


@dataclass(frozen=True)
class ExecutionLifecycleRecord:
    # ...existing fields...
    sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()


@dataclass(frozen=True)
class ClosedTradeRecord:
    # ...existing fields...
    entry_sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()
    exit_sleeve_attributions: tuple[tuple[str, Decimal], ...] = ()
```

Update `FilesystemArtifactStore._write_json` / related serializers so the new tuples round-trip. Update deserializers to read them with `payload.get(..., [])` and default to `()` when absent (backwards compat for pre-2.1 persisted payloads).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_types.py tests/unit/test_persistence.py -v`

Expected: all pass. Pre-2.1 persisted-payload deserialization regression is pinned by the default-to-empty-tuple path.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/types.py src/tradingx/persistence.py tests/unit/test_types.py
git commit -m "feat(types): add sleeve_attributions fields to TradeIntent/ExecutionLifecycleRecord/ClosedTradeRecord"
```

### Task 10: Populate attribution fractions from the decomposition

**Files:**
- Modify: `src/tradingx/runtime_portfolio.py`
- Modify: `src/tradingx/execution.py` (propagate through execution path)
- Modify: `src/tradingx/lifecycle.py` (or the closed-trade aggregator; name matches the existing module)
- Create: `tests/unit/test_sleeve_attributions_threading.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_sleeve_attributions_threading.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest


def test_trade_intent_attributions_sum_to_one_within_tolerance(
    sample_two_sleeve_plan,
):
    """For every blueprint-based intent, sleeve_attributions
    fractions sum to 1.0 within Decimal('1e-9')."""
    for intent in sample_two_sleeve_plan.trade_intents:
        if intent.sleeve_attributions == ():
            continue  # legacy/baseline path
        total = sum(
            (fraction for _sleeve_id, fraction in intent.sleeve_attributions),
            start=Decimal("0"),
        )
        assert abs(total - Decimal("1")) < Decimal("1e-9")


def test_trade_intent_attributions_ordered_descending_then_registry_order(
    sample_spy_two_sleeve_intent,  # SPY held by both sleeves; 60/40 split
):
    expected = (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )
    assert sample_spy_two_sleeve_intent.sleeve_attributions == expected


def test_trade_intent_tie_breaks_by_registry_order(
    sample_spy_50_50_intent,
):
    expected = (
        ("trend-following-v1", Decimal("0.5")),
        ("vol-target-v1", Decimal("0.5")),
    )
    assert sample_spy_50_50_intent.sleeve_attributions == expected


def test_legacy_single_strategy_intent_has_empty_attributions(
    sample_legacy_single_strategy_plan,
):
    for intent in sample_legacy_single_strategy_plan.trade_intents:
        assert intent.sleeve_attributions == ()


def test_execution_lifecycle_inherits_attributions_from_intent(
    sample_two_sleeve_execution_pair,
):
    intent, record = sample_two_sleeve_execution_pair
    assert record.sleeve_attributions == intent.sleeve_attributions


def test_closed_trade_captures_entry_and_exit_separately_across_activation_change(
    sample_activation_change_closed_trade,
):
    """Entry intent was 100% trend; exit intent was 60/40 after
    a blueprint change; ClosedTradeRecord stores both sides."""
    record = sample_activation_change_closed_trade
    assert record.entry_sleeve_attributions == (
        ("trend-following-v1", Decimal("1")),
    )
    assert record.exit_sleeve_attributions == (
        ("trend-following-v1", Decimal("0.6")),
        ("vol-target-v1", Decimal("0.4")),
    )


def test_gate3_evidence_reader_computes_per_sleeve_notional(
    sample_multi_fill_execution_records,
):
    """§W5 Gate 3 consumption contract: summing
    fill_qty * fill_price * fraction across records by
    sleeve_id gives the per-sleeve fill notional."""
    from tradingx.execution import sum_per_sleeve_notional

    notional_by_sleeve = sum_per_sleeve_notional(
        sample_multi_fill_execution_records,
    )
    # Sample fixture arranges records such that trend-following-v1
    # should have a known aggregate notional (see fixture doc).
    assert notional_by_sleeve["trend-following-v1"] == (
        sample_multi_fill_execution_records.expected_trend_notional
    )
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_sleeve_attributions_threading.py -v`

Expected: FAIL — population logic and helper not yet implemented.

- [ ] **Step 3: Implement**

In `src/tradingx/runtime_portfolio.py`, update `_trade_intent_for_plan_item` to compute `sleeve_attributions` from the decomposition:

```python
from tradingx.strategy import build_mandatory_candidate_registry


def _compute_sleeve_attributions(
    *,
    symbol: str,
    decomposition: tuple[SleeveTargetWeights, ...],
) -> tuple[tuple[str, Decimal], ...]:
    """Compute fractions per sleeve for the symbol. Returns
    empty tuple when decomposition is empty (legacy).
    """
    if not decomposition:
        return ()
    contributions: dict[str, Decimal] = {}
    for entry in decomposition:
        contribution = dict(entry.target_weights_by_symbol).get(
            symbol, Decimal("0")
        )
        if contribution > Decimal("0"):
            contributions[entry.sleeve_id] = contribution
    total = sum(contributions.values(), start=Decimal("0"))
    if total <= Decimal("0"):
        return ()
    registry_order = {
        candidate.candidate_id: index
        for index, candidate in enumerate(
            build_mandatory_candidate_registry()
        )
    }

    def _sort_key(item: tuple[str, Decimal]) -> tuple[Decimal, int]:
        sleeve_id, fraction = item
        # Descending fraction → negate; ties break by registry
        # order (ascending).
        return (-fraction, registry_order.get(sleeve_id, 1_000_000))

    fractions = sorted(
        ((sleeve_id, value / total) for sleeve_id, value in contributions.items()),
        key=_sort_key,
    )
    return tuple(fractions)
```

Update `_trade_intent_for_plan_item(plan_item, ..., decomposition=...)` to attach `sleeve_attributions=_compute_sleeve_attributions(symbol=plan_item.symbol, decomposition=decomposition)` to the created `TradeIntent`.

In `src/tradingx/execution.py`, the existing path that constructs `ExecutionLifecycleRecord` from a `TradeIntent` + broker fill must thread `sleeve_attributions=intent.sleeve_attributions` onto the record.

In the closed-trade aggregator (`src/tradingx/lifecycle.py` or the shipped equivalent), the entry and exit intents' `sleeve_attributions` are captured onto the `ClosedTradeRecord.entry_sleeve_attributions` and `.exit_sleeve_attributions` fields respectively.

Add a public `sum_per_sleeve_notional` helper in `src/tradingx/execution.py`:

```python
def sum_per_sleeve_notional(
    records: tuple[ExecutionLifecycleRecord, ...],
) -> dict[str, Decimal]:
    """Gate 3 per-sleeve evidence reader. For each fill,
    per-sleeve notional is fill_qty * fill_price * fraction.
    Records with empty sleeve_attributions (legacy/baseline)
    are skipped.
    """
    result: dict[str, Decimal] = {}
    for record in records:
        if not record.sleeve_attributions:
            continue
        fill_notional = record.filled_qty * record.fill_price
        for sleeve_id, fraction in record.sleeve_attributions:
            result[sleeve_id] = result.get(sleeve_id, Decimal("0")) + (
                fill_notional * fraction
            )
    return result
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_sleeve_attributions_threading.py tests/unit/test_runtime_portfolio.py tests/unit/test_execution.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/runtime_portfolio.py src/tradingx/execution.py src/tradingx/lifecycle.py tests/unit/test_sleeve_attributions_threading.py
git commit -m "feat(runtime_portfolio): populate sleeve_attributions fractions + sum_per_sleeve_notional"
```

---

## W6 — Artifact regeneration on activation change

### Task 11: Activation-change detector keyed on `activation_id`

**Files:**
- Modify: `src/tradingx/automation.py`
- Modify: `src/tradingx/drift/reference.py` (add `force_rebuild=True` path on the build helper — currently checked in 1.5's `_load_or_build_reference_snapshot` in `automation.py`; pull it into the drift module if that's cleaner or keep it in automation).
- Modify: `src/tradingx/drift/backtest_reference.py` (ignore existing file when `force_rebuild=True`).
- Create: `tests/unit/test_drift_artifact_regeneration.py`
- Create: `tests/integration/test_activation_change_regeneration.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_drift_artifact_regeneration.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def test_last_activation_file_written_on_first_boot(
    market_day_runner_with_blueprint_fixture,
):
    """First automation-runner build with an active blueprint
    writes the last_activation.json pin."""
    fixture = market_day_runner_with_blueprint_fixture
    last_activation_path = (
        fixture.artifact_root / "drift" / "last_activation.json"
    )
    assert last_activation_path.exists()
    payload = json.loads(last_activation_path.read_text(encoding="utf-8"))
    assert payload["activation_id"] == fixture.current_activation_id


def test_same_activation_id_does_not_regenerate(
    market_day_runner_with_blueprint_fixture,
):
    """Rebuilding with the same activation_id is a no-op for
    artifact regeneration."""
    fixture = market_day_runner_with_blueprint_fixture
    reference_path = (
        fixture.artifact_root
        / "drift"
        / "reference_distribution_snapshot.json"
    )
    first_mtime = reference_path.stat().st_mtime
    fixture.rebuild_runner()
    assert reference_path.stat().st_mtime == first_mtime


def test_new_activation_id_triggers_regeneration(
    market_day_runner_with_blueprint_fixture,
):
    fixture = market_day_runner_with_blueprint_fixture
    reference_path = (
        fixture.artifact_root
        / "drift"
        / "reference_distribution_snapshot.json"
    )
    original_mtime = reference_path.stat().st_mtime

    # Simulate an operator action that produces a new activation_id
    # (blueprint change, YAML edit, etc.).
    fixture.activate_new_blueprint()
    fixture.rebuild_runner()

    assert reference_path.stat().st_mtime > original_mtime
    last_activation_path = (
        fixture.artifact_root / "drift" / "last_activation.json"
    )
    payload = json.loads(last_activation_path.read_text(encoding="utf-8"))
    assert payload["activation_id"] == fixture.current_activation_id


def test_same_blueprint_id_new_captured_snapshot_triggers_regeneration(
    market_day_runner_with_blueprint_fixture,
):
    """§W6 round-2 P1 regression: same blueprint_id but a YAML
    edit produced a new captured_snapshot_id, which produces a
    new activation_id, which MUST trigger regeneration."""
    fixture = market_day_runner_with_blueprint_fixture
    reference_path = (
        fixture.artifact_root
        / "drift"
        / "reference_distribution_snapshot.json"
    )
    original_mtime = reference_path.stat().st_mtime

    fixture.edit_approved_weight_yaml("trend-following-v1")  # new snapshot_id
    fixture.rebuild_runner()

    assert reference_path.stat().st_mtime > original_mtime


def test_operator_recalibrate_triggers_regeneration_without_deleting_audit_marker(
    market_day_runner_with_blueprint_fixture,
):
    """Round-1 plan P1 fix. Recalibration uses the 1.5
    operator-control audit marker
    (drift_reference_recalibration.json on operator_store root)
    as the trigger source — no separate pending file, no
    OperatorControlStore constructor surgery. The audit marker
    is NEVER deleted; the automation runner tracks
    last_processed_recalibration_at in its own bookkeeping
    file."""
    fixture = market_day_runner_with_blueprint_fixture
    reference_path = (
        fixture.artifact_root
        / "drift"
        / "reference_distribution_snapshot.json"
    )
    audit_marker_path = (
        fixture.operator_control_store._root_dir
        / "drift_reference_recalibration.json"
    )
    bookkeeping_path = (
        fixture.artifact_root / "drift" / "last_activation.json"
    )
    original_mtime = reference_path.stat().st_mtime

    fixture.operator_control_store.recalibrate_drift_reference(
        snapshot_id="ref-operator-1",
        now=fixture.now(),
    )
    assert audit_marker_path.exists()

    fixture.rebuild_runner()

    # Regeneration triggered.
    assert reference_path.stat().st_mtime > original_mtime
    # Audit marker preserved (not deleted).
    assert audit_marker_path.exists()
    # Bookkeeping updated so the next rebuild is idempotent.
    bookkeeping = json.loads(bookkeeping_path.read_text(encoding="utf-8"))
    assert bookkeeping["last_processed_recalibration_at"] is not None


def test_second_rebuild_after_recalibration_is_idempotent(
    market_day_runner_with_blueprint_fixture,
):
    fixture = market_day_runner_with_blueprint_fixture
    reference_path = (
        fixture.artifact_root
        / "drift"
        / "reference_distribution_snapshot.json"
    )
    fixture.operator_control_store.recalibrate_drift_reference(
        snapshot_id="ref-operator-1",
        now=fixture.now(),
    )
    fixture.rebuild_runner()
    after_first_rebuild_mtime = reference_path.stat().st_mtime

    # Same audit marker, no activation change, no new
    # recalibration → no regeneration.
    fixture.rebuild_runner()
    assert reference_path.stat().st_mtime == after_first_rebuild_mtime


def test_operator_recalibrate_from_service_py_construction_site_triggers_regeneration(
    market_day_runner_with_blueprint_fixture,
):
    """§P2 cross-seam regression: the operator-control store
    constructed in service.py (or controller.py / supervisor.py)
    shares the same root_dir as the one the automation runner
    reads. A recalibrate call from any of those production
    sites must produce a marker the runner can see on the next
    rebuild — no new constructor parameter needed.
    """
    fixture = market_day_runner_with_blueprint_fixture
    # Fixture exposes a second store instance with the same
    # root, mimicking the multi-construction-site layout.
    secondary_store = fixture.make_secondary_operator_store()

    secondary_store.recalibrate_drift_reference(
        snapshot_id="ref-from-service",
        now=fixture.now(),
    )
    reference_path = (
        fixture.artifact_root
        / "drift"
        / "reference_distribution_snapshot.json"
    )
    original_mtime = reference_path.stat().st_mtime

    fixture.rebuild_runner()

    assert reference_path.stat().st_mtime > original_mtime
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_drift_artifact_regeneration.py -v`

Expected: FAIL — regeneration detector not yet implemented.

- [ ] **Step 3: Implement**

**Recalibration-marker seam (Codex round-1 plan P1 fix).** The
round-1 plan proposed extending `OperatorControlStore.__init__`
with a `drift_pending_recalibration_path: Path | None = None`
parameter and wiring it through `build_default_market_day_automation_runner`.
Codex correctly flagged that `OperatorControlStore` is
constructed in **four** places — not just the automation
runner. The production construction sites are:

- [service.py:559](/src/tradingx/service.py:559) — paper
  trading service's operator-control store.
- [controller.py:1559](/src/tradingx/controller.py:1559) —
  gate validation controller's store.
- [supervisor.py:662](/src/tradingx/supervisor.py:662) —
  local supervisor's store.
- [automation.py:719](/src/tradingx/automation.py:719) —
  market-day automation runner (the only seam the round-1
  plan updated).

Threading a new constructor parameter through all four sites
is a wide surface change where three sites don't care about
the path at all. Worse, if the operator triggers
`recalibrate_drift_reference` from a code path whose store was
constructed without the new parameter, the marker silently
doesn't get written and the automation runner misses the
regeneration trigger.

**Revised approach: reuse the 1.5 audit marker already shipped
on the operator-control store's own root directory.** The 1.5
`OperatorControlStore.recalibrate_drift_reference` at
[operator_control.py:72](/src/tradingx/operator_control.py:72)
already writes `self._root_dir / "drift_reference_recalibration.json"`
with `{"snapshot_id": ..., "at_utc": ...}`. That file lives on
every construction site by construction — no new parameter
threading is required. The automation runner reads from it
directly.

**Control-store root vs artifact-store root (Codex round-2
plan P1 fix).** Two similarly-named things that are NOT the
same directory:

- `operator_store` in
  [`build_default_market_day_automation_runner`](/src/tradingx/automation.py:725)
  is a `FilesystemArtifactStore` rooted at
  `config.runtime.artifact_root / "operator_platform"` —
  this is the operator-platform audit/evidence tree (trade
  intents, order records, sleeve halts, etc.).
- `OperatorControlStore` (the class in
  [`operator_control.py`](/src/tradingx/operator_control.py:82))
  is rooted at `config.runtime.data_root / "control"` in
  every production construction site
  ([service.py:559](/src/tradingx/service.py:559),
  [controller.py:1559](/src/tradingx/controller.py:1559),
  [supervisor.py:662](/src/tradingx/supervisor.py:662)) —
  this is where `recalibrate_drift_reference` writes the
  audit marker.

The automation runner's regeneration detector MUST read from
the **control-store root** (`config.runtime.data_root /
"control"`), not from `operator_store._root_dir`. Reading
from the wrong path silently misses every operator-triggered
recalibration.

**Implementation in `src/tradingx/operator_control.py`:** no
change. The 1.5 behavior is already what we need.

**Implementation in `src/tradingx/automation.py`:** the
regeneration-trigger check reads the operator-control store's
audit marker and compares its `at_utc` against a
`last_processed_recalibration_at` bookkeeping value that the
automation runner maintains in
`{artifact_root}/drift/last_activation.json`. The combined
bookkeeping file now carries two fields:

```json
{
  "activation_id": "<uuid>",
  "last_processed_recalibration_at": "2026-04-22T14:00:00Z"
}
```

The regeneration decision becomes:

```python
def _read_last_seen_bookkeeping(path: Path) -> dict[str, str | None]:
    if not path.exists():
        return {"activation_id": None, "last_processed_recalibration_at": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"activation_id": None, "last_processed_recalibration_at": None}
    return {
        "activation_id": str(payload.get("activation_id") or "") or None,
        "last_processed_recalibration_at": (
            str(payload.get("last_processed_recalibration_at") or "")
            or None
        ),
    }


def _read_operator_recalibration_marker_timestamp(
    control_store_root: Path,
) -> datetime | None:
    """Read at_utc from the 1.5 audit marker written by
    OperatorControlStore.recalibrate_drift_reference. Path is
    control_store_root / "drift_reference_recalibration.json"
    — NOT the operator-platform artifact-store root. See the
    Codex round-2 plan P1 fix above for the distinction.
    """
    path = control_store_root / "drift_reference_recalibration.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    at_raw = payload.get("at_utc")
    if at_raw is None:
        return None
    normalized = str(at_raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).astimezone(UTC)
    except ValueError:
        return None


def _write_last_seen_bookkeeping(
    path: Path,
    *,
    activation_id: str | None,
    last_processed_recalibration_at: str | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str | None] = {
        "activation_id": activation_id,
        "last_processed_recalibration_at": last_processed_recalibration_at,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


# inside build_default_market_day_automation_runner:

bookkeeping_path = artifact_root / "drift" / "last_activation.json"
# control_store_root matches the path the shipped
# OperatorControlStore uses in service.py, controller.py, and
# supervisor.py: config.runtime.data_root / "control".
control_store_root = config.runtime.data_root / "control"
current_activation = activation_gateway.get_active_blueprint_activation()
last_seen = _read_last_seen_bookkeeping(bookkeeping_path)
marker_at = _read_operator_recalibration_marker_timestamp(
    control_store_root=control_store_root,
)

activation_changed = (
    current_activation is not None
    and current_activation.activation_id != last_seen["activation_id"]
)
recalibration_fresh = (
    marker_at is not None
    and (
        last_seen["last_processed_recalibration_at"] is None
        or datetime.fromisoformat(
            last_seen["last_processed_recalibration_at"].replace("Z", "+00:00"),
        ).astimezone(UTC) < marker_at
    )
)

if activation_changed or recalibration_fresh:
    reference_snapshot = _load_or_build_reference_snapshot(..., force_rebuild=True)
    _ensure_backtest_reference_returns(..., force_rebuild=True)
    _write_last_seen_bookkeeping(
        bookkeeping_path,
        activation_id=(
            current_activation.activation_id
            if current_activation is not None
            else last_seen["activation_id"]
        ),
        last_processed_recalibration_at=(
            marker_at.isoformat().replace("+00:00", "Z")
            if marker_at is not None
            else last_seen["last_processed_recalibration_at"]
        ),
    )
```

**What this buys.** `OperatorControlStore` stays untouched.
Operator calls to `recalibrate_drift_reference` through ANY
production construction site (`service.py`, `controller.py`,
`supervisor.py`, `automation.py`) all write the 1.5 audit
marker at `config.runtime.data_root / "control" /
"drift_reference_recalibration.json"`, which every site
already configures (via `OperatorControlStore(root_dir=
config.runtime.data_root / "control")`). The automation
runner reads from that same control-store root on the next
build and triggers regeneration — no new parameter threading
and no path mismatch between the writing sites and the
reading site.

**What this does NOT do.** The audit marker is NEVER deleted
by the automation runner — it is an operator-audit artifact
and must remain readable for forensic purposes. The bookkeeping
path in `{artifact_root}/drift/last_activation.json` is what
tracks "which marker the runner has already processed,"
preventing duplicate regenerations for the same recalibration.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_drift_artifact_regeneration.py tests/unit/test_automation.py tests/unit/test_operator_control.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/automation.py src/tradingx/drift/reference.py src/tradingx/drift/backtest_reference.py tests/unit/test_drift_artifact_regeneration.py
git commit -m "feat(automation): regenerate drift artifacts on activation-change + recalibrate"
```

Note the file list: `operator_control.py` is **not** in this
task's commit. Per the round-1 plan P1 fix, the 1.5 audit
marker already written by `OperatorControlStore.recalibrate_drift_reference`
is the trigger source — no changes needed on the store side.

---

## W7 — Single-sleeve fallback / rollback path

### Task 12: `narrow_blueprint_on_sleeve_failure` + service-loop integration

**Files:**
- Create: `src/tradingx/portfolio/fallback.py`
- Modify: `src/tradingx/service.py` (detect structural-failure persistence, invoke fallback)
- Create: `tests/unit/test_blueprint_fallback.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_blueprint_fallback.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.portfolio.fallback import (
    BlueprintExhaustionError,
    narrow_blueprint_on_sleeve_failure,
)
from tradingx.types import SleeveFailureReason


def _blueprint_with_two_sleeves() -> PortfolioBlueprint:
    return PortfolioBlueprint(
        blueprint_id="bp-v1",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="trend-following-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
            SleeveRiskBudget(
                sleeve_id="vol-target-v1",
                budget_fraction_of_equity=Decimal("0.5"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )


class _SpyGateway:
    def __init__(self) -> None:
        self.superseded: list[tuple[str, datetime]] = []

    def supersede_active_blueprint(self, *, new_activation, now):
        self.superseded.append((new_activation.activation_id, now))


class _SpyEventSink:
    def __init__(self) -> None:
        self.events = []

    def write_risk_control_event(self, event):
        self.events.append(event)


class _SpyAlertGateway:
    def __init__(self) -> None:
        self.alerts = []

    def publish(self, alert):
        self.alerts.append(alert)


def test_narrow_removes_failed_sleeve_and_preserves_surviving_budget(
    tmp_path: Path,
):
    narrowed_blueprint, narrowed_activation = narrow_blueprint_on_sleeve_failure(
        active_blueprint=_blueprint_with_two_sleeves(),
        active_activation=_active_record(),
        failed_sleeve_id="vol-target-v1",
        failure_reason=SleeveFailureReason.HALT_BY_OPERATOR,
        operator_identifier="operator:test",
        now=datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
        activation_gateway=_SpyGateway(),
        risk_control_event_sink=_SpyEventSink(),
        alert_gateway=_SpyAlertGateway(),
    )
    assert [b.sleeve_id for b in narrowed_blueprint.sleeve_budgets] == [
        "trend-following-v1",
    ]
    trend_budget = narrowed_blueprint.sleeve_budgets[0]
    # Surviving sleeve keeps its original budget fraction.
    assert trend_budget.budget_fraction_of_equity == Decimal("0.5")


def test_narrow_emits_risk_control_event_and_alert(tmp_path: Path):
    sink = _SpyEventSink()
    alerts = _SpyAlertGateway()
    narrow_blueprint_on_sleeve_failure(
        active_blueprint=_blueprint_with_two_sleeves(),
        active_activation=_active_record(),
        failed_sleeve_id="vol-target-v1",
        failure_reason=SleeveFailureReason.DRIFT_ALARM_LIVE,
        operator_identifier="operator:test",
        now=datetime(2026, 4, 22, 15, 0, tzinfo=UTC),
        activation_gateway=_SpyGateway(),
        risk_control_event_sink=sink,
        alert_gateway=alerts,
    )
    assert len(sink.events) == 1
    assert sink.events[0].control_type == "blueprint_narrowed"
    assert sink.events[0].severity == "warning"
    assert sink.events[0].operator_visible is True
    assert len(alerts.alerts) == 1
    assert alerts.alerts[0].category == "blueprint_narrowed"
    assert "vol-target-v1" in alerts.alerts[0].summary
    assert "DRIFT_ALARM_LIVE" in alerts.alerts[0].summary.upper()


def test_narrow_raises_on_zero_survivor():
    one_sleeve = PortfolioBlueprint(
        blueprint_id="bp-one",
        sleeve_budgets=(
            SleeveRiskBudget(
                sleeve_id="only-sleeve",
                budget_fraction_of_equity=Decimal("1.0"),
                max_correlation_with_other_sleeves=Decimal("0.85"),
            ),
        ),
    )
    with pytest.raises(BlueprintExhaustionError):
        narrow_blueprint_on_sleeve_failure(
            active_blueprint=one_sleeve,
            active_activation=_active_record(sleeves=("only-sleeve",)),
            failed_sleeve_id="only-sleeve",
            failure_reason=SleeveFailureReason.HALT_BY_OPERATOR,
            operator_identifier="operator:test",
            now=datetime.now(UTC),
            activation_gateway=_SpyGateway(),
            risk_control_event_sink=_SpyEventSink(),
            alert_gateway=_SpyAlertGateway(),
        )


@pytest.mark.parametrize(
    "trigger",
    [
        SleeveFailureReason.REGIME_STRESSED,
        SleeveFailureReason.INSUFFICIENT_HISTORY,
    ],
)
def test_narrow_refuses_non_structural_trigger(trigger):
    with pytest.raises(ValueError, match="not a structural trigger"):
        narrow_blueprint_on_sleeve_failure(
            active_blueprint=_blueprint_with_two_sleeves(),
            active_activation=_active_record(),
            failed_sleeve_id="vol-target-v1",
            failure_reason=trigger,
            operator_identifier="operator:test",
            now=datetime.now(UTC),
            activation_gateway=_SpyGateway(),
            risk_control_event_sink=_SpyEventSink(),
            alert_gateway=_SpyAlertGateway(),
        )
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_blueprint_fallback.py -v`

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement**

Create `src/tradingx/portfolio/fallback.py`:

```python
"""Single-sleeve fallback / rollback primitive per DESIGN-0017 W7."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Protocol

from tradingx.portfolio.blueprint import PortfolioBlueprint, SleeveRiskBudget
from tradingx.types import (
    BlueprintActivationRecord,
    BlueprintSleeveBinding,
    OperatorAlert,
    RiskControlEvent,
    SleeveFailureReason,
)


BLUEPRINT_NARROWED_CONTROL_TYPE: Final[str] = "blueprint_narrowed"


class BlueprintExhaustionError(RuntimeError):
    """Raised when narrowing would leave the blueprint with zero
    sleeves. Running with zero sleeves is a halt, not a fallback.
    """


# Structural triggers per W7 round-1 + round-2 amendments.
_STRUCTURAL_TRIGGERS: Final[frozenset[str]] = frozenset(
    {
        SleeveFailureReason.HALT_BY_OPERATOR,
        SleeveFailureReason.DRIFT_ALARM_LIVE,
        SleeveFailureReason.SLEEVE_SHARPE_BELOW_THRESHOLD_6M,
    }
)


class ActivationGatewaySupersedeProtocol(Protocol):
    def supersede_active_blueprint(
        self, *, new_activation: BlueprintActivationRecord, now: datetime,
    ) -> BlueprintActivationRecord: ...


class RiskControlEventSinkProtocol(Protocol):
    def write_risk_control_event(self, event: RiskControlEvent) -> object: ...


class OperatorAlertGatewayProtocol(Protocol):
    def publish(self, alert: OperatorAlert) -> None: ...


def narrow_blueprint_on_sleeve_failure(
    *,
    active_blueprint: PortfolioBlueprint,
    active_activation: BlueprintActivationRecord,
    failed_sleeve_id: str,
    failure_reason: str,
    operator_identifier: str,
    now: datetime,
    activation_gateway: ActivationGatewaySupersedeProtocol,
    risk_control_event_sink: RiskControlEventSinkProtocol,
    alert_gateway: OperatorAlertGatewayProtocol,
) -> tuple[PortfolioBlueprint, BlueprintActivationRecord]:
    if failure_reason not in _STRUCTURAL_TRIGGERS:
        raise ValueError(
            f"{failure_reason!r} is not a structural trigger; "
            "narrowing only fires on HALT_BY_OPERATOR, "
            "DRIFT_ALARM_LIVE, or SLEEVE_SHARPE_BELOW_THRESHOLD_6M "
            "(see DESIGN-0017 W7 and BRIEF-0002 D4 for the regime-"
            "stressed exclusion)"
        )
    survivors = tuple(
        budget
        for budget in active_blueprint.sleeve_budgets
        if budget.sleeve_id != failed_sleeve_id
    )
    if not survivors:
        raise BlueprintExhaustionError(
            f"narrowing blueprint {active_blueprint.blueprint_id!r} "
            f"on sleeve {failed_sleeve_id!r} would leave zero sleeves"
        )

    narrowed_blueprint = PortfolioBlueprint(
        blueprint_id=f"{active_blueprint.blueprint_id}--narrowed-{uuid.uuid4().hex[:8]}",
        sleeve_budgets=survivors,
        max_gross_exposure=active_blueprint.max_gross_exposure,
        max_net_exposure=active_blueprint.max_net_exposure,
        mdd_design_target=active_blueprint.mdd_design_target,
        mdd_hard_halt=active_blueprint.mdd_hard_halt,
        cdar_confidence=active_blueprint.cdar_confidence,
        cdar_soft_throttle_threshold=active_blueprint.cdar_soft_throttle_threshold,
        annualized_turnover_budget=active_blueprint.annualized_turnover_budget,
        sleeve_three_month_sharpe_floor=active_blueprint.sleeve_three_month_sharpe_floor,
    )

    surviving_bindings = tuple(
        binding
        for binding in active_activation.sleeve_activation_bindings
        if binding.sleeve_id != failed_sleeve_id
    )
    narrowed_activation = BlueprintActivationRecord(
        activation_id=f"activation-{uuid.uuid4()}",
        blueprint_id=narrowed_blueprint.blueprint_id,
        sleeve_activation_bindings=surviving_bindings,
        status="active",
        approved_at_utc=now,
        approved_by=operator_identifier,
        source_blueprint_path=active_activation.source_blueprint_path,
        superseded_at_utc=None,
        supersedes_activation_id=active_activation.activation_id,
    )
    activation_gateway.supersede_active_blueprint(
        new_activation=narrowed_activation, now=now,
    )

    summary = (
        f"Blueprint narrowed: removed {failed_sleeve_id!r} due to "
        f"{failure_reason}; surviving sleeves: "
        f"{[b.sleeve_id for b in survivors]!r}."
    )
    risk_control_event_sink.write_risk_control_event(
        RiskControlEvent(
            event_id=f"blueprint-narrow-{uuid.uuid4()}",
            intent_id=None,
            severity="warning",
            control_type=BLUEPRINT_NARROWED_CONTROL_TYPE,
            blocked=False,
            recorded_at_utc=now,
            operator_visible=True,
        )
    )
    alert_gateway.publish(
        OperatorAlert(
            alert_id=f"blueprint-narrow-alert-{uuid.uuid4()}",
            severity="warning",
            category=BLUEPRINT_NARROWED_CONTROL_TYPE,
            summary=summary,
            evidence_refs=(),
            delivery_targets=("operator_dashboard",),
            sent_at_utc=now,
        )
    )
    return narrowed_blueprint, narrowed_activation


__all__ = (
    "BLUEPRINT_NARROWED_CONTROL_TYPE",
    "BlueprintExhaustionError",
    "narrow_blueprint_on_sleeve_failure",
)
```

In `src/tradingx/service.py`, add per-cycle tracking of structural-termination rationales per sleeve; after 3 consecutive cycles of the same structural trigger for the same sleeve, invoke `narrow_blueprint_on_sleeve_failure` and swap the active blueprint in the service loop. Transient single-cycle terminations reset the counter. Regime-stressed terminations (which the sleeve runtime controller does not emit at all — regime is a sleeve-internal gate) never increment the counter.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_blueprint_fallback.py tests/unit/test_service.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio/fallback.py src/tradingx/service.py tests/unit/test_blueprint_fallback.py
git commit -m "feat(portfolio): add narrow_blueprint_on_sleeve_failure + 3-cycle service-loop detector"
```

### Task 13: Rollback drill integration test

**Files:**
- Create: `tests/integration/test_fallback_drill.py`

- [ ] **Step 1: Write the integration test**

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest


def test_operator_halt_narrows_blueprint_after_three_cycles(
    two_sleeve_paper_fixture,
):
    """Operator halts one sleeve → service loop runs 3 cycles
    with that termination → blueprint narrows → surviving
    sleeve continues running → blueprint_narrowed event pair
    emitted."""
    fixture = two_sleeve_paper_fixture

    fixture.operator_control.halt_sleeve(
        sleeve_id="vol-target-v1",
        reason="operator drill",
    )

    for _ in range(3):
        fixture.service.run_one_cycle()

    active = fixture.activation_gateway.get_active_blueprint_activation()
    assert active is not None
    surviving_sleeves = {
        binding.sleeve_id for binding in active.sleeve_activation_bindings
    }
    assert surviving_sleeves == {"trend-following-v1"}

    # Predecessor is superseded.
    records = fixture.operator_store.list_blueprint_activation_records()
    superseded = tuple(
        r for r in records if r.status == "superseded"
    )
    assert len(superseded) == 1
    assert superseded[0].sleeve_activation_bindings[0].sleeve_id in (
        "trend-following-v1",
        "vol-target-v1",
    )

    # blueprint_narrowed events emitted.
    events = fixture.list_risk_control_events(
        control_type="blueprint_narrowed",
    )
    assert len(events) == 1
    alerts = fixture.list_operator_alerts(
        category="blueprint_narrowed",
    )
    assert len(alerts) == 1


def test_rollback_reactivates_original_blueprint(
    two_sleeve_paper_fixture,
):
    """After narrowing, operator resumes the halted sleeve and
    re-activates the original blueprint."""
    fixture = two_sleeve_paper_fixture
    fixture.operator_control.halt_sleeve(
        sleeve_id="vol-target-v1",
        reason="operator drill",
    )
    for _ in range(3):
        fixture.service.run_one_cycle()

    fixture.operator_control.resume_sleeve(sleeve_id="vol-target-v1")
    # Operator re-activates the full two-sleeve blueprint.
    fixture.activation_gateway.load_or_activate_blueprint(
        blueprint=fixture.original_blueprint,
        operator_identifier="operator:drill",
        source_blueprint_path=fixture.blueprint_path,
    )
    fixture.service.run_one_cycle()

    active = fixture.activation_gateway.get_active_blueprint_activation()
    sleeve_ids = {
        binding.sleeve_id for binding in active.sleeve_activation_bindings
    }
    assert sleeve_ids == {"trend-following-v1", "vol-target-v1"}
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/integration/test_fallback_drill.py -v`

Expected: pass (once W7 Task 12 is in place).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_fallback_drill.py
git commit -m "test(integration): operator-halt fallback drill across 3 cycles"
```

---

## W8 — Operator dashboard two-sleeve view

### Task 14: Per-sleeve rows + BlueprintActivationRecord header

**Files:**
- Modify: existing operator-dashboard modules (exact files match the current layout; inspect `src/tradingx/portfolio.py` / `src/tradingx/performance.py` or the equivalents before editing).
- Create: `tests/unit/test_dashboard_two_sleeve_view.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_dashboard_two_sleeve_view.py`:

```python
def test_dashboard_header_shows_active_blueprint_when_present(
    two_sleeve_dashboard_fixture,
):
    snapshot = two_sleeve_dashboard_fixture.build_snapshot()
    header = snapshot.header  # adapt to the actual snapshot shape
    assert header.active_blueprint_id is not None
    assert header.active_blueprint_id == "bp-default-v1"
    assert "trend-following-v1" in header.constituent_sleeve_ids
    assert "vol-target-v1" in header.constituent_sleeve_ids


def test_dashboard_shows_per_sleeve_rows_when_blueprint_active(
    two_sleeve_dashboard_fixture,
):
    snapshot = two_sleeve_dashboard_fixture.build_snapshot()
    sleeve_rows = snapshot.per_sleeve_rows
    assert {row.sleeve_id for row in sleeve_rows} == {
        "trend-following-v1",
        "vol-target-v1",
    }


def test_dashboard_surfaces_drift_verdict_per_sleeve(
    two_sleeve_dashboard_fixture_with_critical_ks,
):
    snapshot = two_sleeve_dashboard_fixture_with_critical_ks.build_snapshot()
    by_sleeve = {row.sleeve_id: row for row in snapshot.per_sleeve_rows}
    assert by_sleeve["trend-following-v1"].drift_severity == "critical"
    assert by_sleeve["vol-target-v1"].drift_severity in {"info", "pending"}


def test_dashboard_falls_back_to_legacy_layout_when_no_blueprint(
    single_strategy_dashboard_fixture,
):
    snapshot = single_strategy_dashboard_fixture.build_snapshot()
    # When no blueprint is active, the per-sleeve rows are empty
    # and the legacy single-strategy layout is preserved.
    assert snapshot.per_sleeve_rows == ()
    assert snapshot.header.active_blueprint_id is None


def test_dashboard_surfaces_narrowed_blueprint_with_banner(
    narrowed_blueprint_dashboard_fixture,
):
    snapshot = narrowed_blueprint_dashboard_fixture.build_snapshot()
    assert len(snapshot.per_sleeve_rows) == 1
    assert snapshot.header.narrowing_notice is not None
    assert "vol-target-v1" in snapshot.header.narrowing_notice
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_dashboard_two_sleeve_view.py -v`

Expected: FAIL — dashboard snapshot doesn't yet carry per-sleeve rows or the blueprint header.

- [ ] **Step 3: Implement**

Add per-sleeve row fields to the existing dashboard snapshot types (whatever shape the operator platform uses). The test fixture names suggest a `snapshot.per_sleeve_rows: tuple[PerSleeveRow, ...]` and a `snapshot.header: BlueprintHeader` — match or adapt to the shipped conventions. Inspect the `portfolio.py` + `performance.py` modules before writing production code; follow whatever the existing pattern already establishes.

Data wiring:
- Header active_blueprint_id, constituent_sleeve_ids, narrowing_notice come from `LocalActivationGateway.get_active_blueprint_activation()`.
- Per-sleeve exposure + drift severities come from `DriftAlarmGateway.latest_verdicts()` keyed by `sleeve_id`.
- Per-sleeve daily return comes from `SleeveDailyAttributionRecord` for today's trading_day (falls back to "pending" if no record).
- Per-sleeve halt state from `OperatorControlStore.is_sleeve_halted`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_dashboard_two_sleeve_view.py -v`

Expected: all pass. Existing dashboard tests continue to pass (legacy layout preserved when no blueprint is active).

- [ ] **Step 5: Commit**

```bash
git add src/tradingx/portfolio.py src/tradingx/performance.py tests/unit/test_dashboard_two_sleeve_view.py
git commit -m "feat(dashboard): add two-sleeve per-sleeve rows + blueprint activation header"
```

---

## W9 — Stage 1 closing pass

### Task 15: Integration + regression + INDEX bump

**Files:**
- Create: `tests/integration/test_two_sleeve_paper_cycle.py` (full blueprint-based end-to-end).
- Modify: `docs/INDEX.md` (INDEX version bump if any tranche-2.1 artifact additions land that touch the index; otherwise no-op).

- [ ] **Step 1: Write the end-to-end integration test**

```python
def test_two_sleeve_paper_cycle_end_to_end(
    two_sleeve_paper_fixture,
):
    """Full cycle: activate blueprint, run one service cycle,
    assert aggregate plan + decomposition persisted, intents
    carry sleeve_attributions, attribution records populate
    for both sleeves, dashboard surfaces both sleeves."""
    fixture = two_sleeve_paper_fixture

    # Service loop runs one cycle.
    fixture.service.run_one_cycle()

    # Aggregate plan persisted.
    plans = fixture.operator_store.list_runtime_portfolio_plans()
    assert len(plans) == 1
    plan = plans[0]
    assert len(plan.per_sleeve_target_weights) == 2

    # Decomposition sidecar persisted.
    decompositions = fixture.operator_store.list_sleeve_decomposition_records(
        trading_day=plan.trading_day,
    )
    assert len(decompositions) == 1

    # Intents carry non-empty attributions (symbol with
    # contributions from both sleeves).
    intents = fixture.list_trade_intents()
    blueprint_intents = tuple(
        intent for intent in intents if intent.sleeve_attributions
    )
    assert len(blueprint_intents) > 0
    for intent in blueprint_intents:
        total = sum(
            (fraction for _sleeve_id, fraction in intent.sleeve_attributions),
            start=Decimal("0"),
        )
        assert abs(total - Decimal("1")) < Decimal("1e-9")

    # Dashboard surfaces both sleeves.
    snapshot = fixture.build_dashboard_snapshot()
    assert len(snapshot.per_sleeve_rows) == 2
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/integration/test_two_sleeve_paper_cycle.py -v`

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_two_sleeve_paper_cycle.py
git commit -m "test(integration): two-sleeve paper cycle end-to-end"
```

- [ ] **Step 4: Full regression**

Run in order:

```bash
uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py
uv run mypy src/tradingx
uv run ruff check src/tradingx tests
python3 scripts/check_index.py
./scripts/validate
```

All must pass.

- [ ] **Step 5: Commit formatting fixups (if any)**

```bash
git status
# if auto-format diffs appear:
git add -u
git commit -m "chore: formatting fixups after tranche 2.1 Stage 1"
```

Skip if no fixups needed.

---

## W10 — Stage 2 follow-up commit (separate merge)

### Task 16: Activate drift `pnl::<sleeve_id>` monitor for both sleeves

**Files:**
- Modify: `src/tradingx/drift/gateway.py` (no code change — just threshold calibration against live data; may be a tests-only commit if existing logic already handles activation automatically).
- Modify: `tests/unit/test_drift_gateway.py` + fixtures that previously pinned `pending` verdicts for non-active sleeves to now pin real verdicts.

- [ ] **Step 1: Write failing regression**

Update fixtures so both sleeves have `SleeveDailyAttributionRecord`s populated across the 30+ day minimum-live-days window. Update `test_drift_gateway.py` assertions to expect `pending` → `info` / `warning` / `critical` severities per sleeve.

Key assertion changes:
- Previously: `test_has_alarm_false_when_all_monitors_info` asserted non-active sleeve's `pnl::vol-target-v1` verdict was `pending`.
- Now: asserts `info` (real verdict based on populated attribution data).

Add a new regression:

```python
def test_both_sleeves_produce_real_pnl_verdicts_after_attribution_accumulates(
    gateway_with_30d_attribution_both_sleeves_fixture,
):
    gateway = gateway_with_30d_attribution_both_sleeves_fixture.gateway
    verdicts = gateway.refresh()
    pnl_verdicts = {
        v.monitor_id: v
        for v in verdicts
        if v.monitor_id.startswith("pnl::")
    }
    assert set(pnl_verdicts.keys()) == {
        "pnl::trend-following-v1",
        "pnl::vol-target-v1",
    }
    for v in pnl_verdicts.values():
        assert v.severity != "pending"
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/unit/test_drift_gateway.py -v`

Expected: fails on the old pending assertions; the new regression fails too until fixtures populate attribution.

- [ ] **Step 3: Implement**

Update fixtures to populate 30+ days of `SleeveDailyAttributionRecord`s for both `trend-following-v1` and `vol-target-v1`. No production code change is expected — 1.5's `_pnl_verdicts` loop already iterates both sleeves; it was returning `pending` solely because the attribution reader returned empty for non-active sleeves.

If the threshold calibration against the accumulated live data shows the default thresholds are too tight / loose, adjust `DriftMonitorBlueprint.DriftThresholds` defaults accordingly — but this is an operational judgment call that should only fire if paper-session evidence from Stage 1 surfaces a calibration problem. If thresholds hold, no production code change is needed.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_drift_gateway.py -v`

Expected: all pass.

- [ ] **Step 5: Commit (separate from Stage 1 merge)**

```bash
git add tests/unit/test_drift_gateway.py
git commit -m "feat(drift): activate pnl::<sleeve_id> monitor for both sleeves (tranche 2.1 Stage 2)"
```

This is the Stage-2 commit per BRIEF-0003 D5. It lands on `main` **after** Stage 1 (Tasks 1–15) has accumulated at least one week of paper-session data showing the live attribution records populate correctly and the thresholds hold against real behavior.

---

## Self-review

### Spec coverage

- DESIGN-0017 W1 (`SleeveTargetWeights` + decomposition field): Task 1.
- DESIGN-0017 W2 (SleeveRiskBudget.strategy_id + BlueprintActivationRecord + gateway): Tasks 2–4.
- DESIGN-0017 W3 (live portfolio construction): Tasks 5–6.
- DESIGN-0017 W4 (SleeveDecompositionRecord persistence + service-loop sidecar): Tasks 7–8.
- DESIGN-0017 W5 (sleeve_attributions fractions threading + Gate 3 reader): Tasks 9–10.
- DESIGN-0017 W6 (artifact regeneration on activation change): Task 11.
- DESIGN-0017 W7 (single-sleeve fallback): Tasks 12–13.
- DESIGN-0017 W8 (dashboard two-sleeve view): Task 14.
- DESIGN-0017 W9 (Stage 1 closing pass): Task 15.
- DESIGN-0017 W10 (Stage 2 drift activation): Task 16.

### Placeholder scan

No TBD / TODO / "implement later" in production code. Fixture-name placeholders in tests are implementer-match-existing-convention (sample_bars, sample_regimes, two_sleeve_paper_fixture, etc.) — same pattern as the 1.4 and 1.5 plans.

### Type consistency

- `SleeveTargetWeights` from Task 1 consumed by Tasks 4, 6, 7, 8, 10.
- `BlueprintActivationRecord` + `BlueprintSleeveBinding` from Task 3 consumed by Tasks 4, 7, 11, 12, 14.
- `SleeveRiskBudget.strategy_id` + `effective_strategy_id` from Task 2 consumed by Task 4.
- `_combine_sleeve_weights` from Task 5 consumed by Task 6 (and by the pre-existing batch path — the extraction preserves 1.4's element-wise parity regression).
- `SleeveDecompositionRecord` from Task 7 consumed by Task 8.
- `sleeve_attributions` fields from Task 9 populated by Task 10, read by Task 14 dashboards and Task 15 integration test.
- `narrow_blueprint_on_sleeve_failure` from Task 12 exercised by Task 13 drill.
- Activation-change detector from Task 11 consumed nowhere else; self-contained.
- Stage 2's Task 16 reads already-existing `SleeveDailyAttributionRecord`s produced by 1.5 — no production code change required beyond fixture calibration.

### Open judgment calls left to the implementer

1. **Tie-breaking for attribution fractions** (Task 10). Registry order (trend-first) favors `trend-following-v1` on 50/50 splits. If you prefer budget-fraction ordering, the change is one sort key swap.
2. **3-cycle persistence threshold** (Task 12). The service-loop's per-cycle counter is a straightforward pattern; if Codex sees a better place to track persistence (e.g., on the `SleeveRuntimeController` itself), flag it.
3. **`BlueprintExhaustionError` handling** (Task 12). `narrow_blueprint_on_sleeve_failure` raises; the service loop catches it and transitions to a full `recovery_required` halt via the existing `trigger_hard_halt` path. Conservative; if Codex prefers an auto-switch to the legacy baseline, flag it.
4. **Recalibration-marker seam (resolved in round-1 plan
   review P1 fix)** (Task 11). The round-1 plan proposed
   threading a new path through `OperatorControlStore.__init__`.
   Codex correctly flagged that the store is constructed in
   four places (service.py, controller.py, supervisor.py,
   automation.py), not just the automation runner. The plan
   now reuses the shipped 1.5 audit marker at
   `{config.runtime.data_root}/control/drift_reference_recalibration.json`
   — the control-store root every production site uses. No
   constructor-parameter threading, no `operator_control.py`
   change. Automation runner reads the marker on each build
   and compares its `at_utc` against its own bookkeeping.
   (The round-2 P1 fix corrected an earlier version of this
   note that referenced `operator_store._root_dir` — which is
   the operator-platform artifact store at
   `artifact_root/operator_platform`, a different directory
   from the control-store root.)
5. **Dashboard file surface** (Task 14). The plan points at `portfolio.py` + `performance.py`; actual operator-platform layout may differ. Match existing convention.
6. **Stage 2 timing (Task 16)**. Stage 2 ships after at least one week of Stage 1 paper-session data confirms attribution records populate reliably. This is an operator-triggered ship decision, not an automated one.

### Execution handoff

Plan is for Codex to execute. No subagent-driven or inline execution invocation from this session. Same pattern as tranches 1.1 through 1.5.
