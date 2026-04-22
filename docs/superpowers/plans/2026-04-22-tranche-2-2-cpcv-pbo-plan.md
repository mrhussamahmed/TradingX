# Tranche 2.2 CPCV + PBO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute [DESIGN-0018](../specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md)
— ship the combinatorial purged cross-validation (CPCV) splitter,
the probability-of-backtest-overfitting (PBO) computation, the
persistence layer for `CPCVTrialRecord` / `PBOReport`, and the
Gate-1-validation-pipeline wiring that starts accruing post-§W1
CPCV evidence.

**Stage 1 (Tasks 1–9)** ships only the infrastructure. At Stage 1
merge:

- `controller.py::GateValidationController.generate_gate_report`
  invokes the CPCV helper (`validation.py::_run_cpcv_for_candidate`)
  on eligible candidates and persists 45 `CPCVTrialRecord`s per
  candidate per Gate 1 cycle.
- `compute_pbo` is exercised by unit + integration tests but is
  **not invoked** from the Gate 1 pipeline. Per [DESIGN-0018 §D7](../specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md)
  the runtime `pbo_value` stays `None` on every evidence pack
  throughout Stage 1 — the activation ADR (gate 5) has not fired.
- Criterion 7 continues to report "pending" in the Gate 1
  narrative. `docs/validation/acceptance_gates.md` is unchanged.

**Stage 2 (Task 10)** is the deferred activation: a single-PR
landing that (a) wires `compute_pbo` into the validation pipeline
and populates `pbo_value` / `pbo_report_id` on the evidence pack
when §P4 gates 3 AND 4 clear at evaluation time, (b) flips
criterion 7 from pending to hard-gate, (c) writes the dedicated
Stage 2 activation ADR per [§D6](../specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md),
and (d) updates `docs/validation/acceptance_gates.md`. Preconditions
for Task 10 execution:

- `FilesystemArtifactStore.list_cpcv_cohort_windows()` contains at
  least one summary with `earliest_recorded_at_utc ≤ now -
  timedelta(days=182)` (§P4 gate 3).
- The CURRENT evaluation's cohort summary (looked up separately
  by its `cohort_window_id`) has `strategy_config_count ≥ 50` AND
  `path_count == math.comb(n_groups, test_group_count)` (§P4
  gate 4).

These two gates are checked independently — per DESIGN-0018 §P4,
gate 4 applies to the **current evaluation's cohort**, not to
whichever mature cohort satisfied gate 3.

**Architecture:** Additive only — no existing tranche-1/tranche-2.1
behavior changes.

- New module `src/tradingx/pbo.py` hosts `compute_pbo`,
  `InsufficientCPCVCohortError`, and `MixedCohortWindowError`.
- `src/tradingx/validation_folds.py` gains `generate_cpcv_paths`
  alongside the existing `purged_kfold_indices` (§W7 transition
  window keeps both; no deprecation here).
- `src/tradingx/types.py` gains the `CPCVTrialRecord`,
  `PBOReport`, and `CPCVCohortWindowSummary` dataclasses; the
  existing `EvaluationEvidencePack` gets two nullable `pbo_*`
  fields (§W5).
- `src/tradingx/persistence.py` gains writers, readers, and
  the `list_cpcv_trial_records` + `list_cpcv_cohort_windows`
  methods on `FilesystemArtifactStore`; two new category
  directories (`cpcv_trials/`, `pbo_reports/`) get registered in
  the operator evidence report.
- `src/tradingx/validation.py` gains a private helper
  `_run_cpcv_for_candidate` — a stateless utility that takes
  (candidate, bars, window, artifact_store) and writes the 45
  `CPCVTrialRecord`s. It lives beside the other validation
  utilities but does **not** modify `build_gate_report`'s
  signature. `build_gate_report` stays pure; its existing
  callers (production and tests) are unchanged in Stage 1.
- `src/tradingx/controller.py::GateValidationController.generate_gate_report`
  is the orchestration site. That method already:
  (a) builds `bars_by_symbol` from `self._market_data`
  ([controller.py:1477–1484](/src/tradingx/controller.py:1477)),
  (b) owns the validation `FilesystemArtifactStore` at
  `self._artifacts`, (c) calls `build_gate_report(...)`.
  Stage 1 inserts a CPCV invocation loop between (a) and (c):
  for every candidate, call `_run_cpcv_for_candidate` with the
  store. `build_gate_report`'s call is unchanged. The CPCV write
  is a persistent side effect that does not feed back into the
  returned `ValidationReport` during Stage 1.
- `evaluate_candidate` in `src/tradingx/evaluation.py` stays on
  its existing precomputed-returns surface. CPCV is orchestrated
  at the controller layer (Gate 1 driver), not inside
  `evaluate_candidate`.
- Per DESIGN-0018 §W7, the incumbent `purged_kfold_indices` is
  preserved; every existing caller continues unchanged.

No changes to tranche 2.1 runtime plumbing, the drift stack, the
operator platform, the backtest engine, the sleeves, or any
existing ADR. Criterion 7 narrative in
`docs/validation/acceptance_gates.md` is NOT updated in Stage 1
— that edit lands with Task 10's Stage 2 activation ADR.

**Tech Stack:** Python 3.11. `Decimal` at all numeric boundaries.
`pandas` where the existing validation-folds / evaluation code
already uses it. `pytest` for tests. Existing `uv run` invocations.
Standard library `hashlib` for the deterministic
`cohort_window_id` hash; `math.comb` for the combinatorial path
count; `itertools.combinations` for the CPCV test-group
enumeration; `secrets`-free `random.Random(seed=...)` for
the PBO Monte Carlo split sampling (§P3 determinism). No new
runtime dependencies.

---

## Scope

Implements DESIGN-0018 §W1–§W9 in this order. **No §W6 code
lands in Stage 1** — the criterion-7 evaluator is untouched (it
stays the same "pending" stub it is today). Task 10 is the
single activation commit that (a) wires `compute_pbo` into the
Gate 1 pipeline, (b) populates `EvaluationEvidencePack.pbo_value`,
and (c) flips criterion 7 from reported-only to hard-gate.

1. **W1** — `generate_cpcv_paths` splitter.
2. **W2** — `CPCVTrialRecord` dataclass + filesystem
   writer/reader.
3. **W4** — `PBOReport` and `CPCVCohortWindowSummary`
   dataclasses + `PBOReport` writer/reader.
4. **W8** — `list_cpcv_trial_records` +
   `list_cpcv_cohort_windows`.
5. **W3** — `compute_pbo` + error types + new
   `src/tradingx/pbo.py` module.
6. **W5** — `EvaluationEvidencePack.pbo_value` +
   `pbo_report_id` schema extension.
7. **W7 + CPCV orchestration** — transition window and
   validation-layer CPCV wiring that writes `CPCVTrialRecord`s
   per eligible candidate. Stage 1 leaves `pbo_value = None` on
   every evidence pack per §D7; Task 10 is the activation that
   begins populating it.
8. **Integration test** — end-to-end through the real Gate 1
   entrypoint with a valid two-sleeve candidate set: splitter →
   `CPCVTrialRecord` persistence → cohort-query readback →
   standalone `compute_pbo` sanity call against the assembled
   cohort. Stage 1 invariants asserted: no `pbo_reports/`
   written, `pbo_value` would remain `None` on any persisted
   evidence (Gate 1's report is a `ValidationReport`, not a
   directly-returned evidence pack — see Task 8 for the specifics).
9. **Stage 1 closing pass** — operator evidence report category
   registration, INDEX status bump for DESIGN-0018 to
   `1.0.0 active`, regression sweep.
10. **W6 Stage 2 activation [deferred]** — single-commit flip of
    criterion 7 from reported-only to hard-gate, plus Stage 2
    activation ADR, plus `docs/validation/acceptance_gates.md`
    narrative update. Lands only after §P4 gates 3 + 4 clear.

Tranche-2.1 outcomes (multi-sleeve runtime, sleeve attribution,
blueprint fallback, Gate 3 readers) are unchanged by this tranche.
Stage 2's criterion-7 flip is a single evaluator change; no
infrastructure rework.

## File structure

### New files

- `src/tradingx/pbo.py` — `compute_pbo`,
  `InsufficientCPCVCohortError`, `MixedCohortWindowError`,
  `_cohort_window_id_for` helper (Task 5).
- `tests/unit/test_cpcv_paths.py` — §W1 splitter unit suite
  (Task 1).
- `tests/unit/test_cpcv_trial_record.py` — §W2 schema +
  persistence round-trip (Task 2).
- `tests/unit/test_pbo_report.py` — §W4 schema + persistence
  round-trip + `CPCVCohortWindowSummary` construction
  (Task 3).
- `tests/unit/test_cpcv_cohort_queries.py` — §W8
  `list_cpcv_trial_records` + `list_cpcv_cohort_windows`
  (Task 4).
- `tests/unit/test_pbo_compute.py` — §W3 `compute_pbo`
  algorithm (Task 5).
- `tests/unit/test_evaluation_evidence_pbo_fields.py` — §W5
  EvaluationEvidencePack deserialization with the new fields
  (Task 6).
- `tests/unit/test_validation_cpcv_orchestration.py` — Task 7
  validation-layer CPCV helper unit coverage (record-count
  invariant, Stage 1 no-PBO-writes invariant, insufficient-history
  skip, sleeve-less-candidate no-op).
- `tests/integration/test_cpcv_pbo_pipeline.py` — Task 8
  end-to-end.

### Modified files

- `src/tradingx/validation_folds.py` — add
  `generate_cpcv_paths` (Task 1); `purged_kfold_indices`
  untouched.
- `src/tradingx/types.py` — add `CPCVTrialRecord` (Task 2),
  `PBOReport` + `CPCVCohortWindowSummary` (Task 3); extend
  `EvaluationEvidencePack` with two nullable fields (Task 6).
  `__all__` updates ship with each task.
- `src/tradingx/persistence.py` —
  `write_cpcv_trial_record` + `_deserialize_cpcv_trial_record`
  (Task 2); `write_pbo_report` + `load_pbo_report_by_evaluation_id`
  + `_deserialize_pbo_report` (Task 3);
  `list_cpcv_trial_records` + `list_cpcv_cohort_windows`
  (Task 4); operator-evidence-report category registration for
  `cpcv_trials` and `pbo_reports` (Task 9).
- `src/tradingx/validation.py` — add the private helper
  `_run_cpcv_for_candidate(candidate, bars_by_symbol,
  window_start_utc, window_end_utc, artifact_store, ...)`
  (Task 7). Stateless utility; writes 45 `CPCVTrialRecord`
  artifacts per eligible candidate and returns the tuple.
  `build_gate_report` is **not** modified in Stage 1.
- `src/tradingx/controller.py` — modify
  `GateValidationController.generate_gate_report` (Task 7)
  to invoke `_run_cpcv_for_candidate` for each candidate,
  threading `self._artifacts`. The CPCV call sits between the
  existing bars construction and the `build_gate_report` call.
  In Stage 1, the return value (tuple of records) is discarded
  — persistence is the side effect; there's no feed-back into
  the `ValidationReport`. (Stage 2 — Task 10 — expands this to
  also run `compute_pbo` and thread the resulting `pbo_value`
  into the evidence pack.)
