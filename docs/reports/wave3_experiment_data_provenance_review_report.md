# Wave 3 Experiment Registration And Data Provenance Review Report

## W3-001

Severity: blocker

Affected file or component: `src/tradingx/__main__.py`, `src/tradingx/web/runtime.py`, `src/tradingx/experiments.py`, `src/tradingx/validation.py`

Roadmap requirement involved: Wave 3 tasks 1-3 and 8; Milestone 2 integrity rules requiring committed registration/run-start records before metrics are computed or displayed, registered run tokens before metric computation, metric-vault release before metric exposure, and promotion-scope-aware append-only evidence; Milestone 3 enforcement requiring promotion-valid evidence to reference dataset manifests.

Exact issue: `gate-report` and the web gate action allow the caller to self-assert a released, promotion-valid experiment context with arbitrary strings. No experiment ledger, run-start record, metric-vault release record, or dataset manifest is loaded or validated before metrics are computed and returned. A non-empty `--metric-release-token` flips the context to released, and a non-empty `--dataset-manifest-id` is enough for `apply_metric_visibility_to_report` to mark the report `promotion_valid=True`.

Evidence from code, diff, tests, or validation output: In `src/tradingx/__main__.py`, lines 1022-1031 construct `MetricVisibilityContext(... promotion_valid=True, metric_vault_release_status="released" if args.metric_release_token else "pending")` from CLI arguments only. `src/tradingx/web/runtime.py` lines 552-564 repeats the same behavior for web actions. `src/tradingx/experiments.py` lines 260-285 marks a released context with any `dataset_manifest_id` as `promotion_valid=True` and `evidence_class="valid"`. The `gate-report` parser has no ledger-root, registration-file, run-record, or dataset-manifest path argument in `src/tradingx/__main__.py` lines 295-302.

Why it matters: A post-result, nonexistent, or unregistered experiment can be made promotion-valid by supplying fake experiment/run/token/dataset strings. That defeats the pre-result boundary and allows hidden selection, look-ahead, and unvalidated data provenance to support promotion.

Required fix: Require `gate-report` and web gate actions to resolve a real experiment registration, run-start lifecycle record, metric-vault release record, and dataset manifest from an append-only ledger/CAS before any metric computation or release. If any registration/run/release/dataset requirement is missing or contaminated, fail closed as exploratory/non-promotable and do not compute promotion-valid metrics.

Required test or validation to prove the fix: Add CLI and web integration tests where fake `experiment_id`, `run_id`, release token, and dataset id are supplied without ledger records. The test must assert metrics are not computed or emitted and blockers include `trial_lineage_contaminated` and/or `point_in_time_data_incomplete`. Add a positive test that only a committed pre-result registration, committed run-start record, valid release token, and valid dataset manifest can produce `promotion_valid=True`.

## W3-002

Severity: blocker

Affected file or component: `src/tradingx/data_fingerprint.py`, `src/tradingx/__main__.py`, `tests/unit/test_data_fingerprint.py`

Roadmap requirement involved: Milestone 3 core rule and acceptance criteria requiring raw vendor payload hashes, normalized frame hashes, retained replay inputs, data-level restatement detection, manual review when old raw data is unavailable and normalized data changed, and replay-proven invalidation; Wave 3 tasks 8-9.

Exact issue: Dataset restatement comparison ignores raw payload hash changes, normalized frame hash changes, normalization code hash changes, and normalization policy hash changes. The CLI cannot provide return deltas, replay deltas, or raw-payload availability, and the function always reports `raw_payload_availability="available"` and `manual_review_required=False`.

Evidence from code, diff, tests, or validation output: `src/tradingx/data_fingerprint.py` lines 164-184 compares selected policies/refs but omits `raw_payload_hashes`, `normalized_frame_hashes`, `normalization_code_hash`, and `normalization_policy_hash`. Lines 219-241 derive `evidence_status` only from those limited flags and hard-code raw availability/manual-review fields. `src/tradingx/__main__.py` lines 965-968 calls `compare_dataset_manifests` with only old/new manifests. A review check changing only `raw_payload_hashes` and `normalized_frame_hashes` returned `evidence_status == "valid"` and an empty materiality flag list. The new test coverage in `tests/unit/test_data_fingerprint.py` lines 73-95 exercises a corporate-action hash plus injected deltas, not the raw/normalized replay-input change path.

