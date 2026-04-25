# TradingX Quant Hardening Execution Plan

Status: locked specification / implementation-planning-ready
Date locked: 2026-04-25

This document is the canonical execution program for hardening TradingX into a replayable, fail-closed, statistically defensible quantitative trading system.

It does not claim that TradingX is production-ready. It defines the program required before production claims can be made.

## Final Standard

"World-class" means:

- every claim has an estimator
- every estimator has an artifact
- every artifact has a replay path
- every promotion has a failure mode
- every live action has a safety override
- every production approval expires unless recertified

"Bulletproof" does not mean "cannot lose money." It means the system cannot pass weak evidence as strong evidence, cannot trade unsupported semantics, cannot silently ignore risk, and fails closed when uncertainty rises.

## Promotion States

Every strategy/configuration lives in exactly one state:

```text
disabled -> research_only -> paper_shadow -> paper_trading -> tiny_live_probe -> production
```

Promotion above `research_only` requires executable semantics. Promotion above `paper_shadow` requires promotion-valid evidence. Promotion to `production` requires complete evidence, live-probe recertification where applicable, capacity inside validated range, and unexpired production approval.

## Program-Level Locks

Every milestone must demonstrate:

- one passing case from artifacts alone
- one fail-closed case from artifacts alone
- a migration rule for existing artifacts
- an enforcement point that refuses unsupported promotion or runtime use
- a golden replay that reproduces or invalidates an old decision

Implementation proceeds vertical-slice first:

```text
schema -> artifact -> blocker -> CLI report -> activation refusal -> golden replay
```

Milestone 1 creates the enforcement spine. Milestones 2-10 attach additional evidence types and blockers to that spine.

## Trust Model Invariant

Activation state is a projection, never a source of truth.

The source of truth for promotion state, evidence classification, approvals, amendments, and recertification is an append-only, content-addressed ledger. Mutable files under `config/` may cache the latest projection for operator readability, but they cannot authorize activation, production, live probe, recertification, or exception handling.

Every authority-bearing artifact must include:

- canonical payload hash
- schema version
- content-addressed artifact URI
- ledger sequence
- previous ledger hash
- writer identity
- role/authority reference
- signature or approval record reference
- timestamp from an auditable clock source
- replay input references

Any missing, invalid, unsigned, tampered, out-of-sequence, or non-replayable authority artifact blocks promotion and runtime activation. A local edit to a projection file must be detected as projection drift, not accepted as a state transition.

Promotion-valid replay requires retained immutable inputs, not hashes alone. If raw data, normalized frames, code versions, configuration, or decision inputs cannot be retrieved from a content-addressed artifact store, the evidence is not replay-valid.

Research registration also has a pre-result boundary: promotion-valid runs must be registered before metrics are visible. Out-of-band exploratory work must be attested, and unregistered work cannot become invisible simply because it was not cited.

## V5 Governance Protocol

### Final Blocking Rule

Evidence cannot support `production` if any of the following are true:

- artifact schema is missing or unversioned
- required artifact field is missing
- data restatement materiality is undefined
- tax/account type is `unspecified`
- financing assumptions are `unspecified`
- capacity evidence is extrapolated beyond validated notional range
- human override authority is undefined
- materiality threshold is undefined
- portfolio utility function is undefined
- replay path is missing
- recertification trigger is undefined

These cases can support at most `research_only` or `paper_shadow`, depending on severity.

### Materiality Defaults

A change is material if any are true:

- any split, dividend, or corporate action changes
- any daily return changes by `>= 5 bps`
- cumulative benchmark return changes by `>= 25 bps`
- candidate CAGR changes by `>= 25 bps/year`
- Sharpe changes by `>= 0.05`
- MDD/CDaR changes by `>= 25 bps`
- any gate outcome changes
- any trade decision would have changed
- any production safety rule would have changed

### Authority Boundary

- Low-risk exception: one operator, max one trading day
- Medium-risk exception: operator plus reviewer, max five trading days
- High-risk exception: two approvers, explicit rollback condition, no auto-renewal
- No exception may disable kill switch, reconciliation, stale-data checks, or idempotency

Approval is not a free-text JSON field. Authority records must be bound to a verifiable operator identity, role registry, approval scope, expiry, canonical payload hash, and signature. Missing identity registry, missing signature, stale role registry, or write authorization failure blocks live probe, production, recertification, and manual exceptions.

### Objective Hierarchy

Portfolio-level objectives dominate sleeve-local objectives:

1. Operational safety
2. Liquidity and execution feasibility
3. Portfolio drawdown/CDaR limits
4. Portfolio-level utility after costs
5. Sleeve-level utility
6. Return maximization

A defensive sleeve can pass by reducing drawdown even if CAGR is lower. A return sleeve cannot pass by raising CAGR while violating portfolio drawdown, liquidity, operational, capacity, or cost constraints.

### Capacity, Tax, And Financing

Every strategy must declare:

- target capital scale
- max participation rate
- max order notional
- liquidity bucket
- expected cost curve as notional scales
- capacity limit where marginal edge becomes nonpositive
- whether evidence was generated at intended scale or extrapolated
- account type
- tax treatment assumption
- dividend treatment
- borrow fee treatment
- financing/cash yield assumption
- short dividend liability assumption
- whether results are pre-tax or after-tax

`capacity_extrapolation_risk` blocks `production`.

`unspecified` tax/account/financing caps evidence at `paper_shadow`.

### Production Recertification

Production is temporary, not permanent.

Strategy production approval decays to `paper_shadow` or `research_only` when:

- evidence pack becomes stale
- data vendor changes
- broker API semantics change
- cost model changes materially
- feature/model/optimizer code changes materially
- universe changes
- live drift monitor fails
- quote quality degrades
- performance exits confidence bounds
- emergency control fires
- strategy has not traded for its predeclared inactivity window

Periodic recertification:

- monthly operational review
- quarterly statistical review
- immediate review after any material or critical change

## Milestone Status

| Milestone | Status |
|---|---|
| 1. Governance Spine | Locked specification / planning-ready |
| 2. Experiment Registration & Trial Universe | Locked specification / planning-ready |
| 3. Data Restatement & Fingerprinting | Locked specification / planning-ready |
| 4. Validation Evidence Engine | Locked specification / planning-ready |
| 5. Cost, Quote Quality & Capacity Instrumentation | Locked specification / planning-ready |
| 6. Portfolio Utility & Optimizer Gates | Locked specification / planning-ready |
| 7. Expected Return & Sizing Governance | Locked specification / planning-ready |
| 8. Short-Side Capability & Financing | Locked specification / planning-ready |
| 9. Live Probe & Operational Safety | Locked specification / planning-ready |
| 10. Recertification & Change Control | Locked specification / planning-ready |

These milestones are not instructions to implement all ten at once. Many referenced modules and schema directories do not exist yet. The next work item is a thin architecture slice for Milestone 1 that creates the trust spine, ledger, artifact store interface, schema validator, CLI report, activation refusal, and golden replay.

## Milestone 1: Governance Spine

### Goal

Create the first enforceable quant-governance spine: append-only decision/evidence ledger, content-addressed artifact store interface, signed approvals, strategy capability manifests, blocker evaluation, artifact classification, CLI report, activation refusal, and golden replay for unsupported or incomplete evidence.

### Core Rule

A malformed manifest or mutable promotion projection cannot suppress blockers.