- `docs/INDEX.md` — DESIGN-0018 status flip to
  `1.0.0 active` when the implementation lands (Task 9).

### Untouched (intentional)

- `src/tradingx/trials.py` and `trials.db` — per §W8 rationale,
  CPCV records are file-based; the tranche-1.1 SQLite ledger is
  preserved as-is.
- `src/tradingx/evaluation.py` — `evaluate_candidate` keeps its
  existing surface. Stage 1's CPCV work lives one layer up (in
  `validation.py`) per the §P1 architecture note above. The
  `EvaluationEvidencePack.pbo_value` / `pbo_report_id` fields
  (§W5 / Task 6) are only schema additions in Stage 1; no
  evaluate_candidate code path populates them yet.
- `docs/validation/acceptance_gates.md` — updated by Task 10,
  not Stage 1.
- `docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md`
  — no amendment; the Stage 2 activation ADR is a separate ADR,
  created under Task 10.
- Tranche-2.1 runtime plumbing, drift stack, operator platform,
  dashboard — none touched.

---

## W1 — `generate_cpcv_paths` splitter

### Task 1: CPCV splitter with purging and embargo

**Files:**

- Modify: `src/tradingx/validation_folds.py`
- Create: `tests/unit/test_cpcv_paths.py`

**Dependencies:** none. Pure function; no types, no persistence.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_cpcv_paths.py`:

```python
from __future__ import annotations

import math

import pytest

from tradingx.validation_folds import generate_cpcv_paths


def test_generates_c_n_k_paths_for_valid_inputs() -> None:
    paths = generate_cpcv_paths(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )
    assert len(paths) == math.comb(10, 2)  # 45


def test_each_path_splits_samples_into_train_and_test() -> None:
    n_samples = 1000
    paths = generate_cpcv_paths(
        n_samples=n_samples,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )
    for train, test in paths:
        assert set(train).isdisjoint(set(test))
        assert set(train) | set(test) | set(range(n_samples)) == set(
            range(n_samples)
        )


def test_embargo_removes_adjacent_training_samples() -> None:
    paths = generate_cpcv_paths(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )
    for train, test in paths:
        test_end = max(test) if test else 0
        # No training index may fall in (test_end, test_end + 5].
        for idx in range(test_end + 1, min(1000, test_end + 6)):
            assert idx not in train


def test_deterministic_across_calls() -> None:
    args = dict(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )
    assert generate_cpcv_paths(**args) == generate_cpcv_paths(**args)


def test_rejects_k_equal_1() -> None:
    with pytest.raises(ValueError, match="test_group_count"):
        generate_cpcv_paths(
            n_samples=1000,
            n_groups=10,
            test_group_count=1,
            embargo_days=5,
            label_horizon=1,
        )


def test_rejects_n_groups_below_4() -> None:
    with pytest.raises(ValueError, match="n_groups"):
        generate_cpcv_paths(
            n_samples=1000,
            n_groups=3,
            test_group_count=2,
            embargo_days=5,
            label_horizon=1,
        )


def test_rejects_embargo_smaller_than_label_horizon() -> None:
    with pytest.raises(ValueError, match="embargo_days"):
        generate_cpcv_paths(
            n_samples=1000,
            n_groups=10,
            test_group_count=2,
            embargo_days=0,
            label_horizon=1,
        )


def test_rejects_too_few_samples() -> None:
    with pytest.raises(ValueError, match="n_samples"):
        generate_cpcv_paths(
            n_samples=20,
            n_groups=10,
            test_group_count=2,
            embargo_days=5,
            label_horizon=1,
        )


def test_sample_appears_in_test_c_n_minus_1_k_minus_1_times() -> None:
    n_samples, n_groups, k = 1000, 10, 2
    paths = generate_cpcv_paths(
        n_samples=n_samples,
        n_groups=n_groups,
        test_group_count=k,
        embargo_days=5,
        label_horizon=1,
    )
    expected = math.comb(n_groups - 1, k - 1)  # 9
    counts: dict[int, int] = {idx: 0 for idx in range(n_samples)}
    for _train, test in paths:
        for idx in test:
            counts[idx] += 1
    # Every sample appears in test set exactly `expected` times.
    assert all(count == expected for count in counts.values())


def test_lexicographic_path_order() -> None:
    # Paths MUST be returned in itertools.combinations order:
    # (0,1), (0,2), ..., (n-2, n-1). Test by spot-checking
    # first and last test-group tuples.
    paths = generate_cpcv_paths(
        n_samples=1000,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
    )
    # The first path's test set corresponds to groups (0, 1).
    # The last path's test set corresponds to groups (8, 9).
    first_test = paths[0][1]
    last_test = paths[-1][1]
    fold_size = 1000 // 10
    assert first_test[0] == 0
    assert first_test[-1] == 2 * fold_size - 1
    assert last_test[0] == 8 * fold_size
    assert last_test[-1] == 999  # last group absorbs any remainder
```

- [ ] **Step 2: Run tests to verify they fail**

`uv run pytest tests/unit/test_cpcv_paths.py -v`

Expected: `ImportError` or `AttributeError` for `generate_cpcv_paths`.

- [ ] **Step 3: Implement**

Extend `src/tradingx/validation_folds.py`:

```python
"""Purged/embargoed k-fold and combinatorial purged CV splitters."""

from __future__ import annotations

from itertools import combinations


