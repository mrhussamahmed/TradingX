---
id: DESIGN-0011
title: Tranche 1.1 validation infrastructure design
version: 0.1.0
status: draft
created: 2026-04-21
last_amended: 2026-04-21
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-21
---

# DESIGN-0011: Tranche 1.1 validation infrastructure design

## Status

Draft on 2026-04-21. First sub-tranche under
[BRIEF-0001](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
tranche-1 plan. Pending Hussam approval.

## Purpose

Ship the validation plumbing that every later sub-tranche depends on:

1. Purged/embargoed k-fold cross-validation.
2. A trials ledger recording every candidate evaluation.
3. Deflated Sharpe Ratio wired into `evaluate_candidate` and carried on
   `EvaluationEvidencePack`.
4. Cost-drag reporting on the evidence pack.

None of these change the operational Gate 1 criteria (four hard-pass
criteria from [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
stay as-is). They make Gate 1 evaluation more honest and prepare the
evidence model for the marginal-portfolio-contribution criterion that
ships in 1.4 and the PBO gate that ships in tranche 2.

## Scope

### In scope

- Purged/embargoed k-fold CV splitter with configurable `k` and
  `embargo_days`.
- Trials ledger backed by SQLite (matches
  [journal.py](/src/tradingx/journal.py) pattern).
- DSR field on `EvaluationEvidencePack`, populated by
  `evaluate_candidate` using the existing
  [deflated_sharpe_ratio](/src/tradingx/stats.py:148) primitive and
  trial statistics from the ledger.
- Cost-drag reporting: expose per-candidate annualized cost drag
  (bps) on the evidence pack so `operating_constraint` and
  `opportunity_cost_edge` metrics are visibly net of costs.

### Explicitly out of scope

- **PBO as a hard gate.** Deferred to tranche 2 per ADR-0022. The
  trials ledger enables future PBO computation; we do not add PBO
  computation itself here.
- **CPCV.** Deferred to tranche 2. The purged k-fold in this tranche
  is the fallback topology.
- **Marginal portfolio contribution criterion.** Ships in 1.4
  alongside portfolio construction.
- **25% runtime halt trigger.** Ships in 1.4 with drawdown defense.
- **New sleeves.** Ships in 1.3.
- **HAR-RV vol estimator and regime composite.** Ships in 1.2.

## Prerequisites

None beyond `main` at `c6fbcec`. Existing primitives already present:

- `deflated_sharpe_ratio` at [stats.py:148](/src/tradingx/stats.py:148)
- `estimate_trade_costs` at [costs.py:46](/src/tradingx/costs.py:46)
- `_trade_cost_fraction` in [backtest.py:245](/src/tradingx/backtest.py:245)
  already integrates costs into daily growth
- `evaluate_candidate` in
  [evaluation.py:409](/src/tradingx/evaluation.py:409)
- `EvaluationEvidencePack` at [types.py:68](/src/tradingx/types.py:68)

## Architecture overview

Three new modules plus three surgical modifications:

### New modules

1. **`src/tradingx/validation_folds.py`** — purged/embargoed k-fold
   splitter. Pure Python + numpy. No database, no side effects.
2. **`src/tradingx/trials.py`** — trials ledger. SQLite-backed
   append-only store following the `journal.py` pattern. Exposes
   `TrialsLedger.record(trial)`, `list_for_strategy(strategy_id)`,
   and aggregate queries needed for DSR input parameters.

### New dataclass

3. **`TrialRecord`** in `src/tradingx/types.py` — the trial ledger
   entry type.

### Modifications

4. **`EvaluationEvidencePack`** at
   [types.py:68](/src/tradingx/types.py:68) — add three optional
   fields:
   - `deflated_sharpe_ratio: Decimal | None`
   - `north_star_sharpe_met: bool | None`
   - `annualized_cost_drag_bps: Decimal | None`
5. **`evaluate_candidate`** at
   [evaluation.py:409](/src/tradingx/evaluation.py:409) — after
   computing base metrics, call the trials ledger for trial
   statistics, compute DSR, compute cost-drag bps from the backtest
   engine's existing cost path, populate the three new fields.
6. **`backtest.py`** — expose accumulated per-trade costs alongside
   the existing daily-growth deduction so `evaluate_candidate` can
   report `annualized_cost_drag_bps` without re-running cost math.

## Work items

### W1 — Purged/embargoed k-fold splitter

**Contract:**

```python
# src/tradingx/validation_folds.py

def purged_kfold_indices(
    *,
    n_samples: int,
    k: int,
    embargo_days: int = 5,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Return k (train_indices, test_indices) splits with purging + embargo.

    Purging: any training sample whose index is within a fold-window of a
    test sample is removed from the training set.
    Embargo: after each test fold, `embargo_days` trailing training samples
    are removed to prevent look-ahead contamination.

    Preconditions:
    - n_samples >= k * 2 + embargo_days
    - k >= 2
    - embargo_days >= 0
    """
```

**Validation behavior:**

- Non-overlapping test folds cover the full sample space.
- Every training index is pairwise-disjoint from every test index in
  the same split.
- Every training index is at least `embargo_days + 1` positions away
  from the closest test index in the same split.
- Deterministic given the same inputs.

**Tests (TDD):**

- `test_purged_kfold_splits_cover_all_samples`
- `test_purged_kfold_no_train_test_overlap`
- `test_purged_kfold_embargo_respected`
- `test_purged_kfold_rejects_insufficient_samples`
- `test_purged_kfold_rejects_invalid_k`

**Files:**

- Create: `src/tradingx/validation_folds.py`
- Create: `tests/unit/test_validation_folds.py`

### W2 — Trials ledger

**Contract:**

```python
# src/tradingx/trials.py

from pathlib import Path
from tradingx.types import TrialRecord


class TrialsLedger:
    def __init__(self, database_path: Path) -> None: ...

    def record(self, trial: TrialRecord) -> None:
        """Append a trial record. Idempotent on trial_id."""

    def list_for_strategy(
        self,
        strategy_id: str,
        *,
        window_start_utc: datetime | None = None,
        window_end_utc: datetime | None = None,
    ) -> tuple[TrialRecord, ...]: ...

    def trial_statistics(
        self,
        strategy_id: str,
    ) -> TrialStatistics:
        """Aggregate trial statistics needed for DSR input.

        Returns n_trials, trial_sharpe_mean, trial_sharpe_variance.
        """
```

**TrialRecord fields** (in `src/tradingx/types.py`):

- `trial_id: str` — UUID v4
- `strategy_id: str`
- `candidate_id: str`
- `window_start_utc: datetime`
- `window_end_utc: datetime`
- `observed_sharpe_net_of_costs: Decimal`
- `observed_cagr_net_of_costs: Decimal`
- `observed_max_drawdown: Decimal`
- `observed_cdar_95: Decimal`
- `annualized_cost_drag_bps: Decimal`
- `passed: bool`
- `recorded_at_utc: datetime`
- `git_sha: str`
- `config_fingerprint: str` — SHA-256 of relevant config knobs

**SQLite schema:**

```sql
CREATE TABLE trials (
    trial_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    window_start_utc TEXT NOT NULL,
    window_end_utc TEXT NOT NULL,
    observed_sharpe_net_of_costs TEXT NOT NULL,
    observed_cagr_net_of_costs TEXT NOT NULL,
    observed_max_drawdown TEXT NOT NULL,
    observed_cdar_95 TEXT NOT NULL,
    annualized_cost_drag_bps TEXT NOT NULL,
    passed INTEGER NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    git_sha TEXT NOT NULL,
    config_fingerprint TEXT NOT NULL
);
CREATE INDEX idx_trials_strategy ON trials(strategy_id);
CREATE INDEX idx_trials_window ON trials(window_start_utc, window_end_utc);
```

Default path: `config.runtime.data_root / "validation" / "trials.db"`.

**Tests (TDD):**

- `test_trials_ledger_round_trip`
- `test_trials_ledger_idempotent_on_trial_id`
- `test_trials_ledger_filters_by_strategy`
- `test_trials_ledger_filters_by_window`
- `test_trial_statistics_computes_variance_across_trials`
- `test_trial_statistics_handles_single_trial`

**Files:**

- Create: `src/tradingx/trials.py`
- Create: `tests/unit/test_trials.py`
- Modify: `src/tradingx/types.py` (add `TrialRecord`, `TrialStatistics`)

### W3 — DSR wiring into `evaluate_candidate`

**Behavior change:**

1. Before returning the evidence pack, `evaluate_candidate` queries
   the trials ledger for trial statistics scoped to the candidate's
   `strategy_id`.
2. If `n_trials >= 2` and `trial_sharpe_variance > 0`, compute DSR
   via the existing `deflated_sharpe_ratio` primitive. Inputs:
   - `observed_sharpe` — candidate's observed net-of-costs Sharpe
   - `sample_size` — number of return observations
   - `skewness`, `kurtosis` — computed from candidate returns via
     `scipy.stats.skew` and `scipy.stats.kurtosis` (Fisher's
     definition, consistent with the Lo-adjusted Sharpe path)
   - `n_trials`, `trial_sharpe_variance` — from the trials ledger
3. If the preconditions fail (insufficient trials, zero variance),
   set `deflated_sharpe_ratio = None` and continue.
4. Populate `north_star_sharpe_met = observed_sharpe >= Decimal("1.3")`.
5. Record the current evaluation in the trials ledger **after** the
   evidence pack is built, not before — so the current trial doesn't
   contribute to its own DSR denominator.

**DSR is computed and reported. It is not pass/fail in tranche 1.**

**Tests (TDD):**

- `test_evaluate_candidate_populates_dsr_when_trials_sufficient`
- `test_evaluate_candidate_dsr_is_none_when_trials_insufficient`
- `test_evaluate_candidate_records_trial_after_evidence_pack_built`
- `test_evaluate_candidate_north_star_flag_set_when_sharpe_gte_1_3`
- `test_evaluate_candidate_gate_criteria_unchanged_by_dsr_addition`

**Files:**

- Modify: `src/tradingx/evaluation.py`
- Modify: `src/tradingx/types.py`
- Modify: `tests/unit/test_evaluation.py`

### W4 — Cost-drag reporting on the evidence pack

**Context:**

[backtest.py:245](/src/tradingx/backtest.py:245) already deducts
`estimate_trade_costs.total` from daily growth. Candidate returns
reaching `evaluate_candidate` are therefore net of costs. What's
missing is **visibility** — the evidence pack does not currently
expose how much cost was deducted, which makes it hard to diagnose
whether a failed `opportunity_cost_edge` criterion fails on edge or
on cost.

**Behavior change:**

1. `backtest.py` returns a new field `annualized_cost_drag_bps`
   alongside the return series. Computation: aggregate all
   per-trade `estimate_trade_costs.total` across the backtest
   window, normalize by candidate equity-average, annualize by
   `(252 / n_days)`.
2. `evaluate_candidate` threads that field into
   `EvaluationEvidencePack.annualized_cost_drag_bps`.
3. Downstream readmodel (`src/tradingx/web/readmodels.py`) surfaces
   the field in the validation diagnostic when present.

**Tests (TDD):**

- `test_backtest_reports_annualized_cost_drag_bps`
- `test_backtest_cost_drag_is_zero_for_zero_turnover_path`
- `test_evaluate_candidate_threads_cost_drag_to_evidence_pack`
- `test_readmodel_surfaces_cost_drag_when_present`

**Files:**

- Modify: `src/tradingx/backtest.py`
- Modify: `src/tradingx/evaluation.py`
- Modify: `src/tradingx/types.py` (already being modified in W3)
- Modify: `src/tradingx/web/readmodels.py`
- Modify: `tests/unit/test_backtest.py`, `test_evaluation.py`,
  `test_web_readmodels.py`

## Testing approach

Standard TDD per the repo convention: write the failing test, run it
to verify failure, write the minimal implementation, run again to
verify pass, commit. Task boundaries map to commit boundaries.

**Regression coverage:**

- Every existing `evaluate_candidate` test must continue to pass.
- Every existing `build_gate_report` test must continue to pass.
- Gate 1 pass/fail outcomes for the existing fixtures must not change
  — the four operational criteria from ADR-0022 are untouched.

## Acceptance criteria

Sub-tranche 1.1 is complete when:

1. `validation_folds.purged_kfold_indices` is implemented, tested,
   and available to callers.
2. `TrialsLedger` is implemented, tested, and default-wired to
   `config.runtime.data_root / "validation" / "trials.db"`.
3. `evaluate_candidate` populates `deflated_sharpe_ratio`,
   `north_star_sharpe_met`, and `annualized_cost_drag_bps` on every
   evidence pack (values may be `None` when preconditions are not
   met).
4. Every candidate evaluation records a trial to the ledger.
5. `pytest -q`, `mypy src/tradingx`, and `ruff check` all pass on
   the final branch.
6. No existing Gate 1 pass/fail outcome changes under the current
   fixtures.

## Decisions still open

None block this sub-tranche. Codex's D1–D4 priors (captured in
BRIEF-0001) are not needed until 1.3.

One implementation-level judgment call left to Codex:

- **`config_fingerprint` composition**: which config knobs matter for
  trial-reproducibility? Default proposal: SHA-256 of
  `{candidate_id, benchmark_stack_budget, cost_model_config,
  git_sha}`. Adjust if Codex finds a better fingerprint during
  implementation.

## Governance impact

- Update `docs/INDEX.md` to register `DESIGN-0011` (this spec) and
  `BRIEF-0001` (tranche-1 planning brief).
- No new ADRs.
- No GATES-0001 amendment — Gate 1 criteria don't change; only the
  evidence model does.

## References

### Repo documents

- [BRIEF-0001](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
- [SPEC-0013](/docs/superpowers/specs/2026-04-20-capital-growth-landscape-design.md)
- [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
- [GATES-0001](/docs/validation/acceptance_gates.md)

### Existing source files

- [src/tradingx/stats.py](/src/tradingx/stats.py) — DSR primitive
- [src/tradingx/costs.py](/src/tradingx/costs.py) — per-trade cost
  primitive
- [src/tradingx/backtest.py](/src/tradingx/backtest.py) — cost-aware
  backtest engine
- [src/tradingx/evaluation.py](/src/tradingx/evaluation.py) —
  `evaluate_candidate` entry point
- [src/tradingx/types.py](/src/tradingx/types.py) —
  `EvaluationEvidencePack`
- [src/tradingx/journal.py](/src/tradingx/journal.py) — SQLite pattern
  reference for trials ledger

### External references

- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe
  Ratio: Correcting for Selection Bias, Backtest Overfitting, and
  Non-Normality."
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- López de Prado, M. (2018). *Advances in Financial Machine
  Learning.* Chapter 7 (Cross-Validation in Finance — purging,
  embargo, CPCV).
- Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J.
  (2015). "The Probability of Backtest Overfitting."
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