`config/strategy/promotion/<strategy_id>.json` is a generated projection only. The authoritative state is derived from append-only promotion decision ledger records plus referenced evidence artifacts.

Blockers are recomputed by `src/tradingx/promotion.py` from:

- capability manifest
- append-only promotion decision ledger
- signed approval records
- promotion state projection
- promotion evidence artifacts
- runtime semantics
- replay artifacts
- emitted target weights and sides

### Primary Files

- `src/tradingx/promotion.py`
- `src/tradingx/types.py`
- `src/tradingx/activation.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/__main__.py`
- `config/strategy/capabilities/<strategy_id>.json`
- `config/strategy/promotion/<strategy_id>.json`
- `artifacts/quant/ledger/`
- `artifacts/quant/store/`
- `schemas/quant/*.schema.json`
- `tests/fixtures/promotion/`
- `tests/unit/test_promotion.py`
- `tests/integration/test_promotion_activation.py`

### Schemas

- `schemas/quant/strategy_capability_manifest.schema.json`
- `schemas/quant/promotion_evidence.schema.json`
- `schemas/quant/promotion_decision.schema.json`
- `schemas/quant/promotion_decision_ledger_record.schema.json`
- `schemas/quant/content_addressed_artifact.schema.json`
- `schemas/quant/approval_record.schema.json`
- `schemas/quant/operator_identity.schema.json`

`strategy_capability_manifest` declares capabilities, assumptions, limits, and promotion ceiling. It does not contain `blocking_reasons`.

`promotion_evidence` governs evidence refs, replay refs, evidence class, schema versions, tax/financing/capacity statuses, and artifact freshness.

`promotion_decision` governs strategy id, current state projection, promotion ceiling, max allowed state, blockers, evidence classification, decision timestamp, and source artifacts.

Promotion decision ledger record governs:

- `ledger_record_id`
- `record_sequence`
- `previous_record_hash`
- `decision_payload_hash`
- `strategy_id`
- `decision_id`
- `approval_record_refs`
- `evidence_artifact_refs`
- `projection_target_ref`
- `created_at_utc`
- `created_by_identity_ref`
- `signature_ref`

Approval records bind reviewer intent to verifiable identity:

- operator identity ID
- role registry version
- authority boundary ref
- approval scope
- risk accepted
- expiry
- canonical payload hash
- signature

Current promotion state projection:

```text
config/strategy/promotion/<strategy_id>.json
```

It stores derived fields for operator readability:

- `strategy_id`
- `current_state`
- `last_decision_id`
- `last_reviewed_at_utc`
- `reviewed_by`
- `evidence_refs`
- `schema_version`

Milestone 10 later adds production expiry and recertification metadata to the same projection. Activation must verify that this projection matches the append-only ledger and must ignore or block on projection drift.

### Enforcement

- Activation gateway refuses any strategy/blueprint whose evidence state is below required promotion level.
- CLI promotion reports surface exact blockers.
- Local projection edits cannot create promotion state.
- Missing or invalid approval signatures block promotion.
- Ledger sequence gaps, hash mismatches, or projection drift block activation.
- Runtime planner refuses unsupported emitted sides.
- Negative weights require explicit short support or a manifest-declared long-only transform.
- `mean-reversion-v1` is capped at `research_only` until short-side support exists or the strategy is redesigned long-only.

### Migration

Existing evidence is classified as:

- `valid`: schema-complete, replayable, semantically supported
- `legacy`: old artifact missing V5 fields or schema-major mismatch
- `stale`: evidence exists but fails freshness or replay requirements
- `invalid`: contradicts manifest or runtime semantics

No legacy artifact may support production.

### CLI

```bash
uv run tradingx promotion-check --strategy-id trend-following-v1
```

Output includes strategy id, evidence class, promotion ceiling, max allowed state, blockers, manifest path, evidence refs, replay reference, and schema version.

### Acceptance Criteria

- `promotion-check --strategy-id trend-following-v1` produces a reproducible `paper_shadow`-eligible decision from fixture artifacts.
- The same decision can be reproduced from the ledger and content-addressed artifacts without trusting mutable config projection files.
- Editing `config/strategy/promotion/<strategy_id>.json` by hand produces projection drift and cannot activate a higher state.
- Missing/invalid approval identity or signature blocks promotion.
- `mean-reversion-v1` is capped at `research_only` with `unsupported_side` or `short_support_missing`.
- An old evidence pack without V5 fields is classified `legacy`.
- Activation refuses a blocked strategy and prints exact blockers.
- A negative-weight replay cannot be silently clipped and treated as promotable.

## Milestone 2: Experiment Registration & Trial Universe

### Goal

Make data mining visible by requiring promotion-valid evidence to come from an append-only registered experiment/run ledger scoped to the promotion decision.

### Core Rule

Promotion-valid DSR/PBO/MCS evidence must use the registered experiment universe only. Legacy family-wide trials and unregistered experiments are excluded.

### Primary Files

- `src/tradingx/experiments.py`
- `src/tradingx/trials.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/validation.py`
- `src/tradingx/__main__.py`
- `schemas/quant/experiment_registration.schema.json`
- `schemas/quant/experiment_run_record.schema.json`
- `schemas/quant/experiment_amendment_record.schema.json`
- `schemas/quant/trial_universe_manifest.schema.json`
- `tests/fixtures/experiments/`

### Schemas

`experiment_registration` includes:

- `experiment_id`
- `research_program_id`
- `selection_family_id`
- `promotion_decision_scope`
- `study_id`
- `parent_experiment_id`
- `strategy_id`
- `strategy_config_hash`
- `study_definition_hash`
- `feature_set_hash`
- `label_definition_hash`
- `benchmark_family_hash`
- `cost_model_hash`
- `dataset_fingerprint`
- `objective`
- `loss_function`
- `registered_at_utc`
- `registered_by`
- `pre_result_registration_status`
- `metric_visibility_policy`
- `outside_exploration_attestation_ref`
- `code_git_sha`
- `script_or_notebook_hash`
- `registration_sequence`
- `selection_influence`

`experiment_run_record` records every run lifecycle:

- `started`
- `completed`
- `failed`
- `canceled`

Failed and canceled runs remain in the universe.

Each run record also records:

- `metrics_visible_at_utc`
- `metrics_visibility_status`
- `termination_reason_code`
- `termination_stage`
- `partial_metric_payload_hash`
- `conservative_imputation_policy`
- `cancellation_sensitivity_status`

`experiment_amendment_record` is append-only and records corrections or influence changes. Changing `selection_influence=false` to `true` marks the universe `selection_audit_required`.

`trial_universe_manifest` is scoped by `promotion_decision_scope`, not just `study_id`.

### Universe Definition

`U` is built from all registered experiments and child run records in the same `promotion_decision_scope`, including related `study_id`s when they influenced the same strategy selection.

Changing objective, loss, label, feature set, benchmark family, dataset, or cost model creates a new `study_id`, but does not remove the experiment from the promotion-decision universe if it influenced the same promotion.

### Integrity Rules