def purged_kfold_indices(
    *,
    n_samples: int,
    k: int,
    embargo_days: int = 5,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    # ... EXISTING IMPLEMENTATION — DO NOT MODIFY ...
    ...


def generate_cpcv_paths(
    *,
    n_samples: int,
    n_groups: int,
    test_group_count: int,
    embargo_days: int,
    label_horizon: int,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    if n_groups < 4:
        raise ValueError(f"n_groups must be >= 4, got {n_groups}")
    if not (2 <= test_group_count < n_groups):
        raise ValueError(
            f"test_group_count must satisfy 2 <= k < n_groups; "
            f"got {test_group_count} with n_groups={n_groups}"
        )
    if embargo_days < label_horizon:
        raise ValueError(
            f"embargo_days={embargo_days} must be >= "
            f"label_horizon={label_horizon}"
        )
    min_required = n_groups * (2 + label_horizon + embargo_days)
    if n_samples < min_required:
        raise ValueError(
            f"n_samples={n_samples} is too small; need at least "
            f"{min_required} for n_groups={n_groups}, "
            f"label_horizon={label_horizon}, embargo_days={embargo_days}"
        )

    fold_size = n_samples // n_groups
    group_ranges = tuple(
        range(
            idx * fold_size,
            (idx + 1) * fold_size if idx < n_groups - 1 else n_samples,
        )
        for idx in range(n_groups)
    )

    paths: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for test_groups in combinations(range(n_groups), test_group_count):
        test_indices = tuple(
            idx for group in test_groups for idx in group_ranges[group]
        )
        train_indices: list[int] = []
        test_set = set(test_indices)
        embargo_windows = tuple(
            range(
                group_ranges[group].stop,
                min(n_samples, group_ranges[group].stop + embargo_days),
            )
            for group in test_groups
        )
        embargo_set = {idx for window in embargo_windows for idx in window}
        for idx in range(n_samples):
            if idx in test_set or idx in embargo_set:
                continue
            train_indices.append(idx)
        paths.append((tuple(train_indices), test_indices))

    return tuple(paths)


__all__ = ("generate_cpcv_paths", "purged_kfold_indices")
```

Note: purging for multi-bar labels (`label_horizon > 1`) is NOT
implemented in Stage 1 since all shipped sleeves use 1-bar labels.
When a sleeve with `label_horizon > 1` ships, extend the embargo
computation to also purge any training observation whose
forward-looking label window overlaps a test index. Add a
parameter validation check that raises for
`label_horizon > 1` until that extension lands.

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/unit/test_cpcv_paths.py tests/unit/test_validation_folds.py -v`

Both the new CPCV tests and the existing purged-k-fold tests MUST
pass. `validation_folds.py`'s `purged_kfold_indices` behavior is
unchanged.

- [ ] **Step 5: Commit**

```
feat(validation): add generate_cpcv_paths splitter (W1)

Per DESIGN-0018 §W1. Combinatorial purged cross-validation with
the embargo discipline from tranche 1.1. Deterministic path
ordering via itertools.combinations. Rejects k=1 explicitly per
§D2. No change to purged_kfold_indices; both splitters live
alongside during the §W7 transition window.
```

---

## W2 — `CPCVTrialRecord` type and persistence

### Task 2: `CPCVTrialRecord` schema + writer/reader

**Files:**

- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/persistence.py`
- Create: `tests/unit/test_cpcv_trial_record.py`

**Dependencies:** Task 1 (for `generate_cpcv_paths` import in
integration-adjacent tests, but not required for unit tests here).

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_cpcv_trial_record.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import CPCVTrialRecord


def _record(
    *,
    cohort_window_id: str = "cohort-a1b2c3d4e5f60718",
    strategy_config_id: str = "trend-following-v1::cfg-abc123",
    cpcv_path_id: str = "path-0001",
) -> CPCVTrialRecord:
    return CPCVTrialRecord(
        trial_id=f"cpcv-{cohort_window_id}-{strategy_config_id}-{cpcv_path_id}",
        cohort_window_id=cohort_window_id,
        candidate_id="trend-following-v1",
        config_fingerprint="cfg-abc123",
        strategy_config_id=strategy_config_id,
        cpcv_path_id=cpcv_path_id,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        train_indices=(0, 1, 2, 3, 4),
        test_indices=(5, 6, 7, 8, 9),
        in_sample_sharpe=Decimal("1.23"),
        out_of_sample_sharpe=Decimal("0.87"),
        in_sample_n_trades=42,
        out_of_sample_n_trades=9,
        git_sha="0123456789abcdef",
        recorded_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
    )


def test_cpcv_trial_record_is_frozen() -> None:
    import dataclasses

    record = _record()
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.candidate_id = "other"  # type: ignore[misc]


def test_write_and_load_cpcv_trial_record_roundtrip(tmp_path: Path) -> None:
    import json

    store = FilesystemArtifactStore(tmp_path)
    record = _record()
    written_path = store.write_cpcv_trial_record(record)
    assert written_path.exists()
    assert written_path.parent.name == "cpcv_trials"
    expected_filename = (
        f"{record.cohort_window_id}__{record.strategy_config_id}__"
        f"{record.cpcv_path_id}.json"
    )
    assert written_path.name == expected_filename

    payload = json.loads(written_path.read_text(encoding="utf-8"))
    assert payload["trial_id"] == record.trial_id
    assert payload["cohort_window_id"] == record.cohort_window_id
    # Decimal fields round-trip as strings.
    assert Decimal(str(payload["in_sample_sharpe"])) == record.in_sample_sharpe
    assert (
        Decimal(str(payload["out_of_sample_sharpe"]))
        == record.out_of_sample_sharpe
    )


def test_two_records_same_strategy_different_window_do_not_collide(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    record_a = _record(cohort_window_id="cohort-aaaa1111bbbb2222")
    record_b = _record(cohort_window_id="cohort-cccc3333dddd4444")
    path_a = store.write_cpcv_trial_record(record_a)
    path_b = store.write_cpcv_trial_record(record_b)
    assert path_a != path_b
    assert path_a.exists() and path_b.exists()


def test_record_import_comes_from_types_all() -> None:
    from tradingx import types as tradingx_types

    assert "CPCVTrialRecord" in tradingx_types.__all__


# pytest fixture imports pytest at the module level in the real file
import pytest  # noqa: E402
```

- [ ] **Step 2: Run tests to verify they fail**

`uv run pytest tests/unit/test_cpcv_trial_record.py -v`

Expected: `ImportError` for `CPCVTrialRecord` and
`AttributeError` for `write_cpcv_trial_record`.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`, add next to `TrialRecord`:

```python
@dataclass(frozen=True)
class CPCVTrialRecord:
    trial_id: str
    cohort_window_id: str
    candidate_id: str
    config_fingerprint: str
    strategy_config_id: str
    cpcv_path_id: str
    n_groups: int
    test_group_count: int
    embargo_days: int
    label_horizon: int
    window_start_utc: datetime
    window_end_utc: datetime
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    in_sample_sharpe: Decimal
    out_of_sample_sharpe: Decimal
    in_sample_n_trades: int
    out_of_sample_n_trades: int
    git_sha: str
    recorded_at_utc: datetime
```

Add `"CPCVTrialRecord"` to `__all__`.

In `src/tradingx/persistence.py`, next to
`write_sleeve_decomposition_record`:

```python
def write_cpcv_trial_record(
    self,
    record: CPCVTrialRecord,
) -> Path:
    filename = (
        f"{record.cohort_window_id}__{record.strategy_config_id}"
        f"__{record.cpcv_path_id}.json"
    )
    return self._write_json("cpcv_trials", filename, record)


def _deserialize_cpcv_trial_record(
    self,
    payload: dict[str, Any],
) -> CPCVTrialRecord:
    return CPCVTrialRecord(
        trial_id=str(payload["trial_id"]),
        cohort_window_id=str(payload["cohort_window_id"]),
        candidate_id=str(payload["candidate_id"]),
        config_fingerprint=str(payload["config_fingerprint"]),
        strategy_config_id=str(payload["strategy_config_id"]),
        cpcv_path_id=str(payload["cpcv_path_id"]),
        n_groups=int(payload["n_groups"]),
        test_group_count=int(payload["test_group_count"]),
        embargo_days=int(payload["embargo_days"]),
        label_horizon=int(payload["label_horizon"]),
        window_start_utc=datetime.fromisoformat(
            str(payload["window_start_utc"])
        ),
        window_end_utc=datetime.fromisoformat(str(payload["window_end_utc"])),
        train_indices=tuple(int(idx) for idx in payload["train_indices"]),
        test_indices=tuple(int(idx) for idx in payload["test_indices"]),
        in_sample_sharpe=Decimal(str(payload["in_sample_sharpe"])),
        out_of_sample_sharpe=Decimal(str(payload["out_of_sample_sharpe"])),
        in_sample_n_trades=int(payload["in_sample_n_trades"]),
        out_of_sample_n_trades=int(payload["out_of_sample_n_trades"]),
        git_sha=str(payload["git_sha"]),
        recorded_at_utc=datetime.fromisoformat(str(payload["recorded_at_utc"])),
    )
```

Update the `from tradingx.types import (...)` block at the top of
`persistence.py` to include `CPCVTrialRecord`.

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/unit/test_cpcv_trial_record.py -v`

All four tests pass.

- [ ] **Step 5: Commit**

```
feat(types,persistence): add CPCVTrialRecord schema + writer (W2)

Per DESIGN-0018 §W2. Cohort-window-prefixed filename avoids the
cross-evaluation collision flagged in review round 3.
Strategy_config_id composite key keeps parameter sweeps distinct.
```

---

## W4 — `PBOReport` and `CPCVCohortWindowSummary`

### Task 3: `PBOReport` + `CPCVCohortWindowSummary` dataclasses + PBOReport persistence

**Files:**

- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/persistence.py`
- Create: `tests/unit/test_pbo_report.py`

**Dependencies:** Task 2 (for the typing conventions; no hard code
dep).

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_pbo_report.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import CPCVCohortWindowSummary, PBOReport


def _report() -> PBOReport:
    return PBOReport(
        report_id="pbo-eval-abc123",
        evaluation_id="eval-abc123",
        cohort_window_id="cohort-a1b2c3d4e5f60718",
        cohort_size=55,
        n_paths=45,
        n_splits_sampled=10_000,
        pbo_value=Decimal("0.18"),
        logit_distribution_percentiles=(
            (Decimal("5"), Decimal("-2.1")),
            (Decimal("25"), Decimal("-0.8")),
            (Decimal("50"), Decimal("0.3")),
            (Decimal("75"), Decimal("1.4")),
            (Decimal("95"), Decimal("3.2")),
        ),
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
        metric_name="lo_adjusted_sharpe",
        random_seed=2026,
        generated_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
    )


def test_pbo_report_is_frozen() -> None:
    import dataclasses

    report = _report()
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.pbo_value = Decimal("0.50")  # type: ignore[misc]


def test_write_and_load_pbo_report_roundtrip(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    report = _report()
    written_path = store.write_pbo_report(report)
    loaded = store.load_pbo_report_by_evaluation_id(
        evaluation_id=report.evaluation_id
    )
    assert loaded is not None
    assert loaded == report
    assert written_path.parent.name == "pbo_reports"


def test_load_pbo_report_returns_none_when_missing(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    assert store.load_pbo_report_by_evaluation_id(evaluation_id="nope") is None


def test_cpcv_cohort_window_summary_is_frozen() -> None:
    import dataclasses

    summary = CPCVCohortWindowSummary(
        cohort_window_id="cohort-test",
        cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        earliest_recorded_at_utc=datetime(2026, 4, 22, 10, 0, tzinfo=UTC),
        latest_recorded_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
        record_count=45,
        strategy_config_count=1,
        path_count=45,
        git_shas=frozenset({"abc123"}),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.record_count = 0  # type: ignore[misc]


def test_types_all_exports_both() -> None:
    from tradingx import types as tradingx_types

    assert "PBOReport" in tradingx_types.__all__
    assert "CPCVCohortWindowSummary" in tradingx_types.__all__
```

- [ ] **Step 2: Run tests to verify they fail**

`uv run pytest tests/unit/test_pbo_report.py -v`

Expected: `ImportError` for `PBOReport` and
`CPCVCohortWindowSummary`.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`:

```python
@dataclass(frozen=True)
class PBOReport:
    report_id: str
    evaluation_id: str
    cohort_window_id: str
    cohort_size: int
    n_paths: int
    n_splits_sampled: int
    pbo_value: Decimal
    logit_distribution_percentiles: tuple[tuple[Decimal, Decimal], ...]
    cpcv_config_fingerprint: str
    metric_name: str
    random_seed: int
    generated_at_utc: datetime


@dataclass(frozen=True)
class CPCVCohortWindowSummary:
    cohort_window_id: str
    cpcv_config_fingerprint: str
    window_start_utc: datetime
    window_end_utc: datetime
    earliest_recorded_at_utc: datetime
    latest_recorded_at_utc: datetime
    record_count: int
    strategy_config_count: int
    path_count: int
    git_shas: frozenset[str]
```

Add `"PBOReport"` and `"CPCVCohortWindowSummary"` to `__all__`.

In `src/tradingx/persistence.py`:

```python
def write_pbo_report(self, report: PBOReport) -> Path:
    return self._write_json("pbo_reports", f"{report.report_id}.json", report)


def load_pbo_report_by_evaluation_id(
    self,
    *,
    evaluation_id: str,
) -> PBOReport | None:
    category_dir = self._root_dir / "pbo_reports"
    if not category_dir.exists():
        return None
    for path in sorted(category_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("evaluation_id") == evaluation_id:
            return self._deserialize_pbo_report(payload)
    return None


def _deserialize_pbo_report(
    self,
    payload: dict[str, Any],
) -> PBOReport:
    return PBOReport(
        report_id=str(payload["report_id"]),
        evaluation_id=str(payload["evaluation_id"]),
        cohort_window_id=str(payload["cohort_window_id"]),
        cohort_size=int(payload["cohort_size"]),
        n_paths=int(payload["n_paths"]),
        n_splits_sampled=int(payload["n_splits_sampled"]),
        pbo_value=Decimal(str(payload["pbo_value"])),
        logit_distribution_percentiles=tuple(
            (Decimal(str(pair[0])), Decimal(str(pair[1])))
            for pair in payload["logit_distribution_percentiles"]
        ),
        cpcv_config_fingerprint=str(payload["cpcv_config_fingerprint"]),
        metric_name=str(payload["metric_name"]),
        random_seed=int(payload["random_seed"]),
        generated_at_utc=datetime.fromisoformat(
            str(payload["generated_at_utc"])
        ),
    )
```

The `frozenset[str]` field on `CPCVCohortWindowSummary` is
in-memory only (the summary is not persisted). No serializer
required.

Update the top-of-file `from tradingx.types import (...)` block to
include `PBOReport` and `CPCVCohortWindowSummary`.

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/unit/test_pbo_report.py -v`

- [ ] **Step 5: Commit**

```
feat(types,persistence): add PBOReport + CPCVCohortWindowSummary (W4)

Per DESIGN-0018 §W4. PBOReport persists to pbo_reports/ by
report_id. CPCVCohortWindowSummary is derived only (returned by
list_cpcv_cohort_windows in W8) — no writer.
```

---

## W8 — Cohort queries

### Task 4: `list_cpcv_trial_records` + `list_cpcv_cohort_windows`

**Files:**

- Modify: `src/tradingx/persistence.py`
- Create: `tests/unit/test_cpcv_cohort_queries.py`

**Dependencies:** Task 2 (CPCVTrialRecord + writer), Task 3
(CPCVCohortWindowSummary type).

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_cpcv_cohort_queries.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import CPCVTrialRecord


def _record(
    *,
    cohort_window_id: str,
    strategy_config_id: str,
    cpcv_path_id: str,
    recorded_at_utc: datetime,
    git_sha: str = "abc123",
) -> CPCVTrialRecord:
    # Fill the remainder with deterministic placeholder values.
    candidate_id, _, config_fingerprint = strategy_config_id.partition("::")
    return CPCVTrialRecord(
        trial_id=f"cpcv-{cohort_window_id}-{strategy_config_id}-{cpcv_path_id}",
        cohort_window_id=cohort_window_id,
        candidate_id=candidate_id,
        config_fingerprint=config_fingerprint,
        strategy_config_id=strategy_config_id,
        cpcv_path_id=cpcv_path_id,
        n_groups=10,
        test_group_count=2,
        embargo_days=5,
        label_horizon=1,
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        train_indices=(0, 1, 2),
        test_indices=(3, 4, 5),
        in_sample_sharpe=Decimal("1.0"),
        out_of_sample_sharpe=Decimal("0.8"),
        in_sample_n_trades=10,
        out_of_sample_n_trades=3,
        git_sha=git_sha,
        recorded_at_utc=recorded_at_utc,
    )


def test_list_cpcv_trial_records_filters_to_cohort_window(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    now = datetime(2026, 4, 22, 13, 0, tzinfo=UTC)
    for cohort in ("cohort-aaaa", "cohort-bbbb"):
        for path_idx in range(2):
            store.write_cpcv_trial_record(
                _record(
                    cohort_window_id=cohort,
                    strategy_config_id="trend::cfg1",
                    cpcv_path_id=f"path-{path_idx}",
                    recorded_at_utc=now,
                )
            )

    records = store.list_cpcv_trial_records(cohort_window_id="cohort-aaaa")
    assert len(records) == 2
    assert all(rec.cohort_window_id == "cohort-aaaa" for rec in records)


def test_list_cpcv_cohort_windows_aggregates_metadata(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path)
    earliest = datetime(2026, 4, 22, 10, 0, tzinfo=UTC)
    latest = datetime(2026, 4, 22, 13, 0, tzinfo=UTC)
    for strategy in ("trend::cfg1", "trend::cfg2", "vol::cfg1"):
        for path_idx in range(3):
            store.write_cpcv_trial_record(
                _record(
                    cohort_window_id="cohort-one",
                    strategy_config_id=strategy,
                    cpcv_path_id=f"path-{path_idx}",
                    recorded_at_utc=earliest if path_idx == 0 else latest,
                    git_sha="abc123" if strategy != "vol::cfg1" else "def456",
                )
            )
    store.write_cpcv_trial_record(
        _record(
            cohort_window_id="cohort-two",
            strategy_config_id="trend::cfg1",
            cpcv_path_id="path-0",
            recorded_at_utc=latest,
        )
    )

    summaries = store.list_cpcv_cohort_windows()

    assert len(summaries) == 2
    by_id = {s.cohort_window_id: s for s in summaries}
    one = by_id["cohort-one"]
    assert one.record_count == 9
    assert one.strategy_config_count == 3
    assert one.path_count == 3
    assert one.earliest_recorded_at_utc == earliest
    assert one.latest_recorded_at_utc == latest
    assert one.git_shas == frozenset({"abc123", "def456"})
    two = by_id["cohort-two"]
    assert two.record_count == 1


def test_list_cpcv_cohort_windows_orders_by_earliest_ascending(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    store.write_cpcv_trial_record(
        _record(
            cohort_window_id="cohort-new",
            strategy_config_id="trend::cfg1",
            cpcv_path_id="path-0",
            recorded_at_utc=datetime(2026, 6, 1, tzinfo=UTC),
        )
    )
    store.write_cpcv_trial_record(
        _record(
            cohort_window_id="cohort-old",
            strategy_config_id="trend::cfg1",
            cpcv_path_id="path-0",
            recorded_at_utc=datetime(2025, 10, 1, tzinfo=UTC),
        )
    )

    summaries = store.list_cpcv_cohort_windows()

    assert summaries[0].cohort_window_id == "cohort-old"
    assert summaries[1].cohort_window_id == "cohort-new"


def test_list_cpcv_cohort_windows_empty_store_returns_empty(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    assert store.list_cpcv_cohort_windows() == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: `AttributeError` on both methods.

- [ ] **Step 3: Implement**

In `src/tradingx/persistence.py`:

```python
def list_cpcv_trial_records(
    self,
    *,
    cohort_window_id: str,
) -> tuple[CPCVTrialRecord, ...]:
    category_dir = self._root_dir / "cpcv_trials"
    if not category_dir.exists():
        return ()
    records: list[CPCVTrialRecord] = []
    for path in sorted(category_dir.glob(f"{cohort_window_id}__*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.append(self._deserialize_cpcv_trial_record(payload))
    return tuple(records)


def list_cpcv_cohort_windows(
    self,
) -> tuple[CPCVCohortWindowSummary, ...]:
    category_dir = self._root_dir / "cpcv_trials"
    if not category_dir.exists():
        return ()
    by_cohort: dict[str, list[CPCVTrialRecord]] = {}
    for path in sorted(category_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = self._deserialize_cpcv_trial_record(payload)
        by_cohort.setdefault(record.cohort_window_id, []).append(record)

    summaries = tuple(
        CPCVCohortWindowSummary(
            cohort_window_id=cohort_id,
            cpcv_config_fingerprint=(
                f"N={records[0].n_groups},"
                f"k={records[0].test_group_count},"
                f"h={records[0].embargo_days},"
                f"L={records[0].label_horizon}"
            ),
            window_start_utc=records[0].window_start_utc,
            window_end_utc=records[0].window_end_utc,
            earliest_recorded_at_utc=min(r.recorded_at_utc for r in records),
            latest_recorded_at_utc=max(r.recorded_at_utc for r in records),
            record_count=len(records),
            strategy_config_count=len(
                {r.strategy_config_id for r in records}
            ),
            path_count=len({r.cpcv_path_id for r in records}),
            git_shas=frozenset(r.git_sha for r in records),
        )
        for cohort_id, records in by_cohort.items()
    )
    return tuple(
        sorted(summaries, key=lambda s: s.earliest_recorded_at_utc)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/unit/test_cpcv_cohort_queries.py -v`

- [ ] **Step 5: Commit**

```
feat(persistence): add CPCV cohort queries (W8)

Per DESIGN-0018 §W8. list_cpcv_trial_records uses the
cohort_window_id filename prefix for glob-efficient filtering.
list_cpcv_cohort_windows returns aggregated summaries sorted by
earliest_recorded_at_utc — ready for §P4 gate 3 composition.
```

---

## W3 — `compute_pbo`

### Task 5: PBO computation module

**Files:**

- Create: `src/tradingx/pbo.py`
- Create: `tests/unit/test_pbo_compute.py`

**Dependencies:** Tasks 2, 3, 4 (records, types, queries).

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_pbo_compute.py`:

```python
from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradingx.pbo import (
    InsufficientCPCVCohortError,
    MixedCohortWindowError,
    compute_pbo,
)
from tradingx.types import CPCVTrialRecord


def _make_records(
    *,
    cohort_window_id: str,
    n_paths: int,
    strategy_ids: tuple[str, ...],
    oos_sharpe_by_strategy_path: dict[tuple[str, int], Decimal],
    is_sharpe_default: Decimal = Decimal("0.0"),
) -> tuple[CPCVTrialRecord, ...]:
    records: list[CPCVTrialRecord] = []
    for strategy in strategy_ids:
        candidate_id, _, config_fingerprint = strategy.partition("::")
        for path_idx in range(n_paths):
            records.append(
                CPCVTrialRecord(
                    trial_id=f"cpcv-{cohort_window_id}-{strategy}-path-{path_idx}",
                    cohort_window_id=cohort_window_id,
                    candidate_id=candidate_id,
                    config_fingerprint=config_fingerprint,
                    strategy_config_id=strategy,
                    cpcv_path_id=f"path-{path_idx:04d}",
                    n_groups=10,
                    test_group_count=2,
                    embargo_days=5,
                    label_horizon=1,
                    window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
                    window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
                    train_indices=(0, 1),
                    test_indices=(2, 3),
                    in_sample_sharpe=is_sharpe_default,
                    out_of_sample_sharpe=oos_sharpe_by_strategy_path[
                        (strategy, path_idx)
                    ],
                    in_sample_n_trades=1,
                    out_of_sample_n_trades=1,
                    git_sha="abc123",
                    recorded_at_utc=datetime(2026, 4, 22, 13, 0, tzinfo=UTC),
                )
            )
    return tuple(records)


def test_iid_noise_cohort_gives_pbo_around_half() -> None:
    import random

    rng = random.Random(2026)
    n_paths = 45
    strategies = tuple(f"cand::cfg{idx}" for idx in range(60))
    cells: dict[tuple[str, int], Decimal] = {
        (s, p): Decimal(str(rng.gauss(0.0, 1.0)))
        for s in strategies
        for p in range(n_paths)
    }
    records = _make_records(
        cohort_window_id="cohort-iid",
        n_paths=n_paths,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path=cells,
    )
    report = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )
    # Null hypothesis: IS rank uninformative about OOS rank.
    # Expect PBO ≈ 0.5 with ±0.10 tolerance on 10_000 samples.
    assert Decimal("0.40") <= report.pbo_value <= Decimal("0.60")


def test_dominant_strategy_cohort_gives_pbo_near_zero() -> None:
    n_paths = 45
    strategies = tuple(f"cand::cfg{idx}" for idx in range(60))
    cells: dict[tuple[str, int], Decimal] = {
        # One strategy strictly dominates on every path.
        ("cand::cfg0", p): Decimal("5.0") for p in range(n_paths)
    }
    for idx in range(1, 60):
        for p in range(n_paths):
            cells[(f"cand::cfg{idx}", p)] = Decimal("0.0")
    records = _make_records(
        cohort_window_id="cohort-dominant",
        n_paths=n_paths,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path=cells,
    )
    report = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )
    assert report.pbo_value <= Decimal("0.05")


def test_lucky_winner_cohort_gives_pbo_near_one() -> None:
    # One strategy has huge IS outlier but no OOS persistence.
    # Construct: pick a subset of paths as "IS paths" and place the
    # outlier there; zero everywhere else.
    import random

    rng = random.Random(4242)
    n_paths = 45
    strategies = tuple(f"cand::cfg{idx}" for idx in range(60))
    cells: dict[tuple[str, int], Decimal] = {}
    is_paths = set(rng.sample(range(n_paths), n_paths // 2))
    for idx, strategy in enumerate(strategies):
        for p in range(n_paths):
            if idx == 0 and p in is_paths:
                cells[(strategy, p)] = Decimal("10.0")
            elif idx == 0:
                cells[(strategy, p)] = Decimal("-5.0")
            else:
                cells[(strategy, p)] = Decimal(str(rng.gauss(0.0, 1.0)))
    records = _make_records(
        cohort_window_id="cohort-lucky",
        n_paths=n_paths,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path=cells,
    )
    report = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )
    # Lucky-winner cohort should give PBO close to 1.0 (IS winner
    # becomes OOS loser systematically).
    assert report.pbo_value >= Decimal("0.70")


def test_same_seed_gives_same_pbo_value() -> None:
    import random

    rng = random.Random(999)
    n_paths = 45
    strategies = tuple(f"cand::cfg{idx}" for idx in range(60))
    cells = {
        (s, p): Decimal(str(rng.gauss(0.0, 1.0)))
        for s in strategies
        for p in range(n_paths)
    }
    records = _make_records(
        cohort_window_id="cohort-seed",
        n_paths=n_paths,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path=cells,
    )
    report_a = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )
    report_b = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )
    assert report_a.pbo_value == report_b.pbo_value


def test_mixed_cohort_window_raises() -> None:
    mixed = (
        *_make_records(
            cohort_window_id="cohort-a",
            n_paths=45,
            strategy_ids=("cand::cfg1",) * 1,
            oos_sharpe_by_strategy_path={
                ("cand::cfg1", p): Decimal("0.0") for p in range(45)
            },
        ),
        *_make_records(
            cohort_window_id="cohort-b",
            n_paths=45,
            strategy_ids=("cand::cfg1",),
            oos_sharpe_by_strategy_path={
                ("cand::cfg1", p): Decimal("0.0") for p in range(45)
            },
        ),
    )
    with pytest.raises(MixedCohortWindowError):
        compute_pbo(
            cpcv_records=mixed,
            min_cohort_size=1,
            min_paths=20,
            random_seed=2026,
        )


def test_insufficient_cohort_raises() -> None:
    strategies = tuple(f"cand::cfg{idx}" for idx in range(10))
    records = _make_records(
        cohort_window_id="cohort-small",
        n_paths=45,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path={
            (s, p): Decimal("0.0") for s in strategies for p in range(45)
        },
    )
    with pytest.raises(InsufficientCPCVCohortError):
        compute_pbo(
            cpcv_records=records,
            min_cohort_size=50,
            min_paths=20,
            random_seed=2026,
        )


def test_report_fields_populated(tmp_path) -> None:
    strategies = tuple(f"cand::cfg{idx}" for idx in range(60))
    n_paths = 45
    import random

    rng = random.Random(7)
    records = _make_records(
        cohort_window_id="cohort-fields",
        n_paths=n_paths,
        strategy_ids=strategies,
        oos_sharpe_by_strategy_path={
            (s, p): Decimal(str(rng.gauss(0.0, 1.0)))
            for s in strategies
            for p in range(n_paths)
        },
    )
    report = compute_pbo(
        cpcv_records=records,
        min_cohort_size=50,
        min_paths=20,
        random_seed=2026,
    )
    assert report.cohort_window_id == "cohort-fields"
    assert report.cohort_size == 60
    assert report.n_paths == 45
    assert report.n_splits_sampled == 10_000
    assert report.metric_name == "lo_adjusted_sharpe"
    assert report.random_seed == 2026
    assert report.cpcv_config_fingerprint == "N=10,k=2,h=5,L=1"
    # Percentiles at 5/25/50/75/95 present.
    percentiles = [
        float(p) for p, _ in report.logit_distribution_percentiles
    ]
    assert percentiles == [5.0, 25.0, 50.0, 75.0, 95.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: `ModuleNotFoundError` for `tradingx.pbo`.

- [ ] **Step 3: Implement**

Create `src/tradingx/pbo.py`:

```python
"""Probability-of-backtest-overfitting computation (DESIGN-0018)."""

from __future__ import annotations

import hashlib
import math
import random
import statistics
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.types import CPCVTrialRecord, PBOReport


class InsufficientCPCVCohortError(ValueError):
    """Cohort or path count below BBLZ reliability threshold."""


class MixedCohortWindowError(ValueError):
    """cpcv_records contains records from more than one
    cohort_window_id; PBO requires a single coherent matrix."""


DEFAULT_MIN_COHORT_SIZE = 50
DEFAULT_MIN_PATHS = 20
DEFAULT_RANDOM_SEED = 2026
DEFAULT_N_SPLITS = 10_000
_METRIC_NAME = "lo_adjusted_sharpe"
_PERCENTILES = (Decimal("5"), Decimal("25"), Decimal("50"), Decimal("75"), Decimal("95"))


def compute_pbo(
    *,
    cpcv_records: tuple[CPCVTrialRecord, ...],
    min_cohort_size: int = DEFAULT_MIN_COHORT_SIZE,
    min_paths: int = DEFAULT_MIN_PATHS,
    random_seed: int = DEFAULT_RANDOM_SEED,
    evaluation_id: str | None = None,
    generated_at_utc: datetime | None = None,
) -> PBOReport:
    if not cpcv_records:
        raise InsufficientCPCVCohortError("cpcv_records is empty")
    cohort_window_ids = {r.cohort_window_id for r in cpcv_records}
    if len(cohort_window_ids) > 1:
        raise MixedCohortWindowError(
            f"cpcv_records span {len(cohort_window_ids)} cohort windows: "
            f"{sorted(cohort_window_ids)!r}"
        )
    cohort_window_id = next(iter(cohort_window_ids))

    strategies = sorted({r.strategy_config_id for r in cpcv_records})
    paths = sorted({r.cpcv_path_id for r in cpcv_records})
    n_strategies = len(strategies)
    n_paths = len(paths)

    if n_strategies < min_cohort_size:
        raise InsufficientCPCVCohortError(
            f"cohort_size={n_strategies} < min_cohort_size={min_cohort_size}"
        )
    if n_paths < min_paths:
        raise InsufficientCPCVCohortError(
            f"n_paths={n_paths} < min_paths={min_paths}"
        )

    matrix: dict[tuple[str, str], Decimal] = {
        (r.cpcv_path_id, r.strategy_config_id): r.out_of_sample_sharpe
        for r in cpcv_records
    }
    for path in paths:
        for strategy in strategies:
            if (path, strategy) not in matrix:
                raise InsufficientCPCVCohortError(
                    f"missing cell at (cpcv_path_id={path}, "
                    f"strategy_config_id={strategy})"
                )

    rng = random.Random(random_seed)
    is_size = n_paths // 2
    logits: list[float] = []
    clamp_low = 1.0 / (n_strategies + 1)
    clamp_high = n_strategies / (n_strategies + 1)

    for _ in range(DEFAULT_N_SPLITS):
        is_paths = frozenset(rng.sample(paths, is_size))
        # r̄_IS[s], r̄_OOS[s].
        is_means: dict[str, float] = {}
        oos_means: dict[str, float] = {}
        for strategy in strategies:
            is_values = [
                float(matrix[(p, strategy)]) for p in paths if p in is_paths
            ]
            oos_values = [
                float(matrix[(p, strategy)]) for p in paths if p not in is_paths
            ]
            is_means[strategy] = statistics.fmean(is_values)
            oos_means[strategy] = statistics.fmean(oos_values)
        n_star = max(is_means, key=lambda s: is_means[s])
        oos_value_of_winner = oos_means[n_star]
        # Fractional (average-rank) rank of the winner among OOS means.
        sorted_oos = sorted(oos_means.values())
        rank = (
            sum(1 for v in sorted_oos if v < oos_value_of_winner)
            + 0.5
            * sum(1 for v in sorted_oos if v == oos_value_of_winner)
            + 0.5
        ) / n_strategies
        rank = max(min(rank, clamp_high), clamp_low)
        logits.append(math.log(rank / (1.0 - rank)))

    pbo_value = Decimal(str(sum(1 for x in logits if x <= 0.0) / len(logits)))
    logits_sorted = sorted(logits)

    def _percentile(pct: Decimal) -> Decimal:
        rank_f = (float(pct) / 100.0) * (len(logits_sorted) - 1)
        lower = int(math.floor(rank_f))
        upper = int(math.ceil(rank_f))
        if lower == upper:
            return Decimal(str(logits_sorted[lower]))
        frac = rank_f - lower
        return Decimal(
            str(logits_sorted[lower] * (1 - frac) + logits_sorted[upper] * frac)
        )

    percentiles = tuple((p, _percentile(p)) for p in _PERCENTILES)

    sample_record = cpcv_records[0]
    fingerprint = (
        f"N={sample_record.n_groups},"
        f"k={sample_record.test_group_count},"
        f"h={sample_record.embargo_days},"
        f"L={sample_record.label_horizon}"
    )
    eval_id = evaluation_id or f"eval-{uuid.uuid4()}"
    now = generated_at_utc or datetime.now(UTC)

    return PBOReport(
        report_id=f"pbo-{eval_id}",
        evaluation_id=eval_id,
        cohort_window_id=cohort_window_id,
        cohort_size=n_strategies,
        n_paths=n_paths,
        n_splits_sampled=DEFAULT_N_SPLITS,
        pbo_value=pbo_value,
        logit_distribution_percentiles=percentiles,
        cpcv_config_fingerprint=fingerprint,
        metric_name=_METRIC_NAME,
        random_seed=random_seed,
        generated_at_utc=now,
    )


def cohort_window_id_for(
    *,
    window_start_utc: datetime,
    window_end_utc: datetime,
    cpcv_config_fingerprint: str,
) -> str:
    """Compute the deterministic cohort_window_id per DESIGN-0018 §W2."""
    payload = (
        f"{window_start_utc.isoformat()}"
        f"|{window_end_utc.isoformat()}"
        f"|{cpcv_config_fingerprint}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"cohort-{digest[:16]}"


__all__ = (
    "DEFAULT_MIN_COHORT_SIZE",
    "DEFAULT_MIN_PATHS",
    "DEFAULT_N_SPLITS",
    "DEFAULT_RANDOM_SEED",
    "InsufficientCPCVCohortError",
    "MixedCohortWindowError",
    "cohort_window_id_for",
    "compute_pbo",
)
```

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/unit/test_pbo_compute.py -v`

Expected: all tests pass. The stochastic bounds (IID → ≈ 0.5,
dominant → ≤ 0.05, lucky → ≥ 0.70) use the fixed
`random_seed=2026` so they're deterministic across runs.

- [ ] **Step 5: Commit**

```
feat(pbo): add compute_pbo and cohort_window_id_for (W3)

Per DESIGN-0018 §W3. Monte Carlo over 10_000 splits with fixed
seed 2026 (§P3 determinism). Rejects mixed-cohort inputs;
enforces min_cohort_size / min_paths. Includes cohort_window_id_for
helper for §W2 deterministic-hash callers.
```

---

## W5 — `EvaluationEvidencePack` schema extension

### Task 6: Add `pbo_value` + `pbo_report_id` fields

**Files:**

- Modify: `src/tradingx/types.py`
- Modify: `src/tradingx/persistence.py` (if serialization needs
  updating; confirm at implementation time by reading the
  existing write/read path for `EvaluationEvidencePack`).
- Create: `tests/unit/test_evaluation_evidence_pbo_fields.py`

**Dependencies:** Task 3 (`PBOReport` type for reference).

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_evaluation_evidence_pbo_fields.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradingx.types import EvaluationEvidencePack


def _minimal_pack(**overrides) -> EvaluationEvidencePack:
    base = dict(
        evidence_pack_id="pack-1",
        candidate_id="trend-following-v1",
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="pass",
        assumptions=(),
    )
    base.update(overrides)
    return EvaluationEvidencePack(**base)  # type: ignore[arg-type]


def test_pbo_fields_default_to_none() -> None:
    pack = _minimal_pack()
    assert pack.pbo_value is None
    assert pack.pbo_report_id is None


def test_pbo_fields_accept_values_when_provided() -> None:
    pack = _minimal_pack(
        pbo_value=Decimal("0.18"),
        pbo_report_id="pbo-eval-abc123",
    )
    assert pack.pbo_value == Decimal("0.18")
    assert pack.pbo_report_id == "pbo-eval-abc123"


def test_pre_cpcv_pack_deserializes_without_migration() -> None:
    # Construct a dict without the pbo_* keys to simulate an old
    # persisted pack; ensure EvaluationEvidencePack(**...) accepts it
    # via the None defaults.
    payload_without_pbo = dict(
        evidence_pack_id="pack-legacy",
        candidate_id="trend-following-v1",
        window_start_utc=datetime(2016, 4, 22, tzinfo=UTC),
        window_end_utc=datetime(2026, 4, 22, tzinfo=UTC),
        benchmark_metrics={},
        candidate_metrics={},
        adversarial_checks=(),
        recommendation="pass",
        assumptions=(),
    )
    pack = EvaluationEvidencePack(**payload_without_pbo)
    assert pack.pbo_value is None
    assert pack.pbo_report_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: `TypeError: got an unexpected keyword argument 'pbo_value'`
on the second test.

- [ ] **Step 3: Implement**

In `src/tradingx/types.py`, extend `EvaluationEvidencePack`:

```python
@dataclass(frozen=True)
class EvaluationEvidencePack:
    # ... existing fields unchanged ...
    pbo_value: Decimal | None = None
    pbo_report_id: str | None = None
```

If `persistence.py` has an `EvaluationEvidencePack` serializer,
update its reader to `payload.get("pbo_value")` and
`payload.get("pbo_report_id")` with None fallback. Verify during
implementation by grepping:
`grep -n "EvaluationEvidencePack" src/tradingx/persistence.py`.

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```
feat(types): add pbo_value + pbo_report_id to EvaluationEvidencePack (W5)

Per DESIGN-0018 §W5. Nullable fields with None defaults preserve
deserialization of pre-CPCV evidence packs (§P5 audit link).
```

---

## W7 + CPCV orchestration at the validation-controller layer

### Task 7: Wire CPCV into the Gate 1 pipeline (helper in validation.py, orchestration in controller.py)

**Files:**

- Modify: `src/tradingx/validation.py` — add stateless helper
  `_run_cpcv_for_candidate`.
- Modify: `src/tradingx/controller.py` — insert the CPCV
  invocation loop in `GateValidationController.generate_gate_report`
  between the bars construction and the `build_gate_report` call.
- Create: `tests/unit/test_validation_cpcv_orchestration.py` —
  unit tests for the helper.
- Create: `tests/unit/test_controller_generate_gate_report_cpcv.py`
  — unit tests for the controller's CPCV loop (mocked
  dependencies; verifies the helper is called once per eligible
  candidate with the expected kwargs, and that the existing
  `build_gate_report` path is unaffected).

**Dependencies:** Tasks 1–6.

**Architecture note:** CPCV orchestration lives at the
**controller layer**, not inside
[`build_gate_report`](/src/tradingx/validation.py:778).
Rationale (from Codex round-2 P1 on this plan):
`build_gate_report(gate_id, bars_by_symbol, candidates,
benchmark_stack_payload, window_start_utc, window_end_utc,
trials_ledger)` takes no artifact store and modifying its
signature cascades to every caller including tests.
[`GateValidationController.generate_gate_report`](/src/tradingx/controller.py:1464)
already has `self._artifacts` (the validation
`FilesystemArtifactStore`), builds `bars_by_symbol` from
`self._market_data`, and is the single production call site for
`build_gate_report`. CPCV invocation inserts there; the utility
`_run_cpcv_for_candidate` lives in `validation.py` beside other
validation helpers but is imported and called from
`controller.py`.

**Stage 1 behavior target (per DESIGN-0018 §D7):**

The helper persists `CPCVTrialRecord`s but **does not** invoke
`compute_pbo`. The evidence pack's `pbo_value` + `pbo_report_id`
stay `None` throughout Stage 1. Stage 2 (Task 10) is the commit
that starts invoking `compute_pbo` and populating those fields.

Concretely:

- **Helper (`validation.py::_run_cpcv_for_candidate`):** for a
  single eligible candidate, it
  1. Computes `cohort_window_id` via
     `pbo.cohort_window_id_for(window_start_utc=...,
     window_end_utc=..., cpcv_config_fingerprint="N=10,k=2,h=5,L=1")`.
  2. Generates the 45 paths via
     `generate_cpcv_paths(n_samples=len(bars.index), n_groups=10,
     test_group_count=2, embargo_days=5, label_horizon=1)`.
     `label_horizon` is a fixed module constant (see eligibility
     below); `StrategyCandidate` is NOT modified in Stage 1.
  3. For each of the 45 paths, runs two backtests against the
     candidate's sleeve using the existing backtest seam (confirm
     the exact helper at implementation time by grepping
     `run_daily_bar_backtest` in `src/tradingx/backtest.py`):
     one on the training-index slice of `bars_by_symbol`, one on
     the test-index slice. Compute Lo-adjusted Sharpe on each
     (§P2) and trade counts.
  4. Builds a `CPCVTrialRecord` per path and persists via
     `artifact_store.write_cpcv_trial_record`.
  5. Returns the tuple of persisted records (or `()` if the
     candidate was ineligible or history was insufficient).
- **Orchestration (`controller.py::GateValidationController.generate_gate_report`):**
  between lines [1484](/src/tradingx/controller.py:1484)
  (bars constructed) and [1485](/src/tradingx/controller.py:1485)
  (`build_gate_report` call), add:

  ```python
  from tradingx.validation import _run_cpcv_for_candidate

  if gate_id == "1":
      for candidate in candidates:
          _run_cpcv_for_candidate(
              candidate=candidate,
              bars_by_symbol=bars_by_symbol,
              window_start_utc=window_start_utc,
              window_end_utc=window_end_utc,
              artifact_store=self._artifacts,
          )
  ```

  Stage 1 discards the return value — the persistence is the
  side effect and `build_gate_report`'s result is still the sole
  input to the `ValidationReport`. The CPCV loop runs only for
  `gate_id == "1"` since CPCV feeds only Gate 1 criterion 7.
  Non-sleeve candidates short-circuit inside the helper.

- Do **not** call `compute_pbo` from either site in Stage 1.
- Do **not** populate `pbo_value` / `pbo_report_id` on any
  evidence pack — Stage 1 leaves them `None` by construction.
- Do **not** modify `build_gate_report`'s signature. Do **not**
  touch `purged_kfold_indices` or any of its existing call sites
  — §W7 transition window keeps both splitters alive.

**Eligibility (Stage 1):** the helper is invoked only when
`candidate.sleeve_class_path is not None`. `label_horizon` is
hardcoded as a module constant `_CPCV_LABEL_HORIZON_DAYS = 1`
(consistent with every shipped sleeve today; `StrategyCandidate`
has no `label_horizon` field and Stage 1 does not add one).
Multi-bar label horizons are out of scope until a sleeve ships
that needs them — at that point, a follow-up tranche will either
add `label_horizon` to `StrategyCandidate` or thread it through a
different surface, and update `generate_cpcv_paths`' purging
accordingly.

If `len(bars.index) < n_groups * (2 + label_horizon + embargo_days)`
(i.e., insufficient history for the splitter), log
`criterion: "cpcv_insufficient_history"` at info level and skip
silently — do not raise; do not write any records.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_validation_cpcv_orchestration.py`. The
tests target a private helper the implementer adds to
`validation.py`. Exact helper name is at the implementer's
discretion; tests access it via
`from tradingx.validation import _run_cpcv_for_candidate`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tradingx.persistence import FilesystemArtifactStore
from tradingx.validation import _run_cpcv_for_candidate


def _fixture_bars(
    *, start: datetime, periods: int, symbols: tuple[str, ...]
) -> dict[str, pd.DataFrame]:
    index = pd.date_range(start=start, periods=periods, freq="B", tz="UTC")
    return {
        symbol: pd.DataFrame(
            {
                "open": [100.0 + i * 0.01 for i in range(periods)],
                "high": [100.5 + i * 0.01 for i in range(periods)],
                "low": [99.5 + i * 0.01 for i in range(periods)],
                "close": [100.0 + i * 0.02 for i in range(periods)],
                "volume": [1_000_000] * periods,
            },
            index=index,
        )
        for symbol in symbols
    }


def _fixture_sleeve_candidate():
    # Build via tradingx.strategy.build_mandatory_candidate_registry
    # and pick a sleeve-backed entry (trend-following-v1).
    from tradingx.strategy import build_mandatory_candidate_registry

    registry = build_mandatory_candidate_registry(("SPY", "QQQ"))
    return next(c for c in registry if c.candidate_id == "trend-following-v1")


def test_run_cpcv_for_candidate_writes_exactly_45_records(
    tmp_path: Path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    bars = _fixture_bars(
        start=datetime(2016, 4, 22, tzinfo=UTC),
        periods=260 * 10,  # 10 years of trading days
        symbols=("SPY", "QQQ"),
    )
    records = _run_cpcv_for_candidate(
        candidate=_fixture_sleeve_candidate(),
        bars_by_symbol=bars,
        window_start_utc=min(bars["SPY"].index).to_pydatetime(),
        window_end_utc=max(bars["SPY"].index).to_pydatetime(),
        artifact_store=store,
    )
    assert len(records) == 45
    cpcv_files = list((tmp_path / "cpcv_trials").glob("*.json"))
    assert len(cpcv_files) == 45


def test_run_cpcv_for_candidate_stage_1_returns_records_only(
    tmp_path: Path,
) -> None:
    # Stage 1 invariant: the helper returns the tuple of written
    # records. It does NOT compute PBO, does NOT write a
    # PBOReport, and the caller is responsible for evidence-pack
    # wiring (which in Stage 1 leaves pbo_value=None).
    store = FilesystemArtifactStore(tmp_path)
    bars = _fixture_bars(
        start=datetime(2016, 4, 22, tzinfo=UTC),
        periods=260 * 10,
        symbols=("SPY", "QQQ"),
    )
    records = _run_cpcv_for_candidate(
        candidate=_fixture_sleeve_candidate(),
        bars_by_symbol=bars,
        window_start_utc=min(bars["SPY"].index).to_pydatetime(),
        window_end_utc=max(bars["SPY"].index).to_pydatetime(),
        artifact_store=store,
    )
    # CPCVTrialRecords persisted.
    assert len(records) == 45
    # PBOReport NOT persisted in Stage 1 (Task 10 introduces this).
    assert not (tmp_path / "pbo_reports").exists()


def test_run_cpcv_for_candidate_skips_when_insufficient_history(
    tmp_path: Path,
    caplog,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    # 50 bars is way under the 10 * (2 + 1 + 5) = 80 minimum.
    bars = _fixture_bars(
        start=datetime(2026, 1, 1, tzinfo=UTC),
        periods=50,
        symbols=("SPY", "QQQ"),
    )
    records = _run_cpcv_for_candidate(
        candidate=_fixture_sleeve_candidate(),
        bars_by_symbol=bars,
        window_start_utc=min(bars["SPY"].index).to_pydatetime(),
        window_end_utc=max(bars["SPY"].index).to_pydatetime(),
        artifact_store=store,
    )
    assert records == ()
    assert not (tmp_path / "cpcv_trials").exists()
    # One info-level event logged.
    messages = [rec.message for rec in caplog.records]
    assert any("cpcv_insufficient_history" in m for m in messages)


def test_run_cpcv_for_candidate_noop_when_no_sleeve_class_path() -> None:
    # Baseline candidates without sleeve_class_path should never
    # invoke CPCV even if called. The helper guards internally.
    import dataclasses

    from tradingx.persistence import FilesystemArtifactStore

    store = FilesystemArtifactStore(tmp_path := Path("/tmp/test"))
    candidate = _fixture_sleeve_candidate()
    baseline = dataclasses.replace(candidate, sleeve_class_path=None)
    bars = _fixture_bars(
        start=datetime(2016, 4, 22, tzinfo=UTC),
        periods=260 * 10,
        symbols=("SPY", "QQQ"),
    )
    records = _run_cpcv_for_candidate(
        candidate=baseline,
        bars_by_symbol=bars,
        window_start_utc=min(bars["SPY"].index).to_pydatetime(),
        window_end_utc=max(bars["SPY"].index).to_pydatetime(),
        artifact_store=store,
    )
    assert records == ()


def test_validation_pipeline_call_site_does_not_populate_pbo_value(
    # Integration-style test that exercises the real Gate 1 entrypoint
    # that now calls _run_cpcv_for_candidate. Uses whatever top-level
    # validation function grep identifies. See Task 7 note.
    tmp_path: Path,
) -> None:
    # This test confirms the Stage 1 guarantee: even after the
    # validation pipeline runs end-to-end and writes
    # CPCVTrialRecords, the resulting EvaluationEvidencePack has
    # pbo_value == None.
    pytest.skip(
        "Stub — wire to real Gate 1 entrypoint at implementation time."
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: `ImportError` for `_run_cpcv_for_candidate`.

- [ ] **Step 3: Implement**

In `src/tradingx/validation.py`:

1. Add a module constant `_CPCV_LABEL_HORIZON_DAYS = 1` and
   `_CPCV_DEFAULTS = {"n_groups": 10, "test_group_count": 2,
   "embargo_days": 5}`.
2. Add the helper:

   ```python
   def _run_cpcv_for_candidate(
       *,
       candidate: StrategyCandidate,
       bars_by_symbol: dict[str, pd.DataFrame],
       window_start_utc: datetime,
       window_end_utc: datetime,
       artifact_store: FilesystemArtifactStore,
       git_sha: str | None = None,
       now_provider: Callable[[], datetime] | None = None,
   ) -> tuple[CPCVTrialRecord, ...]:
       if candidate.sleeve_class_path is None:
           return ()
       # Compute cohort_window_id, n_samples, paths, backtests, records.
       # Persist each record via artifact_store.write_cpcv_trial_record.
       # Return the tuple of records.
   ```

   Call the existing backtest seam in `src/tradingx/backtest.py`
   to produce per-path in-sample and out-of-sample Sharpes.
   `git_sha` can be resolved lazily (e.g., from `git rev-parse
   HEAD`) or passed in by the caller; confirm at implementation
   time by checking how tranche 1.1 populates `TrialRecord.git_sha`.
3. Insert the CPCV loop into
   `src/tradingx/controller.py::GateValidationController.generate_gate_report`
   between [line 1484](/src/tradingx/controller.py:1484) (bars
   construction) and [line 1485](/src/tradingx/controller.py:1485)
   (`build_gate_report(...)` call). The loop runs only for
   `gate_id == "1"`; for every candidate in the registry, call
   `_run_cpcv_for_candidate` with `self._artifacts` as the store.
   Discard the return value — persistence is the side effect.
   `build_gate_report`'s signature is unchanged; the
   `ValidationReport` return is unaffected in Stage 1.

- [ ] **Step 4: Run tests to verify they pass**

Run both the validation-helper tests and the controller
integration tests:

```
uv run pytest tests/unit/test_validation_cpcv_orchestration.py \
              tests/unit/test_controller_generate_gate_report_cpcv.py -v
```

Also confirm the existing Gate-1-pipeline tests still pass —
grep `build_gate_report\|generate_gate_report` in tests/ to
identify them.

- [ ] **Step 5: Commit**

Two commits — keeps the helper and the orchestration change
separable and easy to revert in isolation if needed:

```
feat(validation): add _run_cpcv_for_candidate helper (W7, Stage 1)

Per DESIGN-0018 §W7. Stateless helper that takes a candidate plus
bars + window + artifact store, generates the 45 CPCV paths, runs
the backtest seam, and writes 45 CPCVTrialRecords under cpcv_trials/.
Not yet called from any production path — the follow-up commit
wires it into GateValidationController.generate_gate_report.
```

```
feat(controller): invoke CPCV in generate_gate_report (W7, Stage 1)

Per DESIGN-0018 §W7. GateValidationController.generate_gate_report
now calls _run_cpcv_for_candidate for every candidate when
gate_id == "1". self._artifacts is the CPCVTrialRecord write
target. build_gate_report's signature and return shape are
unchanged; CPCV writes are a persistent side effect. Stage 1
guarantee: does NOT call compute_pbo; EvaluationEvidencePack.pbo_value
stays None until the Stage 2 activation commit (Task 10) wires
compute_pbo into the pipeline per §D7.
```

---

## Integration

### Task 8: End-to-end pipeline test

**Files:**

- Create: `tests/integration/test_cpcv_pbo_pipeline.py`

**Dependencies:** Tasks 1–7.

**Stage 1 scope for this test:** exercise the persistence +
cohort-query pipeline end to end through the real controller
entrypoint
[`GateValidationController.generate_gate_report`](/src/tradingx/controller.py:1464).
This is the production site that invokes the Task 7 CPCV loop;
testing one layer below (calling `build_gate_report` directly)
would bypass the `_run_cpcv_for_candidate` orchestration and
miss the integration. The controller is instantiated with a real
`FilesystemArtifactStore` pointed at `tmp_path` and a stub
market-data provider that returns deterministic bars.

Gate 1 rejects candidate sets that aren't exactly two
sleeve-backed candidates
([validation.py:791–800](/src/tradingx/validation.py:791)); the
test uses the two shipped sleeves (`trend-following-v1` +
`vol-target-v1`). Stage 1 invariants are verified by inspecting
the filesystem, not by reading an `EvaluationEvidencePack` off
the return value — `generate_gate_report` returns a
`GateReportResult`, and its `ValidationReport` does not expose
`pbo_value`. `compute_pbo` is exercised separately in the Task 5
unit suite; this integration test adds one standalone
`compute_pbo` sanity call against the assembled cohort to
confirm the persistence layer produces a well-formed matrix
input.

- [ ] **Step 1: Write failing tests**

Exercise the full flow on a small in-memory fixture:

1. Build a deterministic preseed cohort by writing **2,700
   synthetic `CPCVTrialRecord`s** directly to `cpcv_trials/`
   (60 synthetic `strategy_config_id`s × 45 paths = 2,700
   records), all under one `cohort_window_id` computed via
   `pbo.cohort_window_id_for(window_start_utc=W1,
   window_end_utc=W2, cpcv_config_fingerprint="N=10,k=2,h=5,L=1")`.
   Sharpe values sampled from a seeded `random.Random(2026)`.
   No backtests are run for the preseed — the records are
   written as synthetic rows.
2. Construct a `GateValidationController(artifacts=store,
   market_data=stub_market_data, trials_ledger=None)` where
   `stub_market_data.get_daily_bar_history(symbol, start_utc,
   end_utc)` returns bars aligned to W1..W2 with `len ≥ 10 * (2
   + 1 + 5)` rows per symbol. Invoke
   `controller.generate_gate_report(gate_id="1",
   benchmark_stack_payload=..., window_start_utc=W1,
   window_end_utc=W2, universe=("SPY", "QQQ"))`. Verify:
   - The returned value is a `GateReportResult` (containing a
     `ValidationReport`) — NOT an `EvaluationEvidencePack`.
   - `cpcv_trials/` now contains **2,790** records: 2,700
     preseeded + 45 × 2 from the two real sleeve candidates
     (`trend-following-v1` and `vol-target-v1` are the two
     entries in the mandatory candidate registry's sleeve-backed
     subset with universe `("SPY", "QQQ")`).
   - `store.list_cpcv_trial_records(cohort_window_id=<same CWID>)`
     returns all 2,790 records.
   - `store.list_cpcv_cohort_windows()` returns exactly one
     summary with `strategy_config_count == 62`
     (60 preseeded + `trend-following-v1::<fingerprint>` +
     `vol-target-v1::<fingerprint>`), `path_count == 45`,
     `record_count == 2_790`. If the real sleeves' exact
     `config_fingerprint` values are environment-dependent, relax
     to `strategy_config_count >= 62`.
   - No file exists under `pbo_reports/` (Stage 1 invariant: no
     PBO reports written from the pipeline).
3. Standalone `compute_pbo` sanity: given the assembled cohort
   from step 2, `compute_pbo(cpcv_records=records,
   random_seed=2026)` returns a valid `PBOReport` without
   raising. This confirms the persistence layer emits a matrix
   `compute_pbo` can consume — Task 10's activation will wire
   this call into the pipeline; Stage 1 verifies the input shape
   in isolation.
4. Second `controller.generate_gate_report(...)` call on a
   different window (`window_start_utc = W3`, `window_end_utc =
   W4` → different `cohort_window_id`): confirm a new
   `cohort_window_id` emerges, the first window's records are
   unchanged (2,790 still under the original CWID), and
   `store.list_cpcv_cohort_windows()` now returns two summaries
   ordered by `earliest_recorded_at_utc`.

Test-file structure note: because bar generation and the
benchmark-stack payload construction are non-trivial, lift any
existing Gate 1 test fixtures from `tests/integration/test_gate_validation_pipeline.py`
or `tests/unit/test_validation.py` as templates rather than
reinventing them.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement any missing fixtures**

The fixtures may duplicate some infrastructure from Task 7; feel
free to share via `tests/integration/conftest.py`.

- [ ] **Step 4: Run tests to verify they pass**

`uv run pytest tests/integration/test_cpcv_pbo_pipeline.py -v`

- [ ] **Step 5: Commit**

```
test(integration): end-to-end CPCV+PBO pipeline (Task 8)

Preseed cohort, run Gate 1 pipeline, verify cohort_window_id
isolation across windows and that Stage 1's invariant holds
(pbo_value = None on evidence pack, no pbo_reports/ written).
Standalone compute_pbo sanity check against the assembled
cohort confirms the matrix shape Stage 2's activation will
consume.
```

---

## Stage 1 closing pass

### Task 9: INDEX status bump, operator evidence report registration, regression sweep

**Files:**

- Modify: `src/tradingx/persistence.py`
- Modify: `docs/INDEX.md`

**Dependencies:** all Task 1–8 commits landed.

- [ ] **Step 1: Register `cpcv_trials` and `pbo_reports` categories**

In `build_operator_evidence_report` on
`FilesystemArtifactStore`, add `"cpcv_trials"` and
`"pbo_reports"` to the `categories` tuple (same list
tranche 2.1 added `sleeve_decomposition` and
`blueprint_activation` to).

- [ ] **Step 2: Update INDEX.md**

Flip DESIGN-0018's status row from `0.1.0 draft` to
`1.0.0 active`. No new row for the plan (plan files under
`docs/superpowers/plans/` are not frontmatter-indexed; same
convention as DESIGN-0017's plan).

- [ ] **Step 3: Full verification sweep**

Run locally:

```
uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py
uv run mypy src/tradingx
uv run ruff check src/tradingx tests
python3 scripts/check_index.py
./scripts/validate
```

All five MUST pass.

- [ ] **Step 4: Commit**

```
chore(tranche-2-2): Stage 1 closing pass

- Register cpcv_trials and pbo_reports categories in the operator
  evidence report.
- Flip DESIGN-0018 to 1.0.0 active in INDEX.md.
- No other behavior or doc changes; regression sweep green.
```

---

## Stage 2 activation (deferred follow-up)

### Task 10: Flip Gate 1 criterion 7 from reported-only to hard-gate [DEFERRED]

**Status:** **Do not execute until §P4 gates 3 AND 4 both clear
at evaluation time for the target candidate.** The two gates are
checked INDEPENDENTLY per DESIGN-0018 §P4 — do not conflate them.

```python
summaries = store.list_cpcv_cohort_windows()
now = datetime.now(UTC)

# §P4 gate 3 — operational maturity (ANY cohort old enough)
gate_3 = any(
    s.earliest_recorded_at_utc <= now - timedelta(days=182)
    for s in summaries
)

# §P4 gate 4 — statistical power (the CURRENT cohort, not whichever
# cohort satisfied gate 3; these are independent checks)
current_cohort_window_id = pbo.cohort_window_id_for(
    window_start_utc=current_window_start,
    window_end_utc=current_window_end,
    cpcv_config_fingerprint="N=10,k=2,h=5,L=1",
)
current = next(
    (s for s in summaries if s.cohort_window_id == current_cohort_window_id),
    None,
)
gate_4 = (
    current is not None
    and current.strategy_config_count >= 50
    and current.path_count == math.comb(10, 2)  # 45
)

assert gate_3 and gate_4, "Stage 2 activation preconditions not met"
```

Ship a readiness probe as `scripts/check_stage2_activation_ready.py`
(created under this task, not Task 9) that computes and prints
both gates for operator review.

**Task 10 lands as a single PR bundling the changes across
three files + two new artifacts:**

**Files modified:**

- `src/tradingx/controller.py` —
  `GateValidationController.generate_gate_report` now
  extends its Stage 1 CPCV loop: after the loop writes records,
  compute the two gates above; if both pass, call
  `compute_pbo(cpcv_records=store.list_cpcv_trial_records(cohort_window_id=<current>),
  random_seed=2026)`, persist the resulting `PBOReport` via
  `store.write_pbo_report`, and pass `{candidate_id: (pbo_value,
  pbo_report_id)}` into `build_gate_report` via a new optional
  parameter (see next bullet). Catch
  `InsufficientCPCVCohortError` as belt-and-suspenders and fall
  back to None for that candidate, logging
  `criterion: "pbo_cohort_insufficient"` at info level. Let
  `MixedCohortWindowError` propagate — it indicates a
  filesystem-state bug, not a normal low-cohort condition.
- `src/tradingx/validation.py` — two changes in one commit:
  1. **`build_gate_report` gains an optional parameter**
     `pbo_values_by_candidate_id: dict[str, tuple[Decimal, str]] | None = None`
     (value tuple is `(pbo_value, pbo_report_id)`). When
     provided, the function passes each candidate's pair through
     to `_build_gate1_candidate_result_pass1` so the constructed
     `EvaluationEvidencePack` carries populated
     `pbo_value` / `pbo_report_id`. Default `None` preserves the
     existing Stage 1 return shape and every existing caller's
     contract.
  2. **Criterion 7 hard-gate flip (§W6).** The Gate 1 report
     builder now emits a real pass/fail verdict:

     ```python
     pbo_passes = (
         evidence_pack.pbo_value is not None
         and evidence_pack.pbo_value <= Decimal("0.30")
     )
     ```

     When `evidence_pack.pbo_value is None` (a single-candidate
     insufficient-cohort case — gates 3/4 didn't clear for THIS
     candidate's evaluation), criterion 7 continues to report
     "pending" — not fail. Only cohorts where gates 3 + 4 clear
     AND `pbo_value > 0.30` fail criterion 7.

- `docs/validation/acceptance_gates.md` — criterion 7 moves from
  "deferred to tranche 2 hardening" to an active criterion; link
  to DESIGN-0018 and the new Stage 2 activation ADR.
- `docs/INDEX.md` — add the new ADR row; DESIGN-0018 status
  unchanged at `1.0.0 active`.

**Files created:**

- `docs/adrs/ADR-NNNN-gate1-pbo-stage2-activation.md` — the
  standalone Stage 2 activation ADR per §D6. MUST cite
  DESIGN-0018, the `cohort_window_id` that satisfied gate 3, the
  current cohort's `strategy_config_count`, the
  `evaluation_id` + `pbo_report_id` + `pbo_value` of the
  evaluation that triggered the flip, and the concrete date
  boundary (`earliest_recorded_at_utc`) observed. ADR number
  allocated from the next free slot in INDEX.md at activation
  time.
- `scripts/check_stage2_activation_ready.py` — one-off probe
  that reads `list_cpcv_cohort_windows()` and prints both gates'
  pass/fail + the cohort_window_id of the current window
  (calculated from a date range given on the CLI). Exits 0 when
  both gates pass; exits 1 otherwise. Run by the operator before
  taking this task.

**Verification:**

- `scripts/check_stage2_activation_ready.py <window_start>
  <window_end>` exits 0.
- Full sweep (ruff / mypy / pytest / check_index / validate)
  green.
- Existing Gate 1 evaluators continue to pass for candidates
  where `pbo_value is None` (criterion 7 stays "pending" in that
  arm, matching §D7).
- New unit test exercises the `pbo_value > 0.30` fail path
  (synthetic evidence pack with `pbo_value = Decimal("0.35")` →
  criterion 7 fails).
- New unit test exercises the happy path
  (`pbo_value = Decimal("0.18")` → criterion 7 passes).
- Integration test from Task 8 gets extended (or a follow-on
  integration test added) that runs the full Gate 1 pipeline
  after preseeding a mature cohort and confirms
  `EvaluationEvidencePack.pbo_value` is populated and matches
  the persisted `PBOReport.pbo_value` within `Decimal("1e-9")`
  (§P5 invariant).

**Commit:**

```
feat(validation): activate PBO (Stage 2) — criterion 7 hard-gate + evidence-pack population

Per ADR-NNNN (the accompanying Stage 2 activation ADR). Wires
compute_pbo into the Gate 1 pipeline when §P4 gates 3 AND 4 both
clear at evaluation time; populates EvaluationEvidencePack.pbo_value
and pbo_report_id; flips Gate 1 criterion 7 from reported-only to
hard-gate (pbo_value <= 0.30 passes, > 0.30 fails).

Cohort evidence at flip moment (recorded in ADR-NNNN):
  cohort_window_id         = <CWID>
  earliest_recorded_at_utc = <date>
  strategy_config_count    = <N>
  first PBOReport          = pbo_reports/<report_id>.json
  first pbo_value          = <value>

Stage 1's §D7 fallback is preserved: candidates whose CURRENT
cohort hasn't cleared gates 3/4 at their own evaluation time
continue to receive pbo_value=None + criterion 7 "pending".
```

---

## Verification matrix (Stage 1 exit criteria)

At Task 9 merge, the full repository verification MUST show:

| Check | Expected |
|---|---|
| `uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py` | exit 0; all new tests pass; all existing tests unchanged |
| `uv run mypy src/tradingx` | exit 0 |
| `uv run ruff check src/tradingx tests` | exit 0 |
| `python3 scripts/check_index.py` | `INDEX validation passed.`; DESIGN-0018 row = `1.0.0 active` |
| `./scripts/validate` | exit 0 |
| `src/tradingx/pbo.py` | exists, imports cleanly |
| `src/tradingx/validation_folds.py` | `generate_cpcv_paths` and `purged_kfold_indices` both exported |
| `src/tradingx/types.py` `__all__` | contains `CPCVTrialRecord`, `PBOReport`, `CPCVCohortWindowSummary` |
| `src/tradingx/persistence.py` | `write_cpcv_trial_record`, `list_cpcv_trial_records`, `list_cpcv_cohort_windows`, `write_pbo_report`, `load_pbo_report_by_evaluation_id` all callable |
| `FilesystemArtifactStore.build_operator_evidence_report` | reports counts for `cpcv_trials` and `pbo_reports` |
| `tests/integration/test_cpcv_pbo_pipeline.py` | green |

Tranche 2.1 regressions (`tests/integration/test_fallback_drill.py`,
etc.) MUST continue to pass unchanged.

## References

- [DESIGN-0018](../specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md)
  — tranche 2.2 spec (this plan's sole source of truth).
- [BRIEF-0003 §2.2](../specs/2026-04-22-tranche-2-planning-brief.md)
  — tranche 2 planning brief; lane definition and §2.2
  acceptance contract.
- [FFL-0001-06](/docs/roadmap/future-features-ledger.md) — CPCV +
  PBO two-stage bring-back condition.
- [DESIGN-0017 plan](2026-04-22-tranche-2-1-multi-sleeve-live-runtime-wiring-plan.md)
  — structural template for this plan.
- [`src/tradingx/validation_folds.py`](/src/tradingx/validation_folds.py)
  — tranche 1.1's purged-k-fold splitter; §W1 extends this module.
- [`src/tradingx/validation.py`](/src/tradingx/validation.py) —
  Gate 1 pipeline; Task 7 `_run_cpcv_for_candidate` wiring site
  and Task 10 activation commit target.
- [`src/tradingx/evaluation.py`](/src/tradingx/evaluation.py) —
  `evaluate_candidate`; untouched by Stage 1 code (Task 6 adds
  schema-only `pbo_value` / `pbo_report_id` fields to
  `EvaluationEvidencePack` in `types.py`, not wiring in
  `evaluation.py`).
- [`src/tradingx/backtest.py`](/src/tradingx/backtest.py) —
  backtest seam used by Task 7's per-path Sharpe computation.
  Confirm the exact helper at implementation time.
- [`src/tradingx/persistence.py`](/src/tradingx/persistence.py) —
  `FilesystemArtifactStore`; Tasks 2, 3, 4, 9 touch this module.