Why it matters: A vendor restatement that changes retained raw or normalized data can be classified as valid. That allows stale or invalid evidence to survive promotion and breaks the roadmap's replay and restatement guarantees.

Required fix: Compare every provenance field that defines replay validity, including raw payload hashes, normalized frame hashes, normalization code/policy hashes, raw/normalized refs, benchmark/cash inputs, and bitemporal timestamps. Treat raw or normalized content changes as data-level materiality requiring replay. Represent old raw availability explicitly; if old raw data is unavailable and normalized data changed, emit `manual_review_required` and cap promotion accordingly. Extend the CLI to accept or compute materiality/replay inputs instead of using hard-coded defaults.

Required test or validation to prove the fix: Add tests where only `raw_payload_hashes` or `normalized_frame_hashes` differ and assert `evidence_status == "stale"` with `required_action == "replay_required"`. Add a test where old raw payloads are unavailable and normalized hashes differ and assert `manual_review_required=True`. Add a CLI test proving the same behavior through `compare-dataset`.

## W3-003

Severity: high

Affected file or component: `src/tradingx/data_fingerprint.py`, `schemas/quant/dataset_manifest.schema.json`

Roadmap requirement involved: Milestone 3 core rule requiring raw vendor payload hashes, raw artifact refs, normalized frame hashes, normalized frame artifact refs, retained inputs, and the rule that a hash without retained inputs is not replay-valid.

Exact issue: `build_dataset_manifest` fabricates raw and normalized hashes by hashing the reference string, not the retained artifact bytes or normalized frame content. `dataset_manifest_blocker_codes` only checks that ref/hash sequences are non-empty, so arbitrary missing paths or non-hash strings satisfy replay-path checks.

Evidence from code, diff, tests, or validation output: `src/tradingx/data_fingerprint.py` lines 134-141 computes `raw_payload_hashes` and `normalized_frame_hashes` as `canonical_payload_hash({"ref": ref})`. Lines 43-51 only test for non-empty fields. The dataset manifest schema at `schemas/quant/dataset_manifest.schema.json` lines 70-78 declares arrays/strings without minItems, content-addressed format, or hash-pattern constraints. A review check using refs and hashes such as `not-a-cas-ref`, `missing-file`, and `not-a-hash` returned no blocker codes.

Why it matters: The manifest can claim replayability without retaining or hashing the actual data. Data changes behind a stable path/ref are invisible, and bogus refs can support promotion-valid evidence.

Required fix: Require content-addressed artifact refs and actual content hashes for raw payloads and normalized frames. Either compute hashes from retained bytes/frames or require explicit hashes and verify them against CAS artifacts. Strengthen the schema and blocker logic to reject empty arrays, non-hash values, inaccessible refs, and refs whose content hash does not match.

Required test or validation to prove the fix: Add a manifest build test using real retained raw and normalized artifact files and assert hashes equal the content hashes. Add negative tests where refs are missing, non-content-addressed, or hash mismatched and assert `replay_path_missing`.

## W3-004

Severity: blocker

Affected file or component: `src/tradingx/experiments.py`, `src/tradingx/__main__.py`

Roadmap requirement involved: Milestone 2 schemas and integrity rules requiring experiment run records to record every lifecycle state (`started`, `completed`, `failed`, `canceled`), run-start records to be committed before metrics, and failed/canceled runs to remain in the universe; Wave 3 task 1.

Exact issue: A single run cannot progress through the required append-only lifecycle. `start-experiment-run` and `complete-experiment-run` both call `append_run_record`, but `append_run_record` treats `run_id` as the unique immutable identity. A later `completed`, `failed`, or `canceled` record for the same `run_id` necessarily has a different payload and is rejected as a changed duplicate.

