# Tranche 2.2 Stage 2 PBO Activation Plan

> **For agentic workers:** keep this branch narrow. This is an
> activation follow-up, not another CPCV infrastructure tranche. The
> target is one reviewable branch that turns Gate 1 criterion 7 into a
> real CPCV/PBO hard-gate without reopening Stage 1 plumbing.

**Goal:** execute the deferred Stage 2 activation from
[DESIGN-0018](../specs/2026-04-22-tranche-2-2-cpcv-pbo-design.md#W6--gate-1-criterion-7-evaluator-hook-s2-only)
and Task 10 from
[the tranche 2.2 plan](./2026-04-22-tranche-2-2-cpcv-pbo-plan.md):

1. keep the merged CPCV foundation as-is;
2. compute one evaluation-level `PBOReport` when the Stage 2 evidence
   gates are satisfied;
3. thread that PBO result into Gate 1 candidate evidence packs for the
   current validation batch;
4. flip criterion 7 from `pending` to a real pass/fail criterion; and
5. land the acceptance-gates narrative update plus a dedicated
   activation ADR in the same branch.

## Activation contract

This activation does **not** mean “PBO always produces a verdict from
day 1.” It means:

- the Gate 1 pipeline now knows how to compute and apply PBO when the
  existing CPCV evidence is mature enough;
- when the Stage 2 evidence gates are clear, one Gate 1 run produces:
  - exactly one `PBOReport`,
  - exactly one `(pbo_value, pbo_report_id)` payload for that run, and
  - a real criterion-7 pass/fail result on the candidates in that run;
- when the evidence gates are not clear, Gate 1 still runs normally,
  but criterion 7 remains `pending` with explicit “cohort
  insufficient / not mature yet” details; and
- no runtime behavior outside Gate 1 changes.

The important mental model is:

- **Stage 1** already installed the sensor.
- **This Stage 2 activation** connects that sensor to the Gate 1 alarm.

## Review-sensitive locks

These seams are the likely sources of adversarial-review churn. Treat
them as non-negotiable:

1. **Do not reopen CPCV Stage 1.** No changes to
   `generate_cpcv_paths`, `CPCVTrialRecord`, `PBOReport` schema,
   `compute_pbo(...)`, or the Stage 1 `_run_cpcv_for_candidate(...)`
   flow unless a test proves they are required for activation.
2. **Keep Gate 3 and Gate 4 separate.** Stage 2 readiness means:
   - gate 3: any cohort window is at least 182 days old;
   - gate 4: the **current** cohort window has at least 50 distinct
     `strategy_config_id`s and a full path matrix.
   These are independent checks and must stay independent in code.
3. **Controller owns the store-backed readiness seam.** The activation
   logic reads cohort summaries / records in `controller.py`, where the
   artifact store already lives. `validation.py` stays store-free and
   receives only an optional activation payload.
4. **One PBO report per Gate 1 run.** PBO is evaluation-level, not
   per-candidate. The activation computes PBO once from the current
   cohort window and fans the same `(pbo_value, pbo_report_id)` into
   that Gate 1 batch.
5. **The current registry shape must not create permanent pending
   candidates.** `build_mandatory_candidate_registry(...)` still
   includes the non-sleeve `mean-reversion-v1` candidate. Because PBO is
   evaluation-level, the activation payload must be attached to the
   whole Gate 1 batch, not only to sleeve-backed candidates, or the
   baseline candidate will remain structurally pending forever.
6. **No partial writes on insufficient cohort.** If readiness gates do
   not clear, or `compute_pbo(...)` still raises
   `InsufficientCPCVCohortError` / `MixedCohortWindowError`, the run
   writes no `PBOReport` and Gate 1 remains `pending` on criterion 7.
7. **`evaluate_candidate(...)` should stay untouched unless blocked.**
   The narrow path is to keep `evaluation.py` pure and apply the
   activation payload inside `validation.py` via `replace(...)` on the
   `EvaluationEvidencePack`.
8. **Criterion 7 pending is a status rule, not a fake pass/fail.**
   When `pbo_value is None`, the criterion details should say
   “pending / insufficient cohort,” and the surrounding Gate 1 status
   logic should keep the candidate `pending` rather than counting the
   criterion as an ordinary failure.
9. **Acceptance-gates doc update and ADR land in the same commit as the
   code flip.** This is an activation event, not a loose follow-up.
10. **No threshold retuning in this branch.** The hard gate is still
    `pbo_value <= Decimal("0.30")` from DESIGN-0018.

## Scope

This plan is narrower than the full tranche 2.2 plan. It activates the
already-built PBO machinery; it does **not** revisit CPCV persistence or
matrix construction.

### In scope

- controller-side Stage 2 readiness checks against
  `list_cpcv_cohort_windows()`;
- controller-side `compute_pbo(...)` orchestration and `PBOReport`
  persistence;
- evaluation-level PBO payload threading into Gate 1 validation;
- criterion-7 activation in Gate 1 candidate results;
- integration coverage proving that one Gate 1 batch can move from
  `pending` to real PBO pass/fail; and
- the acceptance-gates narrative update plus a dedicated activation ADR.

### Out of scope

- new CPCV artifact categories or schema changes;
- any rework of `_run_cpcv_for_candidate(...)`;
- changing the CPCV cohort-size / path-count thresholds;
- dashboard changes;
- Gate 2, Gate 3, or Gate 4 code;
- paper-session evidence gathering; and
- portfolio/runtime behavior outside Gate 1 validation.

## Modified files

- `src/tradingx/controller.py`
- `src/tradingx/validation.py`
- `docs/validation/acceptance_gates.md`
- `docs/adrs/ADR-0023-gate1-pbo-activation.md`
- `tests/unit/test_controller_generate_gate_report_cpcv.py`
- `tests/unit/test_validation_gate1_pbo_activation.py`
- `tests/integration/test_cpcv_pbo_pipeline.py`

No `INDEX.md` change is needed. Plan files under
`docs/superpowers/plans/` are not frontmatter-indexed.

## Implementation shape

The activation should land as one small production change with three
moving parts:

1. **Controller readiness + report generation**
   `GateValidationController.generate_gate_report(...)` already owns the
   artifact store and the window metadata. It should become the only
   place that decides whether this Gate 1 run is PBO-ready and, if so,
   writes the `PBOReport`.
2. **Validation-layer criterion flip**
   `build_gate_report(...)` stays store-free and receives one optional
   evaluation-level PBO payload for the run.
3. **Documentation / regression lock**
   The branch updates the acceptance-gates text and adds the activation
   ADR in the same commit as the code, with tests that pin the pending,
   pass, and fail paths.

That is the whole activation. No other subsystem should move.

---

## Task 1 — Controller-side Stage 2 readiness and PBO report write

**Goal:** compute one evaluation-level `PBOReport` from the current
cohort window only when the DESIGN-0018 Stage 2 readiness gates are
actually satisfied.

### Files

- `src/tradingx/controller.py`
- `tests/unit/test_controller_generate_gate_report_cpcv.py`
- `tests/integration/test_cpcv_pbo_pipeline.py`

### TDD steps

- [ ] Add failing tests in
  `tests/unit/test_controller_generate_gate_report_cpcv.py` for:
  - a mature historical cohort plus a full current cohort causes
    `generate_gate_report(gate_id="1", ...)` to write exactly one
    `PBOReport`;
  - no mature cohort anywhere in `list_cpcv_cohort_windows()` keeps the
    run PBO-pending and writes no `PBOReport`;
  - a mature historical cohort plus an undersized current cohort keeps
    the run PBO-pending and writes no `PBOReport`;
  - if `compute_pbo(...)` raises on the current cohort despite the
    summary checks, the controller logs the insufficiency and writes no
    partial `PBOReport`.
- [ ] Add one integration-style failing test in
  `tests/integration/test_cpcv_pbo_pipeline.py` that:
  - seeds a mature historical cohort;
  - seeds a full current cohort under the current window’s
    `cohort_window_id`;
  - runs the real `GateValidationController.generate_gate_report(...)`;
  - proves exactly one `pbo_reports/*.json` file exists for that run.
- [ ] Verify those tests fail against current `main`.
- [ ] In `src/tradingx/controller.py`, add a narrow private helper such
  as `_gate1_pbo_activation_payload(...)` that:
  - returns `None` unless `gate_id == "1"`;
  - computes the current evaluation’s `cohort_window_id` from
    `window_start_utc`, `window_end_utc`, and the fixed
    `N=10,k=2,h=5,L=1` CPCV fingerprint;
  - loads `list_cpcv_cohort_windows()`;
  - checks gate 3 with “any mature cohort”;
  - checks gate 4 against the **current** cohort summary only;
  - on success, loads the current cohort’s records and runs
    `compute_pbo(...)`;
  - persists the returned `PBOReport`; and
  - returns one evaluation-level payload:
    `(pbo_value, pbo_report_id)`.
- [ ] Use a deterministic explicit `evaluation_id` for the activation
  run rather than relying on `compute_pbo(...)`’s fallback. Recommended
  shape:
  `gate1-{window_end_utc:%Y%m%dT%H%M%SZ}-{cohort_window_id}`.
  This keeps reruns for the same window stable and makes the report easy
  to audit.
- [ ] If readiness fails, or `compute_pbo(...)` raises an
  insufficiency/mixed-cohort error, log one info-level
  `criterion: pbo_cohort_insufficient` event and return `None`.
- [ ] Thread the resulting payload into `build_gate_report(...)`.
- [ ] Re-run the Task 1 test slice until green.

### Lock

This task is not allowed to move the readiness seam into
`validation.py`. The store-backed activation logic belongs in the
controller, where the artifact store already exists.

---

## Task 2 — Gate 1 criterion-7 activation in validation

**Goal:** convert criterion 7 from “not implemented yet” into a real
pending/pass/fail path without widening the blast radius of
`evaluate_candidate(...)`.

### Files

- `src/tradingx/validation.py`
- `tests/unit/test_validation_gate1_pbo_activation.py`
- `tests/integration/test_cpcv_pbo_pipeline.py`

### TDD steps

- [ ] Add failing tests in
  `tests/unit/test_validation_gate1_pbo_activation.py` for:
  - `gate1_pbo_payload=None` keeps criterion 7 `pending` and the
    candidate status `pending` when the rest of Gate 1 would otherwise
    pass;
  - `gate1_pbo_payload=(Decimal("0.18"), "pbo-...")` makes criterion 7
    pass and leaves the candidate pass/fail outcome to the other
    criteria;
  - `gate1_pbo_payload=(Decimal("0.35"), "pbo-...")` makes criterion 7
    fail and therefore fails the candidate;
  - the final `EvaluationEvidencePack` seen by the Gate 1 result path
    carries the same `pbo_value` / `pbo_report_id` as the activation
    payload;
  - the non-sleeve `mean-reversion-v1` candidate receives the same
    evaluation-level PBO payload as the sleeve-backed candidates, rather
    than remaining structurally pending.
- [ ] Verify the tests fail against current `main`.
- [ ] In `src/tradingx/validation.py`, widen `build_gate_report(...)`
  with one optional argument:

  ```python
  gate1_pbo_payload: tuple[Decimal, str] | None = None
  ```

  Gate 2 remains unchanged.
- [ ] Keep `evaluate_candidate(...)` unchanged if possible. After the
  pack is created, use `replace(...)` to attach `pbo_value` and
  `pbo_report_id` when the activation payload exists.
- [ ] Add the new criterion-7 `ValidationCriterionResult` in the Gate 1
  pass-1 builder with explicit details for the three states:
  - pending: no activation payload / insufficient cohort;
  - pass: `pbo_value <= 0.30`;
  - fail: `pbo_value > 0.30`.
- [ ] Update the surrounding Gate 1 status logic so `gate1_pbo_payload
  is None` behaves like the current insufficient-history path:
  criterion 7 is shown as pending and the candidate status is `pending`,
  not ordinary `fail`.
- [ ] Keep `_reconcile_gate1_status(...)` semantics unchanged: once
  pass-1 is `pending`, the final result remains `pending`.
- [ ] Re-run the Task 2 test slice until green.

### Lock

This task is not allowed to push store reads into `validation.py`.
`validation.py` receives one optional payload for the current Gate 1
run and nothing more.

---

## Task 3 — Docs and end-to-end activation lock

**Goal:** land the governance flip and pin the full activation path with
real integration coverage.

### Files

- `docs/validation/acceptance_gates.md`
- `docs/adrs/ADR-0023-gate1-pbo-activation.md`
- `tests/integration/test_cpcv_pbo_pipeline.py`

### TDD steps

- [ ] Extend `tests/integration/test_cpcv_pbo_pipeline.py` so the
  activation path proves all of:
  - when no readiness gates clear, Gate 1 remains `pending` on criterion
    7 and no `PBOReport` is written;
  - when readiness clears and the seeded current cohort yields
    `pbo_value <= 0.30`, the Gate 1 report contains criterion-7 pass
    results and exactly one `PBOReport`;
  - when readiness clears and the seeded current cohort yields
    `pbo_value > 0.30`, criterion 7 fails the Gate 1 run.
- [ ] Verify those tests fail before the code/docs flip.
- [ ] Update
  `docs/validation/acceptance_gates.md` so Gate 1 no longer lists
  CPCV/PBO under “Deferred to tranche 2 hardening.” Replace that text
  with the active criterion-7 rule and cite DESIGN-0018 plus the new
  ADR.
- [ ] Add `docs/adrs/ADR-0023-gate1-pbo-activation.md` in the same
  branch. It must record:
  - the activating commit / date;
  - the current `cohort_window_id`;
  - the mature-cohort evidence that satisfied gate 3;
  - the current-cohort size/path evidence that satisfied gate 4; and
  - the first activated `pbo_value` / `pbo_report_id`.
- [ ] Re-run the integration slice until green.

### Lock

The ADR and acceptance-gates update are part of the activation, not
optional documentation follow-up.

---

## Verification

Run the narrow slices first, then the full repo checks:

```bash
uv run pytest tests/unit/test_controller_generate_gate_report_cpcv.py \
              tests/unit/test_validation_gate1_pbo_activation.py \
              tests/integration/test_cpcv_pbo_pipeline.py -v
uv run ruff check src/tradingx tests
uv run mypy src/tradingx
uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py
python3 scripts/check_index.py
./scripts/validate
```

## Expected end state

After this branch merges:

- Gate 1 criterion 7 is a real criterion in code and docs.
- A Gate 1 run with insufficient CPCV evidence still behaves safely:
  criterion 7 is `pending`, no report is written, and the rest of Gate
  1 runs normally.
- A Gate 1 run with sufficient CPCV evidence writes exactly one
  `PBOReport`, attaches one shared `(pbo_value, pbo_report_id)` payload
  to the Gate 1 batch, and turns criterion 7 into real pass/fail logic.
- The branch leaves Stage 1 CPCV plumbing untouched.

## Commit shape

Keep this as one narrow branch, but split the work into two commits if
helpful for review:

1. `feat(controller): add Gate 1 PBO activation payload + report write`
2. `feat(validation): activate Gate 1 criterion 7 with PBO payload`

The ADR and acceptance-gates update should land with the second commit
or as part of a final squash if you choose one review commit instead.