- Records are never edited in place.
- Experiment registration and run start records must be committed before metrics are computed or displayed.
- Backtest, validation, and notebook wrappers must obtain a registered run token before releasing metric outputs.
- A run whose metrics were visible before registration is `post_result_registered` and cannot support promotion.
- `registration_sequence` is monotonic per `promotion_decision_scope`.
- Duplicate sequence -> `ledger_integrity_violation`
- Sequence gap -> `trial_universe_incomplete`
- Same ID with different payload -> `ledger_integrity_violation`
- Registered experiment without run record -> `trial_universe_incomplete`
- Cited unregistered artifact -> `selection_audit_required`
- Missing outside-exploration attestation -> `selection_audit_required`
- Repeated unexplained out-of-band exploration -> promotion capped at `paper_shadow` until reviewed

All hashes use canonical JSON with sorted keys, normalized decimal strings, UTC ISO timestamps, stable enum casing, explicit schema version, and no insignificant whitespace.

### DSR Universe Statistics

`trial_statistics_for_universe(...)` reports:

- `registered_trial_count`
- `metric_bearing_trial_count`
- `trial_sharpe_mean`
- `trial_sharpe_variance`
- `failed_or_canceled_count`
- `selection_audit_required`

DSR variance uses metric-bearing completed runs. Trial count and audit metadata include all selection-influencing registered attempts.

Failed and canceled runs require reason codes and cancellation sensitivity. Promotion-valid DSR must report whether conservative imputation of failed/canceled/no-metric attempts would change the hard-pass conclusion. If the conclusion flips or reason codes indicate result-contingent cancellation, DSR status becomes `pending_selection_bias`.

### Enforcement

- Promotion engine blocks states above `paper_shadow` if trial universe is incomplete or audit-required.
- Promotion engine blocks states above `paper_shadow` if any supporting run is post-result registered.
- Gate reports intended for promotion require registered experiment context.
- DSR/PBO/MCS readiness fails closed unless the universe is complete and registered.
- Gate reports without `--experiment-id` embed `promotion_valid=false` and `evidence_class=exploratory`.

### CLI

```bash
uv run tradingx register-experiment ...
uv run tradingx start-experiment-run --experiment-id ...
uv run tradingx complete-experiment-run --run-id ...
uv run tradingx trial-universe --promotion-decision-scope ...
uv run tradingx gate-report --experiment-id ...
```

### Migration

Existing `TrialsLedger` rows are classified `legacy_unregistered`, excluded from DSR/PBO/MCS, and allowed only as exploratory historical context.

### Acceptance Criteria

- DSR uses only complete registered trial-universe records, never broad family-wide legacy trials.
- Child parameter and cost perturbation runs are visible in `U`.
- Splitting studies by changing loss/objective/feature set does not evade promotion-decision universe accounting.
- Registered-but-omitted failed experiments make `trial_universe_incomplete`.
- Unregistered notebooks cannot support promotion and trigger `selection_audit_required` if later cited.
- Out-of-band exploratory work must be attested; missing or contradictory attestation triggers `selection_audit_required`.
- Post-result registered runs cannot support promotion.
- Failed/canceled runs require reason codes and DSR cancellation sensitivity.
- Legacy trials are excluded from DSR/PBO/MCS.
- Trial universe is reproducible from artifacts alone.

## Milestone 3: Data Restatement & Fingerprinting

### Goal

Make promotion-valid evidence dependent on reproducible data provenance, restatement detection, and replay-based invalidation.

### Core Rule

Promotion-valid evidence must be tied to:

- raw vendor payload hashes
- raw vendor payload artifact refs
- normalized research-frame hashes
- normalized research-frame artifact refs
- normalization code/policy hashes
- universe membership hash
- calendar/timezone/session policy
- benchmark/cash curve versions
- dependency references from dataset to evidence

Data-level change makes evidence `stale/replay_required`. Replay-proven claim change makes evidence `invalid` for the old claim.

A hash without retained inputs is not replay-valid. Promotion-valid datasets require immutable content-addressed storage of raw payloads when available, normalized frames, normalization code reference, normalization policy, benchmark/cash inputs, and universe membership inputs.

### Primary Files

- `src/tradingx/data_fingerprint.py`
- `src/tradingx/data.py`
- `src/tradingx/historical.py`
- `src/tradingx/benchmark_stack.py`
- `src/tradingx/risk_free.py`
- `src/tradingx/validation.py`
- `src/tradingx/promotion.py`
- `src/tradingx/experiments.py`
- `src/tradingx/__main__.py`
- `schemas/quant/dataset_manifest.schema.json`
- `schemas/quant/data_restatement_report.schema.json`
- `schemas/quant/evidence_invalidation_report.schema.json`
- `schemas/quant/evidence_dependency_index.schema.json`
- `tests/fixtures/data_fingerprints/`

### Schemas

`dataset_manifest` records vendor, pull time, symbols, window, bar frequency, adjustment policy, total-return policy, corporate-action policy, benchmark/cash curve versions, timezone, calendar, session policy, timestamp alignment, missing/stale policies, universe membership, inception/delisting policy, survivorship policy, raw payload hashes, normalized frame hashes, normalization code hash, normalization policy hash, corporate action hash, benchmark hash, and cash curve hash.

`data_restatement_report` records old/new dataset IDs, changed symbols/bars/corporate actions/benchmark/cash values, data-level materiality flags, evidence-level materiality flags, return deltas, raw payload availability, manual review requirement, and summary metrics.

`evidence_dependency_index` maps:

- `dataset_id -> evidence_pack_id`
- `dataset_id -> experiment_id`
- `dataset_id -> gate_report_id`
- `dataset_id -> promotion_decision_id`

`evidence_invalidation_report` records affected evidence refs, old/new dataset IDs, invalidation reason, materiality flags, required action, and timestamp.

### Materiality Split

Data-level materiality:

- split/dividend/corporate-action change
- adjustment policy mismatch
- total-return policy mismatch
- corporate-action policy mismatch
- universe membership change
- calendar/timezone/session mismatch
- daily return delta `>= 5 bps`
- cumulative benchmark return delta `>= 25 bps`
- cumulative non-material drift crossing threshold
- cash curve change crossing threshold

Evidence-level materiality after replay:

- candidate CAGR changes by `>= 25 bps/year`
- Sharpe changes by `>= 0.05`
- MDD/CDaR changes by `>= 25 bps`
- any gate outcome changes
- any trade decision would have changed
- any production safety rule would have changed

### Enforcement

- Promotion blocks above `paper_shadow` on missing/stale/materially restated datasets.
- Gate reports intended for promotion require dataset manifest.
- DSR/PBO/MCS readiness requires dataset fingerprints through Milestone 2 experiment records.
- Adjustment policy mismatch blocks promotion.
- Universe membership changes cannot masquerade as the same dataset.

### CLI

```bash
uv run tradingx dataset-manifest --symbols SPY,QQQ --window-start ... --window-end ...
uv run tradingx compare-dataset --old <dataset-id-or-path> --new <dataset-id-or-path>
uv run tradingx invalidate-evidence --restatement-report <path>
```

### Migration

Existing evidence without a dataset manifest becomes `legacy`.

Existing evidence with a manifest becomes:

- `valid` if no materiality fires
- `stale` if data-level materiality fires and replay is required
- `invalid` if replay proves old metric/gate/trade/safety claim changed
- `manual_review_required` if old raw payload is unavailable and normalized data changed

`manual_review_required` cannot support promotion above `paper_shadow`. If raw or normalized replay inputs are missing and the dataset cannot be reconstructed from immutable artifacts, the evidence is `replay_input_missing` and capped at `research_only` for claims that depend on that dataset.

### Acceptance Criteria