Evidence from code, diff, tests, or validation output: `src/tradingx/__main__.py` lines 904-913 handles both start and complete commands through `ledger.append_run_record(payload)`. `src/tradingx/experiments.py` lines 312-313 calls `_append_unique(... identity_field="run_id")`. `_append_unique` returns only for identical payload hashes and raises `ExperimentLedgerError` for the same identity with different payload at lines 341-347. Tests only validate one completed fixture and do not cover start-then-complete for the same run.

Why it matters: The ledger cannot prove that a run-start token existed before metrics were computed. Implementations must either skip the `started` event or invent a new run id for completion, both of which break the lifecycle chain and weaken failed/canceled-run accounting.

Required fix: Model run lifecycle as append-only events with an event id/sequence or identity `(run_id, lifecycle_status, lifecycle_sequence)`, while deriving one logical run from those events. Enforce valid transitions, require a `started` event before terminal events and metric release, and keep failed/canceled/no-metric terminal events in the promotion universe.

Required test or validation to prove the fix: Add a ledger/CLI test that appends `started` then `completed` for the same `run_id` and succeeds. Add tests that `completed` without `started` fails closed, duplicate identical lifecycle events are idempotent, and changed duplicate event payloads raise a ledger-integrity error.

## W3-005

Severity: high

Affected file or component: `src/tradingx/experiments.py`

Roadmap requirement involved: Milestone 2 universe definition and integrity rules requiring `U` to be built from registered experiments and child run records in the same promotion scope, unregistered metric-bearing work to contaminate lineage, and registered/unregistered work not to be hidden.

Exact issue: `build_trial_universe_manifest` accepts scoped run records whose `experiment_id` has no scoped registration. With no registrations and one released run record, the manifest can be `complete`, contain no blockers, list the orphan run id, and count it as metric-bearing despite `registered_trial_count == 0`.

Evidence from code, diff, tests, or validation output: `src/tradingx/experiments.py` lines 373-383 independently selects scoped registrations and scoped runs. Lines 407-410 only check registered experiments missing run records; there is no reverse check for run records missing registrations. Lines 497-501 count released completed runs as metric-bearing regardless of registration. A review check with `registrations=[]` and one released run returned `status="complete"`, `blocker_codes=[]`, `run_ids=["run-orphan"]`, `registered_trial_count=0`, and `metric_bearing_trial_count=1`.

Why it matters: Unregistered metric-bearing runs can enter the trial universe and its statistics, allowing post-result or hidden experiments to affect promotion evidence without contamination.

Required fix: Join run records to valid pre-result registrations by `promotion_decision_scope` and `experiment_id`. Any scoped run without a valid scoped registration must be `trial_lineage_contaminated` or a ledger-integrity violation. Trial statistics should count only joined registration/run records and should explicitly report orphan/unregistered runs.

Required test or validation to prove the fix: Add a test with no registrations and a released run record and assert the manifest is contaminated, the orphan run is reported, and metric-bearing registered count remains zero. Add a test with a run whose experiment id is outside the promotion scope and assert it cannot enter `U`.

## W3-006

Severity: high

Affected file or component: `src/tradingx/evaluation.py`, `src/tradingx/validation.py`, `src/tradingx/trials.py`

Roadmap requirement involved: Milestone 2 core rule requiring promotion-valid DSR/PBO/MCS evidence to use only the registered experiment universe, excluding legacy family-wide trials and unregistered experiments; Wave 3 exit criterion that legacy trials cannot support DSR/PBO/MCS promotion claims.

Exact issue: Deflated-Sharpe inputs still come from the legacy `TrialsLedger` family table, not from a Wave 3 promotion-scope trial universe manifest. New gate runs continue to write anonymous UUID trial rows keyed only by `family`, with no experiment id, run id, promotion decision scope, lifecycle status, metric visibility, dataset fingerprint, failed/canceled/no-metric treatment, or child perturbation lineage.

Evidence from code, diff, tests, or validation output: `src/tradingx/evaluation.py` lines 437-445 calls `trials_ledger.trial_statistics_for_family(candidate.family)`. `src/tradingx/trials.py` lines 131-135 computes statistics with `SELECT observed_sharpe_net_of_costs FROM trials WHERE family = ?`. `src/tradingx/validation.py` lines 1203-1226 records trials using `uuid.uuid4()`, `candidate.family`, and metric fields only. No `ExperimentLedger` or `trial_universe_manifest` is involved in that path.

