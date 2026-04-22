---
id: DESIGN-0018
title: Tranche 2.2 CPCV + PBO design
version: 0.1.0
status: draft
created: 2026-04-22
last_amended: 2026-04-22
supersedes: null
superseded_by: null
author_session: claude-opus-4.7-2026-04-22
---

# DESIGN-0018 — Tranche 2.2 CPCV + PBO Design

**Status:** draft v0.1.0 — 2026-04-22

**Supersedes / Amends:** none (net-new).

**Related:** [BRIEF-0003](2026-04-22-tranche-2-planning-brief.md)
(tranche 2 planning brief, lane 2.2); [FFL-0001-06](/docs/roadmap/future-features-ledger.md)
(CPCV + PBO deferred feature); [ADR-0022](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
(Gate 1 reframe — supersedes ADR-0020).

---

## Status

Stage 1 scope is **design-only**: this document, its INDEX entry,
and the Stage 2 activation checklist. **No code changes, no
behavior changes.** All dataclasses, persistence methods, and
wiring in the §W items below are Stage 2 deliverables; Stage 1
locks their interfaces so Stage 2 can implement against a stable
target. Stage 2 activation (wiring CPCV into `evaluate_candidate`
and flipping Gate 1 criterion 7 from "pending" to pass/fail) is a
separate future sub-tranche, gated on ≥ 6 months of
CPCVTrialRecord accumulation under `cpcv_trials/` post-§W1 merge
per [FFL-0001-06](/docs/roadmap/future-features-ledger.md)
Stage 2.

This document fills the "CPCV + PBO research + spec" lane of
BRIEF-0003 (§2.2) and closes out FFL-0001-06 Stage 1.

## Purpose

Design the combinatorial purged cross-validation (CPCV) topology
and the probability of backtest overfitting (PBO) computation that
will replace tranche 1.1's [`purged_kfold_indices`](/src/tradingx/validation_folds.py)
as the validation topology once Stage 2 activates. Produce:

- A concrete CPCV parameter set (groups, test-group size, embargo)
  and a deterministic path-generation interface.
- A PBO computation aligned with Bailey-Borwein-López de Prado-Zhu
  (2016) "The Probability of Backtest Overfitting," computed from
  the CPCV path metrics.
- Artifact schemas for `CPCVTrialRecord` and `PBOReport`, ready to
  land in `types.py` and `persistence.py` without changing behavior.
- The Stage 2 activation checklist that gates the Gate 1
  criterion-7 flip.

This is a **design-only** deliverable. No code changes; no behavior
changes; no INDEX entries for new artifact categories (those land
with Stage 2).

## Prerequisites (inline research)

Per the planning-cycle call in BRIEF-0003 and Claude's round-1
discussion with Hussam, CPCV/PBO research is kept inline rather
than in a separate artifact. This section gives the background
needed to interpret the §W work items and §D decisions below.

### Current state — purged/embargoed k-fold (tranche 1.1)

[`purged_kfold_indices`](/src/tradingx/validation_folds.py) takes
`n_samples`, `k`, and `embargo_days`. It walks the sample axis in
`k` equal-sized contiguous blocks, designating each block as the
test set in turn, and removes the `embargo_days` observations
immediately following the test block from the training set.

Properties:

- Produces `k` splits (forward walk).
- Each observation appears in the test set exactly once.
- Embargo prevents look-ahead leakage from serial correlation.
- Purging of overlapping labels is **not** currently implemented —
  the current sleeves use single-bar forward labels (next-day
  return), so label overlap reduces to the embargo window.

Limitations that CPCV addresses:

1. **Only `k` CV paths.** PBO needs enough IS/OOS splits to
   estimate the overfitting probability. With `k = 5`, only 5
   paths exist — too few to stabilize PBO.
2. **No combinatorial coverage.** Every split places a contiguous
   block as test, so regime dependence between blocks is baked in.
3. **Forward-walk asymmetry.** Early blocks have less training
   data before them; late blocks have less after. Useful for
   walk-forward evidence but not for symmetric in-sample /
   out-of-sample sampling.

### CPCV background (López de Prado, 2018, Ch. 7 & 12)

Combinatorial Purged Cross-Validation partitions the `T`-sample
time series into `N` contiguous groups of roughly equal size
(`T / N` samples each). For a chosen test-group size `k` (typically
`k = 2`), every `k`-sized combination of the `N` groups becomes a
test set, and the remaining `N − k` groups become the train set.

Given `N` groups and `k` test groups:

- Number of paths: `C(N, k) = N! / (k! · (N − k)!)`.
- Each observation appears in the test set `C(N − 1, k − 1)` times
  across paths, and in the train set `C(N − 1, k)` times.
- **Purging**: remove from the training set any observation whose
  forward-looking label period overlaps any test observation.
- **Embargo**: remove from the training set `h` observations
  immediately after each test group to prevent leakage from
  residual serial correlation beyond the label horizon.

With `N = 10, k = 2`: 45 paths, each test set covers ~20% of the
sample axis.

With `N = 8, k = 2`: 28 paths, each test set ~25%.

With `N = 12, k = 2`: 66 paths, each test set ~17%.

Compute scales linearly in the number of paths. If a single
backtest on the full sample takes `B` seconds, a CPCV run takes
approximately `C(N, k) · B · (N − k) / N` seconds (each path
trains on `(N − k) / N` of the data; a full-sample backtest would
use all of it). For `N = 10, k = 2`: compute ≈ 45 · B · 0.8 = 36 B.

### PBO background (Bailey-Borwein-López de Prado-Zhu, 2016)

The probability of backtest overfitting quantifies the chance that
the "best" strategy selected in-sample will rank in the bottom
half out-of-sample. Formally, given a matrix `M` of shape
`(S, N_strategies)` where `S` is the number of CPCV paths (rows
correspond to paths) and each cell holds the performance metric of
one strategy on one path, the PBO computation is:

1. For every way to split the `S` rows into two subsets — the
   in-sample set `J` of size `⌊S/2⌋` and its complement `J_c`
   (out-of-sample) of size `⌈S/2⌉` — compute:
   - `n*`: the index of the strategy with the highest mean metric
     across rows in `J`.
   - `ω̄`: the rank of strategy `n*` among the column means of
     rows in `J_c`, normalized to `[0, 1]` (a value of 0 means
     `n*` was the worst OOS; 1 means the best).
   - `λ = ω̄ / (1 − ω̄)` (relative rank, bounded at a small
     epsilon when `ω̄ ∈ {0, 1}`).
   - `logit(λ) = log(ω̄ / (1 − ω̄))`.
2. Aggregate `logit(λ)` values across all `C(S, ⌊S/2⌋)` splits.

When `S` is even, `⌊S/2⌋ = ⌈S/2⌉` and the subsets are equal
halves (the BBLZ default case). When `S` is odd (as with the §D1
choice `N = 10, k = 2 → S = 45`), the IS set is always the smaller
`⌊S/2⌋`-sized subset — this convention is locked for determinism
(§P3). The asymmetry is negligible for `S ≥ 20` per BBLZ §4.2
simulation study; selecting IS as the floor side rather than the
ceiling side is a notation choice, not a statistical one.
3. Report:
   - **`PBO = P(logit(λ) ≤ 0) = P(ω̄ ≤ 0.5)`** — the probability
     that the IS-best strategy underperforms the median OOS.
   - **Logit distribution summary** — mean, median, stochastic
     dominance statistics from BBLZ §3.
4. The hard gate is `PBO ≤ 0.30` (tolerates up to a 30% chance
   that IS selection is non-informative).

Key properties:

- Rank-based, so robust to return-distribution assumptions.
- Requires `N_strategies ≥ ~50` and `S ≥ 20` for stable estimates
  (BBLZ §5 simulation study). With fewer, the metric is noisy.
- Uses **all** strategies, not just the winner; sparse cohorts
  under-estimate overfitting risk.

### Strategy cohort — what goes into the `N_strategies` dimension?

The question that Stage 1 must answer unambiguously: what is a
"strategy" in this project for PBO purposes? Three options:

- **Option A (registry only):** each entry in
  `build_mandatory_candidate_registry()` with
  `sleeve_class_path is not None`. Today: 2 (trend, vol-target).
  Way below the BBLZ threshold.
- **Option B (parameter configurations):** every parameter
  configuration ever evaluated under CPCV and persisted as
  `CPCVTrialRecord` files under `cpcv_trials/` (§W2) becomes a
  strategy, keyed by `strategy_config_id = candidate_id::config_fingerprint`.
  A candidate with 50 parameter tweaks over 6 months contributes
  50 distinct `strategy_config_id`s (same `candidate_id`, 50
  different `config_fingerprint`s), each with 45 path records.
- **Option C (union):** every distinct `strategy_config_id` in
  `cpcv_trials/` that satisfies the §W8 filter — i.e., any
  registry-baseline or parameter-sweep configuration that was
  evaluated under the same CPCV topology. Registry membership is
  implicitly covered by Option B once the registry baselines are
  evaluated (each baseline contributes one `strategy_config_id`).

Option C is adopted (see §D5 below). Rationale: PBO asks "given
the selection process that produced the final strategy, how likely
is this selection to be overfit?" If the selection process includes
parameter tuning — which it does, via operator-initiated parameter
sweeps written to `cpcv_trials/` — then all tuned configurations
must appear in the cohort for an honest overfitting estimate.
Omitting them under-counts the selection universe and produces an
artificially low PBO. The existing [`TrialsLedger`](/src/tradingx/trials.py)
SQLite table (tranche 1.1) is **not** the cohort source; it
holds pre-CPCV `TrialRecord`s, which lack the per-path structure
PBO requires.

### Why Stage 2 is gated on 6 months of evidence

Two reasons:

1. **Statistical power (per-cohort).** Before §W1 merge, zero
   `CPCVTrialRecord` artifacts exist under `cpcv_trials/` — CPCV
   isn't implemented yet. After merge, each weekly Gate 1
   evaluation defines a fresh `cohort_window_id` (new sample
   window) and writes 45 records per strategy evaluated in that
   cohort. The cohort grows as parameter sweeps are run against
   the same window. Reaching ≥ 50 distinct `strategy_config_id`s
   inside a single `cohort_window_id` (§P4 gate 4) requires
   repeated operator-initiated sweeps against that window.
2. **Operational maturity (across cohorts).** §P4 gate 3 demands
   that at least one `cohort_window_id` has accumulated for ≥ 6
   months — i.e., that weekly Gate 1 evaluations have been running
   that long and the CPCV pipeline has been exercised against
   real operator traffic. This is a separate check from gate 4:
   one freshly-filled cohort with 50 strategies wouldn't satisfy
   operational maturity alone. Pre-§W1-merge records do not exist,
   so the fingerprint-filter inside the `cohort_window_id` hash
   is automatically respected.

### Label horizon and embargo sizing

All currently-shipped sleeves (`trend-following-v1`,
`vol-target-v1`, baseline mean-reversion) use **single-bar
forward labels**: the strategy decides at bar `t`, the return
realizes between bar `t` and bar `t + 1`. Label horizon `L = 1`
bar (1 trading day).

Embargo `h` must satisfy `h ≥ L`, but should exceed the signal
autocorrelation decay. For trend and vol-target signals with
lookbacks of 21–252 days, signal autocorrelation at lag 1 is
moderate (empirically ρ ≤ 0.3). The tranche 1.1 choice of
`embargo_days = 5` is adequate for daily bars and is retained
(see §D3).

If a future candidate introduces multi-bar forward labels
(e.g., a 5-day forward return), the embargo rule becomes
`h ≥ L + 5` and the §W1 config accepts a per-candidate override.

## Design principles

Each principle below constrains the Stage 2 implementation.
Codex should refuse any Stage 2 plan that violates these.

### P1 — Purging and embargo preserved from tranche 1.1

The CPCV splitter MUST apply purging (drop training observations
whose label window overlaps any test observation) AND embargo
(drop `h` training observations immediately following each test
group) before emitting a split. Tranche 1.1's purged-k-fold
discipline is not weakened; it is generalized to combinatorial
test-group selection.

### P2 — Lo-adjusted Sharpe is the sole performance metric

The performance metric in every cell of the PBO matrix `M` MUST
be [`tradingx.stats.lo_adjusted_sharpe_ratio`](/src/tradingx/stats.py)
`(risk_free=0, periods_per_year=252)`. Never a per-period mean/std
or raw Sharpe. Project convention (CLAUDE.md, [ADR-0009](/docs/adrs/ADR-0009-lo-adjusted-sharpe.md))
and precedent across sleeve-runtime, evaluation, and backtest
modules. Rationale: PBO rank correlations degrade under
metric-definition drift; consistency with the rest of the stack is
mandatory.

### P3 — Deterministic CPCV path generation

Given identical `(n_samples, N, k, embargo_days, label_horizon)`
inputs, `generate_cpcv_paths` MUST return an identical ordered
tuple of `(train, test)` index pairs. No `random.shuffle`, no
hash-table iteration order, no Python set ordering relied on.
Reproducibility is mandatory for `cpcv_trials/` evidence accrual
and for Gate 1 artifact audit.

### P4 — Stage 2 activation is gated on both evidence and code

Flipping Gate 1 criterion 7 from "pending" to pass/fail requires
**all** of:

1. All six tranche-1 completion criteria met per BRIEF-0002.
2. CPCV implementation merged to `main` (the §W1–§W4 work items).
3. **Operational maturity:** at least one
   `CPCVCohortWindowSummary` returned by
   `FilesystemArtifactStore.list_cpcv_cohort_windows()` satisfies
   `summary.earliest_recorded_at_utc <= now - timedelta(days=182)`.
   Because the `CPCVTrialRecord` schema itself ships with §W1,
   the existence of any such artifact implies post-§W1-merge
   provenance; `summary.git_shas` is a belt-and-suspenders audit
   surface but is not consulted by the gate itself.
4. **Statistical power:** the `CPCVCohortWindowSummary` matching
   the current evaluation's `cohort_window_id` satisfies
   `summary.strategy_config_count >= 50` AND
   `summary.path_count == C(n_groups, test_group_count)` (full
   matrix — no missing cells).
5. A Stage 2 activation ADR explicitly flipping criterion 7 from
   reported-only to hard-gate.

Any one of (1)–(4) missing means PBO is reported alongside the
evidence pack but does NOT fail Gate 1. (5) is the formal
governance checkpoint.

### P5 — Single source of truth for PBO

Every Gate 1 evaluation that computes PBO MUST produce exactly
one `PBOReport` artifact and exactly one `pbo_value` field on the
corresponding `EvaluationEvidencePack`. The evidence pack's
`pbo_value` MUST equal the referenced `PBOReport.pbo_value` within
`Decimal("1e-9")` tolerance. No in-memory-only PBO values, no
duplicate reports per evaluation. Audit path:
`EvaluationEvidencePack.pbo_report_id → PBOReport.report_id`.

## Architecture overview

```text
  Gate 1 evaluation
        |
        v
  evaluate_candidate(candidate, bars, config)        [Stage 2: new CPCV branch]
        |
        +--> generate_cpcv_paths(n_samples=T,
        |         N=10, k=2, embargo_days=5,
        |         label_horizon=1)
        |         -> ((train_0, test_0), ..., (train_44, test_44))
        |
        +--> cohort_window_id = sha256(window_start, window_end,
        |                                   cpcv_config_fingerprint)
        |
        +--> for each (train, test) path:
        |        run_daily_bar_backtest(candidate, bars[train])    # IS Sharpe
        |        run_daily_bar_backtest(candidate, bars[test])     # OOS Sharpe
        |        -> CPCVTrialRecord (cohort_window_id,
        |                            strategy_config_id, cpcv_path_id,
        |                            is_sharpe, oos_sharpe, ...)
        |
        +--> collect cohort matrix M (shape: 45 paths × N_strategies)
        |        by calling artifact_store.list_cpcv_trial_records(
        |            cohort_window_id=<the hash computed above>)
        |        and pivoting into (cpcv_path_id × strategy_config_id)
        |
        +--> compute_pbo(M) -> PBOReport
        |        (pbo_value, logit_distribution, cohort_size, n_paths)
        |
        +--> EvaluationEvidencePack.pbo_value = PBOReport.pbo_value
             EvaluationEvidencePack.pbo_report_id = PBOReport.report_id

  Gate 1 criterion 7 check (Stage 2 post-activation ADR):
        pass iff pbo_value <= Decimal("0.30")
```

Stage 1 delivers only the type definitions, schemas, and the
activation checklist. None of the arrows above run yet.

## Work items

The §W numbering parallels DESIGN-0017's style. Every §W item is
**[S2 only]** — Stage 1 ships this document and its interface
specifications; all code lands with Stage 2, gated per §P4. §W9
is the deferred implementation PLAN, a separate spec-cycle artifact.

### W1 — `generate_cpcv_paths` splitter **[S2 only]**

Interface (Stage 1 locks this signature; Stage 2 implements):

```python
def generate_cpcv_paths(
    *,
    n_samples: int,
    n_groups: int = 10,
    test_group_count: int = 2,
    embargo_days: int = 5,
    label_horizon: int = 1,
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Return C(n_groups, test_group_count) (train_indices, test_indices)
    pairs. Purged and embargoed per §P1. Deterministic per §P3."""
```

Validation rules (Stage 2 implementation must enforce):

- `n_groups >= 4` (below which combinatorial coverage is
  meaningless; `C(3, 2) = 3` is below tranche 1.1's k=5).
- `2 <= test_group_count < n_groups`.
- `embargo_days >= label_horizon`.
- `n_samples >= n_groups * (2 + label_horizon + embargo_days)`
  (each group must fit plus its embargo slot).
- Group boundaries align to integer sample indices
  (`floor(n_samples / n_groups)`; the last group absorbs the
  remainder).

Determinism: path order is lexicographic over the set of test-group
index tuples (`itertools.combinations(range(n_groups),
test_group_count)` order).

File: `src/tradingx/validation_folds.py` (extend existing module;
keep `purged_kfold_indices` alongside for the Stage 1→2 transition
window — §W7).

### W2 — `CPCVTrialRecord` type **[S2 only]**

```python
@dataclass(frozen=True)
class CPCVTrialRecord:
    trial_id: str                  # f"cpcv-{cohort_window_id}-{strategy_config_id}-{cpcv_path_id}"
    cohort_window_id: str          # deterministic hash grouping records into one PBO matrix (see below)
    candidate_id: str              # registry candidate_id (e.g. "trend-following-v1")
    config_fingerprint: str        # same spec as TrialRecord
    strategy_config_id: str        # f"{candidate_id}::{config_fingerprint}" — cohort column key
    cpcv_path_id: str              # f"path-{test_group_tuple_hash}" — matrix row key
    n_groups: int                  # cpcv config at generation
    test_group_count: int
    embargo_days: int
    label_horizon: int
    window_start_utc: datetime     # inclusive start of the sample axis the CPCV paths partition
    window_end_utc: datetime       # exclusive end of the sample axis
    train_indices: tuple[int, ...] # post-purge, post-embargo
    test_indices: tuple[int, ...]
    in_sample_sharpe: Decimal      # lo-adjusted per §P2; diagnostic only, not used by compute_pbo
    out_of_sample_sharpe: Decimal  # lo-adjusted per §P2; the PBO matrix cell value (§W3)
    in_sample_n_trades: int
    out_of_sample_n_trades: int
    git_sha: str
    recorded_at_utc: datetime
```

**Three cohort key axes:**

- `cohort_window_id` groups records into **one coherent PBO
  matrix**. Computed deterministically as
  `f"cohort-{sha256(f'{window_start_utc.isoformat()}|{window_end_utc.isoformat()}|{cpcv_config_fingerprint}').hexdigest()[:16]}"`
  where `cpcv_config_fingerprint` encodes `(n_groups,
  test_group_count, embargo_days, label_horizon)`. Two records
  share a `cohort_window_id` iff they were evaluated on the same
  sample window with the same CPCV topology — the exact condition
  PBO requires. Reproducible across operators and machines
  without central coordination.
- `strategy_config_id = "{candidate_id}::{config_fingerprint}"`
  is the **matrix column key**. Two parameter sweeps of the same
  `candidate_id` produce distinct `strategy_config_id`s (different
  `config_fingerprint`s) and occupy distinct columns. Mirrors the
  existing [`TrialRecord`](/src/tradingx/types.py) separation of
  `candidate_id` and `config_fingerprint`.
- `cpcv_path_id` is the **matrix row key** (one of the
  `C(N, k)` paths from §W1).

Persistence category: `cpcv_trials/`. File name:
`{cohort_window_id}__{strategy_config_id}__{cpcv_path_id}.json`.
Including `cohort_window_id` in the filename prevents the
cross-evaluation overwrite: a re-evaluation of the same
`(strategy_config_id, cpcv_path_id)` on a **later window**
produces a different `cohort_window_id` and therefore a different
filename. Within a single window the record is deterministic by
construction (same inputs, same CPCV paths, same metric → same
Sharpe); overwrites within one `cohort_window_id` are idempotent
by definition.

The `::` separator in `strategy_config_id` and the `__` separator
between key parts are legal in POSIX filenames; `config_fingerprint`
and `cohort_window_id` are content hashes, so the filename length
stays bounded.

Stage 2 lands: dataclass in `types.py` + `__all__` entry;
`write_cpcv_trial_record` and `list_cpcv_trial_records` writers
on `FilesystemArtifactStore`; `cpcv_trials` registered in
`build_operator_evidence_report`. All in a single commit so
schema and writers ship together.

### W3 — `compute_pbo` function **[S2 only]**

Interface:

```python
def compute_pbo(
    *,
    cpcv_records: tuple[CPCVTrialRecord, ...],
    min_cohort_size: int = 50,
    min_paths: int = 20,
) -> PBOReport:
    """Compute PBO per Bailey-Borwein-López de Prado-Zhu (2016).
    Raises InsufficientCPCVCohortError if cohort_size < min_cohort_size
    or n_paths < min_paths. §P2 metric; §P3 determinism."""
```

Algorithm (Stage 2 implementation):

1. Build matrix `M` of shape `(n_paths, n_strategies)` from
   `cpcv_records`:
   - **Pre-condition:** every record in `cpcv_records` shares one
     `cohort_window_id` (§W2). The caller assembles this via
     §W8's query. If records with mixed `cohort_window_id` are
     passed in, raise `MixedCohortWindowError` — PBO on a
     cross-window matrix is a category error, not a degraded mode.
   - Rows = unique `cpcv_path_id` values (the `n_paths` CPCV paths
     from §W1, e.g. 45 for `N = 10, k = 2`).
   - Columns = unique `strategy_config_id` values (the cohort;
     §W2). Two parameter configs of the same registry candidate
     occupy distinct columns.
   - Cell `M[p, s]` = `out_of_sample_sharpe` for the record with
     `(cpcv_path_id=p, strategy_config_id=s)`. Each CPCV path
     contributes exactly one out-of-sample Sharpe per strategy
     (the strategy is trained on the path's train index set and
     evaluated on the path's test index set). Missing cells raise
     `InsufficientCPCVCohortError`.
   - `in_sample_sharpe` from the record is **not** used in PBO
     matrix construction; it is retained on `CPCVTrialRecord` for
     adjacent IS/OOS-divergence diagnostics (Stage 2 follow-on).
2. Enumerate all `C(n_paths, ⌊n_paths / 2⌋)` ways to choose the
   in-sample subset `J` of size `⌊n_paths / 2⌋`; the complement
   `J_c` (size `⌈n_paths / 2⌉`) is the out-of-sample subset. For
   `n_paths = 45`, this is `C(45, 22) ≈ 5 × 10^12` — too many to
   enumerate. BBLZ §4.2 approves a Monte Carlo approximation:
   sample `K = 10_000` random splits with a fixed seed (§P3). Odd
   `n_paths` always produces a floor/ceil asymmetry per
   Prerequisites; even `n_paths` reduces to the BBLZ default.

   Note: "in-sample" / "out-of-sample" in the PBO context refer to
   the split of CV **paths** (rows of `M`), NOT to the
   train/test partition inside each individual CPCV path. Every
   cell of `M` already reflects a path-level out-of-sample
   backtest Sharpe; the PBO IS/OOS split decides which of those
   path-level results are used to choose the winner (`J`) versus
   to evaluate the winner's persistence (`J_c`).

3. For each sampled split, compute two column-mean vectors over
   `M`:
   - `r̄_IS[s] = mean(M[J, s])` — strategy `s`'s mean path-level
     OOS Sharpe across the IS subset of paths.
   - `r̄_OOS[s] = mean(M[J_c, s])` — strategy `s`'s mean
     path-level OOS Sharpe across the OOS subset of paths.

   Then:
   - `n* = argmax_s r̄_IS[s]`.
   - `rank_OOS[n*] = (rank of r̄_OOS[n*] among {r̄_OOS[s] : all s}) /
     n_strategies` — rank in `[1 / n_strategies, 1]` using
     average-rank tie-breaking.
   - `ω̄ = rank_OOS[n*]` (clamp to
     `[1 / (n_strategies + 1), n_strategies / (n_strategies + 1)]`
     to avoid logit singularities when `n*` is best or worst OOS).
   - `logit_λ = log(ω̄ / (1 − ω̄))`.
4. Aggregate:
   - `pbo_value = fraction of samples with logit_λ <= 0`.
   - `logit_distribution` = empirical CDF summary (percentiles
     at 5, 25, 50, 75, 95).

Selection rule locked: `n*` is chosen by `argmax r̄_IS` (matches
BBLZ §2); full-sample-metric selection is explicitly NOT
permitted.

Error types (Stage 2):

```python
class InsufficientCPCVCohortError(ValueError):
    """Cohort or path count below BBLZ reliability threshold."""


class MixedCohortWindowError(ValueError):
    """cpcv_records contains records from more than one
    cohort_window_id; PBO requires a single coherent matrix."""
```

File: new module `src/tradingx/pbo.py` (Stage 2).

### W4 — `PBOReport` type **[S2 only]**

```python
@dataclass(frozen=True)
class PBOReport:
    report_id: str                           # f"pbo-{evaluation_id}"
    evaluation_id: str                       # links to EvaluationEvidencePack
    cohort_window_id: str                    # the exact cohort this PBO ran on (§W2)
    cohort_size: int                         # distinct strategy_config_ids in the cohort
    n_paths: int
    n_splits_sampled: int                    # 10_000 for Monte Carlo
    pbo_value: Decimal                       # P(logit_λ <= 0)
    logit_distribution_percentiles: tuple[   # (percentile, value) pairs
        tuple[Decimal, Decimal], ...
    ]
    cpcv_config_fingerprint: str             # f"N={n_groups},k={test_group_count},h={embargo_days},L={label_horizon}"
    metric_name: str                         # "lo_adjusted_sharpe" per §P2
    random_seed: int                         # for Monte Carlo reproducibility
    generated_at_utc: datetime
```

Persistence category: `pbo_reports/`. File name:
`{report_id}.json`.

Stage 2 lands: dataclass in `types.py` + `__all__` entry;
`write_pbo_report` + `load_pbo_report_by_evaluation_id` +
`list_pbo_reports` on `FilesystemArtifactStore`; `pbo_reports`
category registered in `build_operator_evidence_report`.

In addition to the persisted `PBOReport`, §W4 defines one
non-persisted summary type used as the return value of §W8's
cohort-enumeration query:

```python
@dataclass(frozen=True)
class CPCVCohortWindowSummary:
    cohort_window_id: str
    cpcv_config_fingerprint: str   # shared by every record in the cohort
    window_start_utc: datetime     # shared by every record in the cohort
    window_end_utc: datetime
    earliest_recorded_at_utc: datetime  # age of the cohort
    latest_recorded_at_utc: datetime    # freshness of the cohort
    record_count: int              # total CPCVTrialRecords present
    strategy_config_count: int     # distinct strategy_config_ids (matrix columns)
    path_count: int                # distinct cpcv_path_ids (matrix rows)
    git_shas: frozenset[str]       # every distinct git_sha present; audit trail
```

The summary is derived, not persisted. Stage 2's §W8
implementation computes it by scanning `cpcv_trials/` once,
bucketing records by `cohort_window_id`, and aggregating. Its
purpose is to make §P4 gates 3 and 4 testable with a single
query: gate 3 filters by `earliest_recorded_at_utc`; gate 4
filters by `strategy_config_count`. `git_shas` supports audit
review but is not part of either gate by itself (the existence
of a CPCVTrialRecord already implies post-§W1-merge provenance,
since the schema didn't exist before §W1; `git_shas` is retained
for explicit traceability).

### W5 — `EvaluationEvidencePack` schema extension **[S2 only]**

Stage 2 adds two nullable fields to
[`EvaluationEvidencePack`](/src/tradingx/types.py):

```python
@dataclass(frozen=True)
class EvaluationEvidencePack:
    # ... existing fields ...
    pbo_value: Decimal | None = None
    pbo_report_id: str | None = None
```

The `None` defaults ensure existing pre-CPCV evidence packs
deserialize without migration. `evaluate_candidate` populates
both when the CPCV branch runs and the cohort size clears §P4
gates 3 and 4; leaves them `None` when pre-threshold (see §D7 for
the low-cohort fallback).

### W6 — Gate 1 criterion 7 evaluator hook **[S2 only]**

The Gate 1 evaluator (today in [`evaluate_candidate`](/src/tradingx/evaluation.py)
and [`validation.py`](/src/tradingx/validation.py)) gains a
criterion-7 check:

```python
pbo_passes = (
    evidence_pack.pbo_value is not None
    and evidence_pack.pbo_value <= Decimal("0.30")
)
```

Stage 1 leaves Gate 1 as-shipped (criterion 7 marked
"pending — requires Stage 2"). Stage 2's activation ADR flips this
single line from `pending` to the pass/fail check above.

Acceptance-gates doc update
([`docs/validation/acceptance_gates.md:111–113`](/docs/validation/acceptance_gates.md))
moves CPCV/PBO from "deferred to tranche 2 hardening" to an active
criterion with a reference to DESIGN-0018 and the Stage 2 ADR.
That doc-change lands with Stage 2, not with this spec.

### W7 — Transition window: purged k-fold ↔ CPCV **[S2 only]**

For one tranche after Stage 2 activation, both splitters stay in
`validation_folds.py`:

- `purged_kfold_indices` — kept for backward-compatible evidence
  replay and for any consumer that explicitly requests non-CPCV
  splits.
- `generate_cpcv_paths` — default for `evaluate_candidate`.

After two tranches of confirmed CPCV operation (Stage 2 + one
follow-on), an ADR may deprecate `purged_kfold_indices`. No
deprecation in this spec.

### W8 — Cohort assembly from `cpcv_trials/` artifacts **[S2 only]**

`compute_pbo` assembles the cohort from persisted
`CPCVTrialRecord` files, not from
[`TrialsLedger`](/src/tradingx/trials.py). The existing SQLite
trials ledger stays untouched; CPCV records are exclusively
file-based under `cpcv_trials/` (§W2), mirroring the tranche-2.1
pattern where `SleeveDecompositionRecord` lives as files under
`sleeve_decomposition/` rather than in the ledger.
[`FilesystemArtifactStore`](/src/tradingx/persistence.py) gains:

```python
def list_cpcv_trial_records(
    self,
    *,
    cohort_window_id: str,
) -> tuple[CPCVTrialRecord, ...]:
    """Return every CPCVTrialRecord under `cpcv_trials/` whose
    `cohort_window_id` equals the argument. The cohort_window_id
    uniquely identifies one coherent PBO matrix: same sample
    window, same CPCV topology, same deterministic path set
    (§W2). Records outside the matching window are not returned;
    §W3 can build `M` directly from the result without further
    filtering."""


def list_cpcv_cohort_windows(
    self,
) -> tuple[CPCVCohortWindowSummary, ...]:
    """Enumerate every distinct `cohort_window_id` present under
    `cpcv_trials/`, returning one `CPCVCohortWindowSummary` per
    cohort (§W4 addendum). No filter arguments — the caller
    composes whatever age / size / fingerprint checks the
    activation gate requires. Summaries are returned ordered by
    `earliest_recorded_at_utc` ascending for deterministic
    iteration.

    Stage 2 activation checks compose against the return value.
    Gates 3 and 4 are evaluated SEPARATELY — gate 3 scans all
    summaries for maturity; gate 4 looks up the current
    evaluation's cohort specifically:

      summaries = store.list_cpcv_cohort_windows()

      # §P4 gate 3 — operational maturity (any cohort old enough)
      gate_3 = any(
          s.earliest_recorded_at_utc <= now - timedelta(days=182)
          for s in summaries
      )

      # §P4 gate 4 — statistical power (current cohort big enough)
      current = next(
          s for s in summaries
          if s.cohort_window_id == current_evaluation.cohort_window_id
      )
      gate_4 = (
          current.strategy_config_count >= 50
          and current.path_count
              == math.comb(n_groups, test_group_count)
      )
    """
```

Rationale for file-based over SQLite:

- No schema migration on `trials.db` (preserves tranche-1.1's
  stable ledger surface).
- Same read/write pattern as Stage 2.1's
  `write_sleeve_decomposition_record` / `list_sleeve_decomposition_records`;
  consistent with the operator-evidence-report category convention.
- Cohort sizes (~50–200 distinct `strategy_config_id`s × 45 paths
  × N_cohort_windows records ≈ ≤ ~100 k files over 6 months of
  weekly Gate 1 evaluations) stay well inside glob-performance
  bounds — and the primary query filters by `cohort_window_id`,
  which appears as a filename prefix (glob pattern
  `{cohort_window_id}__*.json` avoids a full scan).
- `cohort_window_id` (§W2) is the cohort boundary key;
  `strategy_config_id` is the column key; `cpcv_path_id` is the
  row key. No `evaluation_id` cross-reference is needed.

Stage 1: interface agreement only. Stage 2: implementation in
`persistence.py`. Unit tests cover: (a) writes across two
cohort windows, confirms `list_cpcv_trial_records` returns only
the target window; (b) mixed `strategy_config_id`s within one
window are all returned; (c) `list_cpcv_cohort_windows` returns
one `CPCVCohortWindowSummary` per distinct `cohort_window_id`
with correct `earliest_recorded_at_utc`, `record_count`,
`strategy_config_count`, `path_count`, and `git_shas` aggregates;
(d) caller-composed filter (e.g., `[s for s in summaries if
s.earliest_recorded_at_utc <= cutoff]`) correctly identifies
mature cohorts as specified by §P4 gate 3.

### W9 — Deferred PLAN **[separate artifact]**

Per the round-post-merge call with Hussam, the implementation plan
for Stage 2 (CPCV + PBO wiring + Gate 1 flip) is NOT drafted here.
It will be drafted after DESIGN-0018 merges, by the same spec-first
pattern tranche 2.1 used (DESIGN-0017 merge → PLAN merge).
Filename at that time:
`docs/superpowers/plans/<date>-tranche-2-2-cpcv-pbo-plan.md`.

## Testing approach

### Stage 1

Spec review only. No tests land with this document. Codex's peer
review is the primary verification; `check_index.py` and
`./scripts/validate` must continue to pass on the docs-only
branch before merge.

### Stage 2 (documented for the future PLAN; not binding here)

Unit tests for §W1:

- Identical inputs produce identical outputs (determinism, §P3).
- `C(N, k)` paths emitted for valid `(N, k)`.
- Each sample appears in the test set `C(N − 1, k − 1)` times.
- Embargo removes exactly `embargo_days` adjacent observations.
- Invalid inputs raise with the documented messages (including
  `k = 1`, which §D2 explicitly rejects — ensure the splitter
  refuses rather than silently collapsing to single-fold walk).

Unit tests for §W3:

- Synthetic deterministic cohort: 100 strategies, all iid — PBO
  should be ≈ 0.50. (Validates the no-edge null distribution.)
- Synthetic "one strategy strictly dominates" cohort: PBO ≈ 0.
- Synthetic "noise + lucky winner" cohort (one strategy with IS
  outlier, no OOS persistence): PBO ≈ 1.0.
- Monte Carlo reproducibility: same `random_seed` yields same
  `pbo_value`.
- `InsufficientCPCVCohortError` fires when
  `cohort_size < min_cohort_size` or `n_paths < min_paths`.

Integration tests:

- `evaluate_candidate` on a fixture strategy produces a
  CPCV-populated `EvaluationEvidencePack` with non-null
  `pbo_value` and `pbo_report_id`; round-tripping the persisted
  artifacts reproduces identical values.
- `EvaluationEvidencePack.pbo_value == PBOReport.pbo_value` within
  `Decimal("1e-9")` (§P5 invariant).

Regression:

- Existing `test_purged_kfold_*` tests continue to pass (§W7
  transition).
- Existing Gate 1 evaluators on pre-CPCV evidence packs (with
  `pbo_value = None`) continue to pass; no schema-migration
  failures.

## Acceptance criteria

### Stage 1

1. DESIGN-0018 reviewed and merged into `main` via the
   `docs/tranche-2-2-planning` → `main` merge.
2. All §D decisions resolved (no open items).
3. §W1–§W8 interfaces agreed: type signatures in
   DESIGN-0018 match what Stage 2's PLAN will implement.
4. `check_index.py` passes; `./scripts/validate` passes.
5. No runtime code changes, no new INDEX entries for code
   artifacts, no behavior changes.

### Stage 2 (recorded here; not evaluated at Stage 1 merge)

6. `generate_cpcv_paths` implemented per §W1 interface; all §W1
   unit tests pass.
7. `compute_pbo` implemented per §W3 interface; all §W3 unit tests
   pass.
8. `CPCVTrialRecord` and `PBOReport` types + writers + readers
   land with the round-trip persistence tests.
9. `EvaluationEvidencePack` schema migrated; existing packs still
   deserialize; new packs carry `pbo_value` and `pbo_report_id`
   when the §P4 thresholds are cleared.
10. `evaluate_candidate` calls CPCV branch when the cohort meets
    the §P4 threshold; falls back to a `pbo_value = None` evidence
    pack otherwise.
11. `FilesystemArtifactStore.list_cpcv_trial_records` ships;
    cohort assembly integration test passes (§W8).
12. Gate 1 criterion 7 evaluator (§W6) flipped from `pending` to
    hard-gate via a dedicated Stage 2 activation ADR.
13. `docs/validation/acceptance_gates.md` updated to reference
    DESIGN-0018 + the Stage 2 ADR.
14. `FilesystemArtifactStore.list_cpcv_cohort_windows()` returns
    at least one `CPCVCohortWindowSummary` whose
    `earliest_recorded_at_utc` is ≥ 6 months before the flip
    moment (§P4 gate 3).
15. The `CPCVCohortWindowSummary` matching the current
    evaluation's `cohort_window_id` has
    `strategy_config_count >= 50` and full matrix (`path_count
    == C(N, k)`) at the flip moment (§P4 gate 4).

## Decisions resolved

Per §D convention from DESIGN-0017, each is a concrete choice
that Codex review may challenge before merge but that is
otherwise locked.

### D1 — CPCV group count `N = 10`

With `n_samples ≈ 2520` (10 years of daily bars), each group holds
~252 samples. `C(10, 2) = 45` paths give stable PBO per BBLZ §5.

Rejected alternatives:

- `N = 8` (28 paths): acceptable but noisier PBO near the 0.30
  threshold.
- `N = 12` (66 paths): ~47% more compute with marginal statistical
  benefit on a 10-year window.

### D2 — Test-group size `k = 2`

BBLZ §3 recommends `k ∈ {1, 2}`; `k = 1` degenerates to N-fold CV
without combinatorial coverage. `k = 2` is the canonical choice.

### D3 — `embargo_days = 5`

Matches tranche 1.1's `purged_kfold_indices` default. Adequate for
1-bar label horizon and the currently-shipped signal
autocorrelations. Configurable per-candidate via §W1 if a future
sleeve introduces a longer label horizon.

### D4 — Performance metric = `lo_adjusted_sharpe_ratio`

Per §P2 and project convention. No per-period mean/std, no raw
Sharpe, no Sortino. If a future analyst wants an alternative
metric, they land a separate DESIGN amending this one; do not add
a metric selector to §W3's interface without that amendment.

### D5 — Cohort definition = every `strategy_config_id` within one `cohort_window_id`

The cohort `N_strategies` for a single PBO computation is every
distinct `strategy_config_id` present in `cpcv_trials/` sharing
the current evaluation's `cohort_window_id` (§W2). The
`cohort_window_id` is the full cohort boundary: it encodes the
sample window (`window_start_utc`, `window_end_utc`) **and** the
CPCV topology (`cpcv_config_fingerprint` = `N, k, h, L`). Records
from different sample windows never mix into the same PBO matrix.

Since `strategy_config_id = "{candidate_id}::{config_fingerprint}"`
(§W2), the cohort within one `cohort_window_id` covers:

- Every mandatory registry candidate's baseline configuration
  that has been evaluated on this window's CPCV paths (one
  `strategy_config_id` per candidate per baseline fingerprint).
- Every parameter configuration sweep whose operator-initiated
  evaluation on this window wrote its 45 `CPCVTrialRecord`s to
  the artifact store. Two sweeps of the same `candidate_id` with
  different `config_fingerprint`s count as two distinct strategies
  in the cohort (addresses Codex round-2 P1 on collision).

Rationale: omitting the tuned parameter set under-counts the
selection universe (BBLZ §3.3 caution). The cohort-window
boundary is what makes the matrix `M` internally coherent: BBLZ
assumes every cell of `M` comes from the same `(window, topology,
path)` triple, which `cohort_window_id` exactly encodes.

Typical operating pattern: a weekly Gate 1 evaluation runs on the
trailing 10-year window as of the run day; each week's window
shifts by 7 days, producing a new `cohort_window_id`; records
accumulate per-cohort. The operational-maturity gate (§P4 gate 3)
checks that the earliest `cohort_window_id` in `cpcv_trials/` is
≥ 6 months old. The statistical-power gate (§P4 gate 4) checks
that the specific `cohort_window_id` being evaluated now has
≥ 50 distinct `strategy_config_id`s.

### D6 — Stage 2 activation requires a dedicated ADR

Not a routine Gate 1 threshold tweak. The activation ADR MUST:

- Cite DESIGN-0018 as the design source.
- Document the cohort size and the count of post-§W1 records at
  the flip moment.
- Amend `docs/validation/acceptance_gates.md` in the same commit
  to flip criterion 7 from pending to hard-gate.

### D7 — Low-cohort fallback behavior

Before Stage 2 activation, and after activation whenever §P4
gates 3 or 4 fail at evaluation time, `evaluate_candidate`:

- Computes the rest of the Gate 1 evaluation normally.
- Records `EvaluationEvidencePack.pbo_value = None` and
  `pbo_report_id = None`.
- Logs a single info-level event
  (`criterion: "pbo_cohort_insufficient"`).
- Gate 1 criterion 7 reports "pending" rather than failing.

Rationale: stalling Gate 1 on insufficient PBO cohort would block
tranche-3+ candidates from progressing during the 6-month evidence
accrual window.

### D8 — Monte Carlo sampling for PBO splits

Full enumeration of `C(45, 22) ≈ 5 × 10^12` splits (odd-`S`
case, IS = floor side per Prerequisites) is infeasible. `K =
10_000` Monte Carlo samples with a fixed seed (§P3) gives a PBO
standard error < 0.005 per BBLZ §4.2's simulation study, well
inside the 0.30 threshold margin. Seed stored on `PBOReport` for
audit.

## Governance impact

- **ADRs touched:** none by this spec. Stage 2 activation will
  require a dedicated ADR per §D6.
- **Gate 1 criterion 7:** remains "pending — requires tranche 2
  CPCV infrastructure per DESIGN-0018" until Stage 2.
- **BRIEF-0003 §2.2 lane:** this spec closes the design portion.
  The deferred PLAN (see §W9) closes the rest of the lane.
- **FFL-0001-06:** Stage 1 marked complete in
  `docs/roadmap/future-features-ledger.md` at DESIGN-0018 merge.
  Stage 2 remains deferred.
- **ADR-0020 / ADR-0022:** unaffected. ADR-0022 (Gate 1 reframe)
  already left criterion 7 as a future-work slot; this spec fills
  the slot.

## References

- Bailey, D.H., Borwein, J.M., López de Prado, M., & Zhu, Q.J.
  (2016). **The Probability of Backtest Overfitting.** *Journal of
  Computational Finance*, 20(4), 39–69.
- López de Prado, M. (2018). **Advances in Financial Machine
  Learning.** Wiley. Chapters 7 (Cross-Validation in Finance) and
  12 (Backtesting through Cross-Validation).
- [BRIEF-0003 — tranche 2 planning brief](2026-04-22-tranche-2-planning-brief.md)
  (§2.2 CPCV + PBO lane definition).
- [FFL-0001-06 — CPCV and PBO as hard gates](/docs/roadmap/future-features-ledger.md)
  (two-stage bring-back condition).
- [ADR-0022 — Gate 1 reframe](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)
  (supersedes ADR-0020; leaves criterion 7 as a tranche-2 slot).
- [`src/tradingx/validation_folds.py`](/src/tradingx/validation_folds.py)
  — tranche 1.1's `purged_kfold_indices`; the incumbent splitter
  CPCV generalizes.
- [`src/tradingx/stats.py`](/src/tradingx/stats.py) —
  `lo_adjusted_sharpe_ratio` (metric per §P2),
  `deflated_sharpe_ratio` (adjacent Gate 1 primitive).
- [`src/tradingx/trials.py`](/src/tradingx/trials.py) — tranche
  1.1 trials ledger; **not** the PBO cohort source (see §W8 —
  cohort comes from `cpcv_trials/` via `FilesystemArtifactStore`).
  Referenced here for convention precedent on `candidate_id` vs.
  `config_fingerprint` field separation, which motivates §W2's
  `strategy_config_id` composite key.
- [`src/tradingx/persistence.py`](/src/tradingx/persistence.py) —
  Stage 2 wiring site for `list_cpcv_trial_records` (§W8),
  `write_cpcv_trial_record` (§W2), and `write_pbo_report` (§W4).
- [`src/tradingx/evaluation.py`](/src/tradingx/evaluation.py) —
  `evaluate_candidate`; Stage 2 wiring site for the CPCV call and
  the `EvaluationEvidencePack.pbo_value` population (§W5).
- [`docs/validation/acceptance_gates.md`](/docs/validation/acceptance_gates.md)
  (§"Deferred to tranche 2 hardening") — criterion 7 narrative
  updated with Stage 2.