- Promotion-valid evidence references dataset manifests.
- Raw/normalized/code/policy hashes are recorded.
- Cumulative small changes can trigger material restatement.
- Unavailable old raw data plus normalized change requires manual review.
- Missing raw/normalized replay inputs cap evidence and cannot satisfy artifact-only replay.
- Dependency index lists affected evidence from `dataset_id`.
- Data-level change makes evidence stale/replay-required.
- Replay-proven claim change makes old evidence invalid.
- Golden replay can reproduce or invalidate old evidence from artifacts alone.

## Milestone 4: Validation Evidence Engine

### Goal

Ensure statistical evidence supports the exact economic promotion claim, not just impressive standalone metrics.

### Core Rule

Statistical evidence can block promotion, but it can support promotion only when the economic claim is:

- powered
- paired against declared baselines
- threshold-justified
- cost-stressed
- universe-aware
- stable across inference settings
- derived from promotion-valid evidence

DSR/PBO/MCS can block promotion. They cannot, by themselves, prove economic edge.

### Primary Files

- `src/tradingx/stats.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/validation.py`
- `src/tradingx/experiments.py`
- `src/tradingx/promotion.py`
- `src/tradingx/pbo.py`
- `src/tradingx/validation_folds.py`
- `src/tradingx/trials.py`
- `src/tradingx/__main__.py`
- `schemas/quant/power_analysis_report.schema.json`
- `schemas/quant/bootstrap_report.schema.json`
- `schemas/quant/paired_benchmark_uncertainty_report.schema.json`
- `schemas/quant/statistical_validation_report.schema.json`
- `schemas/quant/threshold_justification.schema.json`
- `tests/fixtures/validation_evidence/`

### Schemas

`power_analysis_report` includes Gaussian/HAC power, empirical block-bootstrap power when sample permits, `n_eff <= n`, HAC standard error, lag sensitivity, and `pending_power_conflict` if Gaussian/empirical power materially disagree.

`bootstrap_report` uses stationary block bootstrap, default `n_resamples >= 5000`, default block length `ceil(sqrt(n_eff_pre))`, sensitivity grid, fixed seed, tail metric stability check, and pending statuses for short samples or instability.

`paired_benchmark_uncertainty_report` covers cash, 60/40, static sleeve baseline, and no-trade/current holdings where applicable. It reports paired excess return CI, paired excess utility CI, paired cost-stressed CI, material edge threshold, and pass/pending/fail per baseline.

`statistical_validation_report` records dataset, experiment, promotion scope, trial universe hash, power/bootstrap/paired benchmark refs, return edge, risk constraints, cost stress, portfolio contribution, multiple-testing status, DSR/PBO/MCS/SPA statuses, economic edge CI, registered/metric-bearing/failed counts, exploratory lineage, promotion validity, and blockers.

`threshold_justification` records threshold value, economic rationale, statistical rationale, strategy type, approval metadata, and version.

### Status Rules

- Missing threshold justification -> `pending_threshold`; no hard pass allowed.
- Underpowered or unstable evidence -> max state `paper_shadow`.
- Evidence derived from exploratory gate report remains non-promotable downstream.
- DSR uses only Milestone 2 registered universe stats.
- PBO requires a complete promotion-decision CPCV matrix.
- MCS/SPA requires predeclared loss and hypothesis family.

### Enforcement

Promotion blocks above `paper_shadow` if any are true:

- missing threshold justification
- underpowered evidence
- unstable lag/bootstrap inference
- incomplete trial universe
- exploratory source evidence
- missing paired benchmark uncertainty
- DSR/PBO/MCS not universe-backed
- missing dataset manifest
- missing replay path

### CLI

```bash
uv run tradingx power-report --experiment-id ...
uv run tradingx bootstrap-report --experiment-id ...
uv run tradingx paired-benchmark-report --experiment-id ...
uv run tradingx statistical-validation-report --experiment-id ...
```

### Migration

Old evidence packs without power, bootstrap, paired benchmark uncertainty, and universe-aware DSR become `legacy_statistical_evidence`. They cannot support promotion above `paper_shadow`.

### Acceptance Criteria

- Every promotion-valid statistical report has power, bootstrap, paired benchmark, dataset, experiment, threshold, and trial-universe references.
- Missing thresholds produce `pending_threshold`.
- Underpowered/unstable evidence caps at `paper_shadow`.
- Paired benchmark uncertainty is required for economic edge claims.
- Exploratory evidence remains non-promotable downstream.
- DSR uses registered universe stats only.
- PBO/MCS/SPA fail closed on incomplete universe or missing loss/null definition.
- Old metric-only evidence is legacy.

## Milestone 5: Cost, Quote Quality & Capacity Instrumentation

### Goal

Make economic edge depend on replayable cost evidence, quote-quality state, conservative sparse-bucket handling, and turnover-adjusted capacity at intended scale.

### Core Rule

Promotion-valid cost evidence must:

- use a predeclared arrival timestamp policy
- include clean and all-events estimates
- fall back conservatively for sparse buckets
- model runtime no-trade quote states
- separate paper from live/probe/live evidence
- prove capacity at intended turnover-adjusted capital scale

Paper fills validate lifecycle/reconciliation. They do not prove real market impact.

### Primary Files

- `src/tradingx/costs.py`
- `src/tradingx/replay_slippage.py`
- `src/tradingx/execution.py`
- `src/tradingx/backtest.py`
- `src/tradingx/validation.py`
- `src/tradingx/promotion.py`
- `src/tradingx/data.py`
- `src/tradingx/experiments.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/quote_quality_record.schema.json`
- `schemas/quant/execution_cost_observation.schema.json`
- `schemas/quant/cost_model_report.schema.json`
- `schemas/quant/capacity_curve_report.schema.json`
- `tests/fixtures/cost_capacity/`

### Milestone 2 Amendment

Add `arrival_timestamp_policy` to `experiment_registration`. Changing it creates a new `study_id`. If selection-influencing, it remains in the same promotion-decision universe.

### Schemas

`quote_quality_record` records quote timestamps, system receive time, source, bid/ask/mid, spread, locked/crossed/stale flags, quote age, latency, handling policy, outage-adjacent window, trading session, vendor, and quality status.

`execution_cost_observation` records intent/order/execution IDs, symbol, side, decision/submit/ack timestamps, arrival timestamp policy, arrival mid, fill price, signed slippage, half-spread, quantity, notional, interval volume, participation rate, volatility/spread/time buckets, quote quality ref, paper/live status, and whether an impact claim is allowed.

`cost_model_report` records model version, cost feature hash, bucket assignment policy, training dataset, sample window, bucket definitions, minimum bucket sample size, bucket confidence, sparse-bucket fallback policy, clean estimate, all-events stress, adverse percentiles, sample sizes, unsupported buckets, counterfactual quality, paper/live-probe/live counts, calibration source, impact claim status, and blockers.

`capacity_curve_report` records target capital scale, tested scales, validated range, max participation, expected turnover, orders per day, rebalance frequency, annualized cost drag by scale, capacity under turnover assumption, expected cost curve, net edge curve, capacity limit, extrapolation risk, and blockers.

### Cost Rules

Clean quote estimate can support promotion only if runtime has enforced no-trade rules for stale/crossed/locked/bad-quality quote states. Otherwise promotion uses `all_events_cost_stress`.