Why it matters: Legacy or unregistered trials can still influence DSR and selection-statistics calculations. Hidden trials remain hidden from the promotion-decision universe, and failed/canceled/no-metric runs are not conservatively represented in the statistics.

Required fix: Replace family-wide `TrialsLedger` statistics in promotion-valid validation with stats derived from the Wave 3 `trial_universe_manifest` scoped by `promotion_decision_scope`. Classify legacy ledger rows as exploratory/non-promotable unless linked to registered run records. Include failed, canceled, omitted, no-metric, and child perturbation runs with a predeclared conservative treatment.

Required test or validation to prove the fix: Seed a legacy `TrialsLedger` with high-Sharpe unregistered rows and assert DSR/PBO/MCS readiness remains blocked for promotion-valid evidence. Seed a valid Wave 3 registered universe and assert only those records feed trial counts, selected rank, correlation estimate, failed-run penalty, and DSR inputs.

## W3-007

Severity: high

Affected file or component: `src/tradingx/persistence/__init__.py`, `src/tradingx/types.py`, `src/tradingx/reporting.py`, `src/tradingx/web/readmodels.py`, `src/tradingx/experiments.py`, `tests/unit/test_web_readmodels.py`

Roadmap requirement involved: Wave 3 tasks 2-5 requiring metric-vault enforcement in the shared report writer and every orchestration surface, an explicit visibility/taint model through metric-producing APIs and artifact writers, and leak-detection tests proving sentinel metrics do not appear in artifacts, logs, web responses, read models, or report summaries before release.

Exact issue: Metric visibility is not enforced in shared artifact writers or most metric-producing types. The artifact store serializes metric-bearing reports/evidence directly. `EvaluationEvidencePack` has no visibility context. The only generic fail-closed function, `assert_metric_visibility_allowed`, is never called in production code. Web read-model redaction works only if a context is already present in persisted JSON, and the test manually mutates that context into the JSON after writing the metric-bearing artifact.

Evidence from code, diff, tests, or validation output: `src/tradingx/persistence/__init__.py` lines 100-105 writes `EvaluationEvidencePack` directly, and lines 307-312 writes `ValidationReport` directly. `src/tradingx/types.py` lines 90-109 defines `EvaluationEvidencePack` with metric fields but no visibility context. `src/tradingx/reporting.py` lines 61-63 reads raw validation reports and gate assessments with no sanitization. `rg` found `assert_metric_visibility_allowed` only at its definition/export. `tests/unit/test_web_readmodels.py` lines 230-259 writes an evidence pack containing sentinel metrics and then manually edits the JSON to add `metric_visibility_context`.

Why it matters: A promotion-valid caller can persist metric-bearing artifacts before release unless it happens to use the newly wrapped gate-report path exactly. Tests hide the integration gap by injecting the context after the unsafe write. Report summaries and artifact JSON can still leak sealed metrics.

Required fix: Add `MetricVisibilityContext` or an equivalent taint field to all metric-bearing return types and artifact writers. Enforce fail-closed behavior in `FilesystemArtifactStore` or specific metric-bearing writers before serialization. Sanitize or reject report summaries and web/read-model payloads based on persisted context, and reject promotion-valid metric writes with missing context.

Required test or validation to prove the fix: Add an integration test that passes an unreleased promotion-valid context through the real evaluation/report writer and then builds the reporting brief and web read model without manual JSON mutation. The sentinel metric must be absent or the write must raise. Add a negative test proving a promotion-valid metric-bearing artifact with no visibility context is rejected.

## W3-008

Severity: high

Affected file or component: `src/tradingx/data_fingerprint.py`, `src/tradingx/__main__.py`

Roadmap requirement involved: Milestone 3 evidence dependency index and invalidation requirements mapping `dataset_id` to evidence packs, experiments, gate reports, and promotion decisions; acceptance criterion that the dependency index lists affected evidence from `dataset_id`; Wave 3 task 10.