If an intended bucket lacks samples, use the worst defensible fallback among parent bucket, liquidity-class bucket, or global adverse p90. If no defensible fallback exists: `unsupported_cost_bucket`.

If runtime refuses bad quote states and quote-state data exists, backtest replay must model skipped trades under those states.

### Enforcement

Promotion blocks above `paper_shadow` if:

- no quote-quality evidence
- no clean/all-events reports
- sparse bucket has no conservative fallback
- intended bucket unsupported
- intended capital scale outside validated range
- capacity extrapolation risk is true
- impact claim based only on paper fills
- clean estimate used without runtime no-trade rules
- cost counterfactual quality is low

Production blocks if target scale is outside validated range or `capacity_extrapolation_risk=true`.

### CLI

```bash
uv run tradingx quote-quality-report --artifact-root ...
uv run tradingx cost-model-report --sample-window ...
uv run tradingx capacity-curve --strategy-id ... --capital-scales ...
uv run tradingx replay-slippage-report --include-quote-quality
```

### Migration

Existing cost evidence becomes `legacy_cost_evidence` if missing quote-quality or arrival policy. Paper-only evidence supports lifecycle only, not market impact. Placeholder coefficients remain research-only unless tied to a cost-model report.

### Acceptance Criteria

- Every promotion-valid economic report references a cost-model report.
- Arrival policy is predeclared in experiment registration.
- Clean and all-events cost reports are both produced.
- Quote-quality state is recorded for cost observations.
- Paper/live-probe/live samples are split.
- Paper fills cannot support market-impact claims.
- Sparse buckets use conservative fallback or block.
- Bad quote clean-cost promotion requires runtime no-trade rule.
- Backtest replay models no-trade quote states when data exists.
- Capacity includes turnover/order-frequency assumptions.
- Capacity extrapolation and target scale outside validated range block production.

## Milestone 6: Portfolio Utility & Optimizer Gates

### Goal

Prevent optimization from becoming a new overfitting engine by requiring governed utility, explicit tail risk, declared baselines, paired OOS evidence, perturbation stability, turnover control, covariance recertification, and auditable fallback.

### Core Rule

An optimizer can support promotion only if:

- utility weights were predeclared and justified
- tail risk is explicit
- all applicable baselines are tested or approved for exclusion
- expected-return inputs are promotion-valid or uncertainty-penalized
- covariance regime drift is monitored
- turnover is capped
- cost/capacity evidence is incorporated
- fallback is deterministic and auditable

### Primary Files

- `src/tradingx/portfolio/construction.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/portfolio/blueprint.py`
- `src/tradingx/portfolio/optimizer.py`
- `src/tradingx/validation.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/promotion.py`
- `src/tradingx/stats.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/portfolio_utility_definition.schema.json`
- `schemas/quant/optimizer_input.schema.json`
- `schemas/quant/optimizer_decision.schema.json`
- `schemas/quant/optimizer_validation_report.schema.json`
- `schemas/quant/optimizer_recertification_report.schema.json`
- `schemas/quant/optimizer_fallback_record.schema.json`
- `tests/fixtures/portfolio_optimizer/`

### Schemas

`portfolio_utility_definition` records utility ID, lambda values, lambda justification refs, pre-experiment approval, change policy, return/risk/drawdown/tail/cost/capacity/liquidity/constraint components, objective hierarchy, threshold justification, approver, and timestamp.

Tail risk must include at least one of:

- CVaR / expected shortfall
- downside semivariance
- left-tail penalty
- predeclared tail-event stress scenarios

`optimizer_input` records candidate sleeves, expected return estimates and uncertainty, expected return promotion status, penalty policy, covariance estimator, shrinkage method, lookback, effective sample size, condition number, PSD repair policy, cost model, capacity curves, constraints, current positions, baselines, and input hash.

`optimizer_decision` records target weights, expected utility/cost/turnover/risk, tail risk estimate, marginal risk contributions, shadow prices, fallback status/reason, and decision hash.

`optimizer_validation_report` records baselines, excluded baselines and approvals, paired OOS utility, cost/capacity/tail/covariance/return/constraint stress, turnover, adjacent decision turnover, smoothing policy, weight and risk-contribution stability, no-alpha full pipeline results, covariance drift, recertification triggers, optimizer status, and blockers.

`optimizer_recertification_report` and `optimizer_fallback_record` make recertification and fallback auditable.

### Required Baselines

- no-trade/current holdings
- static sleeve budget
- equal weight
- inverse volatility
- equal risk contribution
- current non-optimized TradingX allocation

Applicable baseline exclusion blocks unless approved in an artifact.

### Validation Requirements

- Paired OOS utility on the same windows with lower 95% paired CI above threshold.
- No-alpha simulation reruns the full optimizer/baseline comparison pipeline under null/permuted returns.
- Perturb covariance, expected return, cost, capacity, constraints, and tail stress.
- Constraint shadow-price instability includes sign flip, order-of-magnitude change, binding set changes, or utility rank flips.
- Adjacent optimizer decisions must obey `max_adjacent_decision_turnover`.

### Enforcement

Promotion blocks optimizer use above `paper_shadow` if:

- lambdas lack prior justification
- tail-risk term/stress missing
- applicable baseline excluded without approval
- paired OOS utility fails
- perturbation stability fails
- covariance drift unresolved
- turnover cap exceeded
- expected returns not promotion-valid or penalized
- cost/capacity stress fails
- no-alpha full pipeline fails
- fallback artifact missing when fallback occurs

Runtime must not use stale/invalid optimizer validation. It must emit a fallback record and use static blueprint allocation.

### CLI

```bash
uv run tradingx optimizer-validate --blueprint <path> --experiment-id ...
uv run tradingx optimizer-decision --blueprint <path> --portfolio-state <path>
uv run tradingx optimizer-recertify --optimizer-id ...
uv run tradingx portfolio-baselines --blueprint <path>
```

### Migration

Existing static allocations remain valid baselines. Optimizer evidence without utility governance, baselines, paired OOS validation, perturbation tests, tail stress, or cost/capacity refs becomes `legacy_optimizer_evidence`.

### Acceptance Criteria

- Utility function and lambdas are predeclared, justified, and versioned.
- Tail risk is explicit and stress-tested.
- All applicable baselines are tested or approved for exclusion.
- Optimizer beats baselines on paired OOS utility after costs.
- Covariance/return/cost/capacity/constraint/tail perturbation tests exist.
- No-alpha full pipeline simulation prevents manufactured edge.
- Optimizer evidence references cost/capacity reports.
- Expected returns are promotion-valid or uncertainty-penalized.
- Adjacent turnover is capped.
- Optimizer recertification triggers exist.
- Invalid/stale optimizer evidence blocks runtime optimizer use.
- Fallback to static allocation is deterministic and auditable.

## Milestone 7: Expected Return & Sizing Governance

### Goal

Prevent expected-return models and sizing rules from becoming polished heuristics by requiring registered forecast identity, auditable feature/label timing, calibrated uncertainty, OOS utility improvement, and hard exposure/capacity/drawdown caps.

### Core Rule

Expected returns may affect weights only when:

- forecast identity is registered
- feature and label timing is auditable
- uncertainty is calibrated
- OOS utility improves after costs against no-forecast baselines
- sizing is bounded by hard exposure, drawdown, cost, liquidity, and capacity caps

### Primary Files

- `src/tradingx/signals/`
- `src/tradingx/sizing.py`
- `src/tradingx/strategy.py`
- `src/tradingx/evaluation.py`
- `src/tradingx/validation.py`
- `src/tradingx/portfolio/optimizer.py`
- `src/tradingx/promotion.py`
- `src/tradingx/experiments.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/forecast_model_manifest.schema.json`
- `schemas/quant/feature_manifest.schema.json`
- `schemas/quant/label_definition.schema.json`
- `schemas/quant/expected_return_report.schema.json`
- `schemas/quant/sizing_policy.schema.json`
- `schemas/quant/sizing_decision.schema.json`
- `tests/fixtures/forecast_sizing/`

### Milestone 2 Amendment

Add to `experiment_registration`:

- `forecast_model_hash`
- `feature_manifest_hash`
- `label_definition_hash`
- `sizing_policy_hash`

Changing horizon, label, feature set, model identity, or sizing policy creates a new `study_id`. If selection-influencing, it remains in the same promotion-decision scope.

### Schemas

`forecast_model_manifest` records model identity, hashes, change policy, horizon, target variable, label/feature manifests, training dataset, model class/parameters, prior/shrinkage, uncertainty estimator/version, retraining cadence, regime conditioning, economic rationale, monotonicity constraints, promotion status, and approval timestamp.

`feature_manifest` records feature definitions, source refs, availability timestamp policy, timestamp source, source data arrival timestamp, computation timestamp, decision timestamp, lookback windows, lag policy, missing value policy, normalization, hash, leakage audit, and leakage checks.

`label_definition` records target, horizon, return basis, benchmark ref, cost adjustment, overlap policy, purge window, embargo window, overlap status, timestamp alignment, and hash.

`expected_return_report` records `mu_hat`, `sigma_mu`, uncertainty-penalized mu, uncertainty calibration, prediction interval coverage, calibration window/status, forecast decay, OOS utility, no-forecast baseline, simple heuristic baselines, feature ablation, regime split, promotion validity, and blockers.

`sizing_policy` records sizing method, target vol, position/sleeve/gross/net/leverage/order/participation caps, drawdown budget, cost/capacity refs, Kelly disablement/gate/variance/tail/estimation-error haircuts, max Kelly multiplier, cap rules, and approval timestamp.

`sizing_decision` records forecast ref, sizing policy, raw signal, mu/sigma/penalized mu, vol, cost/capacity/drawdown adjustment, final target weight, cap bindings, and decision hash.

### Expected Return Rules

Forecasts must beat no-forecast and simple heuristic baselines on OOS utility after costs/capacity. Prediction fit alone cannot support promotion.

If uncertainty is present but uncalibrated:

- blocker: `expected_return_uncertainty_uncalibrated`
- max state: `paper_shadow`

Features must be available before decision time with auditable timestamp source. Label overlap must feed purge/embargo behavior in CV/CPCV.

### Sizing Rules

Existing heuristic signals remain allowed as inputs, but they are not expected-return forecasts. Production requires governed sizing policy and utility evidence.

Kelly is disabled by default. It requires a complete Kelly gate, and full Kelly is never allowed.

Sizing property rules:

- higher cost cannot increase size
- higher uncertainty cannot increase size
- lower capacity cannot increase size
- worse drawdown state cannot increase size
- negative penalized edge cannot produce long exposure unless explicitly allowed

### Enforcement

Promotion blocks above `paper_shadow` if:

- uncertainty is uncalibrated
- forecast fails OOS utility after costs
- hashes missing from experiment registration
- feature timestamp source unauditable
- hard exposure caps missing
- heuristic signals lack governed sizing
- Kelly enabled without complete gate

### CLI

```bash
uv run tradingx forecast-report --model-id ...
uv run tradingx sizing-policy-check --strategy-id ...
uv run tradingx sizing-decision --strategy-id ... --forecast-ref ...
```

### Migration

Existing signals remain heuristic signals, not expected-return forecasts. Existing pseudo-Kelly sizing becomes `heuristic_sizing_not_kelly`. Heuristic signals can reach production only through governed sizing and portfolio utility validation after costs/capacity.

### Acceptance Criteria

- Forecast identity, feature manifest, label definition, and sizing policy are registered.
- Feature timestamp source is auditable.
- Label overlap policy drives purge/embargo.
- Uncertainty is calibrated, not merely present.
- Forecasts improve OOS utility after costs vs no-forecast/simple baselines.
- Optimizer consumes only promotion-valid or uncertainty-penalized returns.
- Pseudo-Kelly is renamed/classified and cannot claim Kelly.
- True Kelly remains disabled unless gate satisfied.
- Hard exposure/cost/capacity/drawdown caps bind.
- Sizing monotonicity/property tests pass.

## Milestone 8: Short-Side Capability & Financing

### Goal

Prevent negative weights from being confused with executable shorting by separating research simulation from runtime capability and requiring broker/mode-specific evidence, fresh borrow data, financing costs, margin stress, corporate-action controls, forced-buy-in handling, and live-probe evidence.

### Core Rule

Short strategies may be researched with modeled financing, but runtime short promotion requires:

- broker/mode-specific short capability
- fresh borrow/locate/fee data
- ex-dividend and corporate-action controls
- margin stress and portfolio interaction
- forced-buy-in and broker-initiated cover handling
- integration with cost/capacity evidence
- live-probe evidence before production

Mean reversion remains capped until short package exists or the strategy is redesigned long-only.

### Primary Files

- `src/tradingx/risk.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/execution.py`
- `src/tradingx/costs.py`
- `src/tradingx/strategy.py`
- `src/tradingx/signals/mean_revert.py`
- `src/tradingx/promotion.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/short_capability_manifest.schema.json`
- `schemas/quant/borrow_availability_snapshot.schema.json`
- `schemas/quant/short_financing_model.schema.json`
- `schemas/quant/short_risk_report.schema.json`
- `schemas/quant/short_runtime_event.schema.json`
- `tests/fixtures/short_side/`

### Schemas

`short_capability_manifest` separates `short_research_simulation_supported` from `short_runtime_supported` and records broker ID, broker mode, API version, shortability semantics, paper/live match status, allowed symbols, borrow/shortability sources, locate requirements, freshness thresholds, HTB/fee/recall/forced buy-in/dividend/corporate action/margin policies, exposure caps, live-probe requirement, and approval timestamp.

`borrow_availability_snapshot` records symbol, broker, mode, shortable/easy-to-borrow/hard-to-borrow flags, borrow rate, fee timestamp, locate status/expiry, source, and staleness.

`short_financing_model` records borrow fee curve, locate fee policy, dividend liability, margin model, portfolio margin usage, concentration/gross/net policies, stress margin, cash collateral, fee stress, forced-buy-in slippage, financing drag, and version.

`short_risk_report` records broker/mode, symbols tested, borrow coverage, historical borrow coverage, fee/margin/portfolio margin/recall/dividend/ex-dividend/corporate action/forced buy-in stress, paper/live semantics, live-probe refs, constraint status, and blockers.

`short_runtime_event` includes borrow unavailable, fee spike, recall, forced buy-in, margin breach, dividend liability, short rejected, shortability changed, broker-initiated cover detected, ex-dividend risk, and corporate-action risk.

### Runtime Rules