Exact issue: Evidence invalidation can succeed with no dependency index or with an index that lacks the old dataset id, returning an empty affected set. Even when the index has experiment, gate report, or promotion decision refs, `invalidate_evidence_from_restatement` only emits `evidence_pack_ids` as `affected_evidence_refs` and drops the other dependency classes.

Evidence from code, diff, tests, or validation output: `src/tradingx/__main__.py` lines 980-986 builds an empty dependency index when `--dependency-index` is omitted. `src/tradingx/data_fingerprint.py` lines 289-317 defaults `affected` to `{}` and returns a report regardless of whether old dataset dependencies were found. Line 301 emits only `affected.get("evidence_pack_ids", [])`, while `build_evidence_dependency_index` stores `experiment_ids`, `gate_report_ids`, and `promotion_decision_ids` at lines 258-261.

Why it matters: A material restatement can produce an invalidation report that appears complete while affected gate reports or promotion decisions remain undiscovered. That hides stale/invalid evidence and breaks replay-based invalidation.

Required fix: Require a dependency index for material restatements. If the old dataset id is absent or affected dependencies cannot be enumerated, fail closed with an explicit unresolved-dependency blocker/status. Include evidence packs, experiments, gate reports, and promotion decisions in the invalidation report.

Required test or validation to prove the fix: Add tests where a material restatement is invalidated without an index and with an index missing the old dataset id; both must fail closed or emit unresolved dependency status. Add a test where the old dataset maps only to a gate report or promotion decision and assert those refs appear in the invalidation report and block promotion.

## W3-009

Severity: medium

Affected file or component: `schemas/quant/*.schema.json`, `src/tradingx/experiments.py`, `src/tradingx/promotion.py`

Roadmap requirement involved: Milestone 2 and 3 schema/integrity requirements, including required lifecycle fields, monotonic registration sequence, duplicate sequence as `ledger_integrity_violation`, same id with different payload as `ledger_integrity_violation`, and immutable artifact/hash requirements.

Exact issue: The new schemas and ledger validation are too permissive for the roadmap invariants. Schemas allow arbitrary extra properties and weak strings, the run schema does not require all fields that Milestone 2 says every run record records, append methods do not validate schema payloads, and duplicate registration sequences are downgraded to `trial_universe_incomplete` rather than `ledger_integrity_violation`.

Evidence from code, diff, tests, or validation output: Each new schema uses `"additionalProperties": true`, for example `schemas/quant/experiment_registration.schema.json` line 5 and `schemas/quant/dataset_manifest.schema.json` line 5. `schemas/quant/experiment_run_record.schema.json` lines 6-23 does not require `metrics_visible_at_utc`, `metric_release_token_ref`, or `partial_metric_payload_hash` even though Milestone 2 lists them as run-record fields. `src/tradingx/experiments.py` lines 305-313 appends registrations/runs without schema validation. Duplicate registration sequences are mapped to `trial_universe_incomplete` in `src/tradingx/experiments.py` lines 398-405. `ledger_integrity_violation` is not present in the blocker registry search results, while roadmap requires it for duplicate sequence and changed payload cases.

Why it matters: Malformed or incomplete records can be written to the ledger and later interpreted as evidence. Ledger-integrity failures are under-classified, which can allow a weaker state cap than intended and obscure broken append-only ordering.

Required fix: Validate registrations, run records, amendments, manifests, restatement reports, dependency indexes, and invalidation reports before append/output. Strengthen schemas with required lifecycle fields, enums, min lengths, hash/ref patterns, minItems, and stricter additional-property handling where feasible. Add `ledger_integrity_violation` to the blocker registry and emit it for duplicate sequences and changed-payload ledger conflicts.

Required test or validation to prove the fix: Add negative schema/ledger tests for missing `metrics_visible_at_utc`, missing `metric_release_token_ref`, bad hash strings, bogus refs, extra unknown fields where disallowed, duplicate registration sequences, and changed duplicate payloads. Assert duplicate sequence yields `ledger_integrity_violation` and the strictest promotion cap expected by the blocker registry.