- Negative target weights require short capability manifest.
- Sell-short intents require fresh broker/mode-specific borrow snapshot.
- Stale borrow/locate/fee data blocks new shorts.
- Policy defines whether stale data also forces reduction.
- Shortability changes produce event and apply policy.
- Ex-dividend/corporate-action checks run before opening and while holding shorts.
- Broker-initiated covers must reconcile and emit runtime event.
- Margin stress includes portfolio-level gross/net/concentration interaction.

### Historical Backtest Rules

Short backtests require a historical borrow availability path or are classified research-only. Backtests cannot assume every symbol was shortable for promotion-valid evidence.

Borrow fees, locate fees, dividend liability, forced-buy-in slippage, and short financing drag must feed Milestone 5 cost/capacity reports.

### Enforcement

Promotion blocks:

- above `research_only` if runtime short support is incomplete
- above `paper_shadow` if broker/mode behavior is unverified
- above `tiny_live_probe` if live-probe short evidence is missing
- production if paper/live semantics mismatch or live-probe evidence is absent

Runtime blocks short target/order if manifest missing, runtime support false, symbol not shortable, locate missing, borrow/fee snapshot stale, margin insufficient, ex-dividend/corporate-action policy blocks, or broker constraint is unknown.

### CLI

```bash
uv run tradingx short-capability-check --strategy-id mean-reversion-v1
uv run tradingx borrow-snapshot --symbol QQQ
uv run tradingx short-risk-report --strategy-id ...
```

### Migration

Existing short-emitting strategies are capped at `research_only`. Existing short backtests without borrow/financing/corporate-action/margin model become `legacy_short_evidence`.

### Acceptance Criteria

- Negative target weights cannot be silently clipped or ignored.
- Research short simulation is separate from runtime short support.
- Short-emitting strategies require broker/mode-specific capability for runtime promotion.
- Borrow/locate/fee freshness is enforced.
- Ex-dividend and corporate-action controls exist.
- Margin stress includes portfolio interaction.
- Broker-initiated covers reconcile and emit events.
- Short costs feed Milestone 5 evidence.
- Live-probe evidence is required before production short exposure.
- Mean reversion remains capped until short package exists or long-only redesign lands.

## Milestone 9: Live Probe & Operational Safety

### Goal

Make live-probe trading a bounded operational experiment with role-bounded approval, minimum real activity, fresh safety drills, broker-timeout state transitions, idempotent/reconciled order flow, rollback behavior, and post-probe recertification.

### Core Rule

Live probe can validate operational readiness only if it is:

- preapproved by role-bounded authority
- constrained by explicit capital/loss/activity limits
- backed by fresh safety drills
- governed by a broker-timeout state machine
- fully idempotent and reconciled
- ended with post-probe recertification
- free of unresolved incidents

Live probe does not prove durable edge.

### Primary Files

- `src/tradingx/live_enablement.py`
- `src/tradingx/operator_control.py`
- `src/tradingx/runtime_host.py`
- `src/tradingx/runtime_portfolio.py`
- `src/tradingx/execution.py`
- `src/tradingx/risk.py`
- `src/tradingx/promotion.py`
- `src/tradingx/types.py`
- `src/tradingx/__main__.py`
- `schemas/quant/live_probe_plan.schema.json`
- `schemas/quant/live_probe_run_record.schema.json`
- `schemas/quant/live_probe_recertification_report.schema.json`
- `schemas/quant/authority_boundary.schema.json`
- `schemas/quant/broker_timeout_state_transition.schema.json`
- `schemas/quant/operational_safety_drill.schema.json`
- `schemas/quant/runtime_override_event.schema.json`
- `schemas/quant/reconciliation_incident.schema.json`
- `tests/fixtures/live_probe/`

### Schemas

`authority_boundary` records approval type, identity provider, operator identity IDs, role registry version, role, scope, write authorization status, max exception duration, second approver requirement, approvers, canonical approval payload hash, signatures, approval time, and expiry.

`live_probe_plan` records strategy, broker, mode, symbols, capital/order/loss/order-count/participation/spread limits, duration, minimum order count, minimum filled notional, minimum reconciliation cycles, minimum sessions, no-signal outcome policy, start/success/rollback criteria, flatten policy, kill switch requirement, authority ref, approval, and expiry.

`live_probe_run_record` records status, orders, fills, filled notional, sessions, reconciliation cycles, slippage, quote quality, reconciliation, limit breaches, rollback, success criteria, minimum activity, and evidence refs.

`live_probe_recertification_report` records run refs, incidents, unresolved incidents, minimum activity, drill status, broker-timeout status, idempotency, reconciliation, cost observations, production eligibility, blockers, and approval.

`operational_safety_drill` records drill type, expected/observed behavior, pass/fail, freshness window, valid-until timestamp, staleness, evidence refs, and execution time.

`runtime_override_event` records event type, priority, action, scope, reason, operator, authority ref, disabled controls requested, expiry, and timestamp. `disabled_controls_requested` must be empty.

`broker_timeout_state_transition` records order/intent/idempotency identifiers, retry sequence, dedupe window, state transition, trigger, reconciliation requirement, retry permission, and timestamp.

Timeout states:

- `submit_unknown`
- `ack_unknown`
- `fill_unknown`
- `cancel_unknown`
- `reconcile_required`
- `safe_halted`
- `recovered`

### Override Hierarchy

Runtime precedence:

1. Operator kill
2. Broker anomaly
3. Duplicate order or idempotency failure
4. Reconciliation mismatch
5. Stale/invalid market data
6. Drawdown/loss-limit breach
7. Model signal

Higher priority overrides lower priority. No exception may disable core controls.

### Runtime Rules

- Live probe requires approved, unexpired authority and plan.
- Safety drills must be fresh.
- Minimum activity must be met; otherwise status is `inconclusive`.
- No-signal outcome cannot be marked pass unless predeclared policy permits extension, not promotion.
- Idempotency key and broker client order ID are required.
- Timeout triggers reconcile before retry unless idempotency proves retry safe.
- Clock health is required.
- Stale data blocks orders.
- Reconciliation is required before and after trading cycles.
- Rollback/flatten follows plan.
- Unresolved incidents block production eligibility.

### CLI

```bash
uv run tradingx live-probe-plan-check --probe-id ...
uv run tradingx run-live-probe --probe-id ...
uv run tradingx safety-drill --type kill_switch
uv run tradingx reconcile-live-state
uv run tradingx live-probe-recertify --probe-id ...
```

### Migration

Existing live/paper evidence is `legacy_live_probe_evidence` unless it has approved plan, authority boundary, limits, success criteria, rollback criteria, minimum activity record, reconciliation artifacts, drill evidence, and recertification report.

### Enforcement

Promotion blocks above `tiny_live_probe` if minimum activity is not met, probe inconclusive, drill evidence stale, authority boundary missing, broker-timeout state machine missing, post-probe recertification missing, unresolved incident exists, idempotency/reconciliation evidence missing, or broker anomaly unresolved.

Runtime blocks live probe if authority approval invalid, plan expired, clock health invalid, kill switch unavailable, idempotency unavailable, stale-data checks unavailable, or reconciliation unavailable.

### Acceptance Criteria

- Live-probe plans define limits, activity, success, rollback, and authority.
- Safety drills have freshness windows.
- Minimum activity gates pass/fail/inconclusive.
- Broker-timeout state machine is defined and tested.
- Idempotency spans intent hash and broker client order ID.
- Reconciliation incidents are artifacted.
- Manual exceptions are signed, scoped, expiring, and cannot disable core controls.
- Flatten behavior is explicit.
- Clock health is enforced.
- Post-probe recertification is required for production eligibility.
- Unresolved incidents block production.

## Milestone 10: Recertification & Change Control

### Goal

Make production approval expiring, evidence-bound, dependency-aware, and invalidated by unknown, unrecorded, material, critical, or breaking changes until replay equivalence or full recertification succeeds under role-bounded authority.

### Core Rule

Production approval is expiring evidence, not a permanent state. Any unknown, unrecorded, material, critical, dependency-unresolved, or breaking-schema change blocks production until resolved.

### Primary Files

- `src/tradingx/change_control.py`
- `src/tradingx/promotion.py`
- `src/tradingx/activation.py`
- `src/tradingx/runtime_strategy_registry.py`
- `src/tradingx/live_enablement.py`
- `src/tradingx/validation.py`
- `src/tradingx/experiments.py`
- `src/tradingx/data_fingerprint.py`
- `src/tradingx/drift/`
- `src/tradingx/__main__.py`
- `config/strategy/promotion/<strategy_id>.json`
- `schemas/quant/change_control_record.schema.json`
- `schemas/quant/evidence_invalidation_report.schema.json`
- `schemas/quant/replay_equivalence_report.schema.json`
- `schemas/quant/recertification_report.schema.json`
- `schemas/quant/production_decay_event.schema.json`
- `tests/fixtures/change_control/`

### Milestone 1 Amendment

Promotion state projection gains:

- `production_approved_at_utc`
- `production_expires_at_utc`
- `last_recertification_report_id`
- `next_operational_review_due_utc`
- `next_statistical_review_due_utc`

These fields are derived from the append-only decision/recertification ledger. They are not an approval source of truth.

### Schemas

`change_control_record` records change ID, type, scope, unknown-scope flag, affected strategies, affected evidence refs, dependency index refs, materiality class, automatic classification, manual classification, confidence, classifier version, change hash, git SHAs, creator, replay requirement, recertification requirement, schema compatibility, and approval ref.

Automatic git diff classification is advisory only. Manual classification overrides it. Low confidence requires review. Unknown scope defaults to `critical`.

`replay_equivalence_report` records old/new artifacts, metric deltas, decision deltas, trade deltas, safety rule deltas, equivalence status, and blockers. Replay equivalence fails if any V5 materiality default fires.

`recertification_report` records production state before/after, reason, authority ref, risk accepted, evidence refs, freshness/statistical/cost-capacity/optimizer/live-probe/drift/incident statuses, approval status, approval, production expiry, next review due dates, and blockers.

Critical recertification requires two approvers through Milestone 9 authority boundary semantics.

`production_decay_event` records strategy, decay reason, previous/new state, triggering artifact, timestamp, and operator notification.

### Materiality Classes

Minor:

- docs-only
- UI-only display
- non-semantic refactor with replay equivalence

Material:

- strategy/model/feature/label code change
- data vendor/restatement
- cost/capacity model change
- optimizer/utility/lambda change
- broker API behavior change
- calendar/session logic change
- risk control change
- schema migration required

Critical:

- unknown change scope
- live incident
- reconciliation mismatch
- duplicate order
- unresolved broker anomaly
- kill-switch failure
- safety-control regression
- production safety rule change
- breaking schema change without migration

### Bypass Detection

If current code/data/config/schema hash differs from the last approved artifact and no `change_control_record` exists:

- blocker: `unrecorded_material_change`
- production blocked

Change impact must be resolved through the Milestone 3 dependency index, not only manual lists. If affected evidence cannot be enumerated:

- blocker: `dependency_scope_unresolved`
- production blocked

### Recertification Triggers

Immediate recertification or demotion when:

- production expiry passed
- operational/statistical review due date passed
- evidence stale
- data restatement affects evidence
- vendor/broker/API/schema changes
- model/feature/optimizer/risk/cost/capacity changes
- utility/lambda changes
- universe changes
- live drift monitor fails
- quote quality degrades
- strategy inactive beyond window
- live probe incident unresolved
- emergency control fires
- unrecorded material change detected

Periodic:

- monthly operational review
- quarterly statistical review
- immediate review after material/critical change

### Inactivity Decay

Production decays to `paper_shadow` if:

- no trades for predeclared inactivity window
- cost evidence stale
- borrow/shortability evidence stale
- live regime materially differs from last active period
- venue/broker behavior changed

### Enforcement

Production blocks if:

- current hash differs from approved hash and no change record exists
- change scope unknown
- dependency scope unresolved
- production expiry passed
- operational/statistical review due date passed
- recertification authority invalid
- breaking schema change lacks migration
- required replay missing or failed
- stale evidence
- inactive beyond window
- unresolved incident

Runtime live path checks approval freshness before each cycle and before order submission.

### CLI

```bash
uv run tradingx change-record --type code --scope ...
uv run tradingx replay-equivalence --change-id ...
uv run tradingx recertify-strategy --strategy-id ...
uv run tradingx production-decay-check --strategy-id ...
```

### Manual Exception Rule

Manual exceptions:

- expire
- cannot extend production indefinitely
- cannot bypass critical safety invalidation
- cannot disable kill switch, reconciliation, stale-data checks, idempotency, or dependency-scope resolution

### Migration

Existing production/paper approvals without recertification metadata become `legacy_approval`. They cannot support ongoing production until recertified. Breaking schema changes invalidate dependent artifacts until migrated.

### Acceptance Criteria

- Every material/critical change gets a `change_id`.
- Unknown scope defaults critical.
- Unrecorded hash differences block production.
- Dependency index resolves affected evidence.
- Replay-equivalence uses V5 materiality defaults.
- Material/critical changes invalidate or recertify affected evidence.
- Production approval expires without recertification.
- Operational/statistical due dates are enforced.
- Inactive strategies decay.
- Unresolved incidents block production.
- Activation/runtime enforce approval freshness every cycle and before orders.
- Monthly/quarterly recertification artifacts exist.
- Golden replay reproduces valid, stale, invalidated, unrecorded, and recertified outcomes from artifacts alone.

## Initial Implementation Order

The first implementation slice is Milestone 1 only, and it must include the full enforcement chain:

```text
schema -> artifact -> blocker -> CLI report -> activation refusal -> golden replay
```

For Milestone 1 specifically, that means:

```text
ledger schema -> signed decision/evidence fixture -> blocker evaluator -> promotion-check CLI -> activation refusal -> projection-drift and replay fixtures
```

Recommended execution waves:

1. Governance spine: Milestone 1.
2. Evidence provenance: Milestones 2 and 3.
3. Statistical and economic evidence: Milestones 4 and 5.
4. Portfolio and sizing: Milestones 6 and 7.
5. Runtime semantics and operations: Milestones 8 and 9.
6. Production lifecycle: Milestone 10.

Every wave must leave the system safer than it found it. A partially implemented milestone should add blockers and classification before adding any new pathway to promotion.

## Non-Goals

This plan does not:

- promise profitability
- claim any current strategy has production-grade edge
- authorize live shorting
- authorize production optimizer use
- authorize Kelly sizing
- replace human approval for production decisions
- replace legal, tax, compliance, or broker-specific review

It defines the evidence, artifacts, replay paths, blockers, and operational controls required before those claims can be responsibly made.
