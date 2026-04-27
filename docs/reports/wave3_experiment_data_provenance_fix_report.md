# Wave 3 Experiment Registration And Data Provenance Fix Report

Wave: Wave 3 - Experiment Registration And Data Provenance

Source review report: `docs/reports/wave3_experiment_data_provenance_review_report.md`

Review loop status:

- One adversarial review report was already produced for Wave 3 before the user disabled further adversarial reviews.
- All findings from that report were fixed and validated.
- No further reviewer subagents were spawned after the user instruction to stop adversarial reviews.

Findings fixed:

- `W3-001`: CLI and web gate-report paths now resolve metric visibility from a real experiment ledger plus dataset manifest file. Fake experiment/run/token/dataset strings without ledger and dataset evidence fail closed with lineage and point-in-time blockers.
- `W3-002`: Dataset restatement comparison now includes raw payload refs/hashes, normalized frame refs/hashes, normalization code/policy hashes, vendor observation timestamps, and explicit old raw-payload availability. Normalized changes without old raw data require manual review.
- `W3-003`: Dataset manifest construction now hashes retained local input files into `sha256:` content refs, and replay blockers reject non-content-addressed refs and ref/hash mismatches.
- `W3-004`: Experiment run records are append-only lifecycle events keyed by `(run_id, lifecycle_status)`, allowing `started` then `completed` for the same logical run. Terminal runs without a `started` event contaminate lineage.
- `W3-005`: Trial-universe manifests now report orphan run experiment IDs, contaminate lineage for run records without registrations, and exclude orphan runs from registered metric-bearing trial counts.
- `W3-006`: Promotion-valid gate validation bypasses legacy family-wide `TrialsLedger` statistics and recording so legacy rows cannot support promotion-valid DSR evidence.
- `W3-007`: Metric-bearing `EvaluationEvidencePack` objects now carry promotion/visibility metadata, and `FilesystemArtifactStore.write_evaluation_evidence` rejects promotion-valid metrics without a released visibility context.
- `W3-008`: Evidence invalidation now fails closed when the dependency index is missing or does not include the old dataset, and it reports evidence, experiment, gate-report, and promotion-decision dependency classes.
- `W3-009`: New Wave 3 schemas are closed-world where feasible, ledger append methods validate registration/run/amendment payloads before writing, duplicate registration sequences emit `ledger_integrity_violation`, and generated manifests/reports validate before output.

Files changed for fixes:

- `src/tradingx/experiments.py`
- `src/tradingx/data_fingerprint.py`
- `src/tradingx/persistence/__init__.py`
- `src/tradingx/types.py`
- `src/tradingx/validation.py`
- `src/tradingx/__main__.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/web/app.py`
- `schemas/quant/*.schema.json`
- `tests/fixtures/experiments/trial_universe_manifest_complete.json`
- `tests/fixtures/data_fingerprints/dataset_manifest_complete.json`
- `tests/unit/test_experiments.py`
- `tests/unit/test_data_fingerprint.py`
- `tests/unit/test_main.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_web_runtime.py`

Tests added or updated:

- Ledger lifecycle append, duplicate payload integrity, schema validation, orphan-run contamination, duplicate sequence integrity, and terminal-without-start contamination tests.
- Metric visibility resolution tests for missing and valid ledger/dataset evidence.
- Artifact-store tests for promotion-valid metric evidence rejection and released context persistence.
- Dataset manifest content-hash, restatement raw/normalized materiality, manual review, invalid ref, unresolved dependency, and all dependency class tests.
- CLI tests for fake metric-context fail-closed behavior, valid ledger/dataset release behavior, old raw unavailable comparison behavior, and start-then-complete lifecycle append.
- Web runtime tests for fake metric-context fail-closed behavior and valid ledger/dataset release behavior.
- Validation test proving promotion-valid gate reports do not use the legacy trials ledger.

Validation commands run:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_experiments.py tests/unit/test_data_fingerprint.py tests/unit/test_main.py::test_gate_report_cli_threads_registered_metric_visibility_context tests/unit/test_main.py::test_gate_report_cli_fake_metric_context_fails_closed tests/unit/test_main.py::test_compare_dataset_cli_marks_manual_review_when_old_raw_unavailable tests/unit/test_main.py::test_experiment_run_cli_appends_started_then_completed_lifecycle tests/unit/test_validation.py::test_promotion_valid_gate_report_ignores_legacy_trials_ledger tests/unit/test_web_runtime.py::test_local_web_action_runner_fake_metric_context_fails_closed tests/unit/test_web_runtime.py::test_local_web_action_runner_resolves_released_metric_context`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_experiments.py tests/unit/test_data_fingerprint.py tests/unit/test_main.py tests/unit/test_validation.py tests/unit/test_web_runtime.py tests/unit/test_web_readmodels.py tests/unit/test_controller_generate_gate_report_cpcv.py tests/unit/test_controller.py tests/unit/test_promotion.py tests/unit/test_trials.py`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`
- `UV_CACHE_DIR=/tmp/uv-cache uv run black --check $(git diff --name-only -- '*.py')`
- `python3 scripts/check_index.py`
- `UV_CACHE_DIR=/tmp/uv-cache ./scripts/validate`

Validation results:

- Focused Wave 3 tests: `37 passed`.
- Affected Wave 3 suite: `201 passed`.
- Full unit/contract/integration suite: `1034 passed, 98 skipped, 13 warnings`.
- Ruff: passed.
- Mypy: passed with no issues in 112 source files.
- Touched-file Black check: passed.
- Artifact index validation: passed.
- `UV_CACHE_DIR=/tmp/uv-cache ./scripts/validate`: passed artifact index and Ruff, then failed at repository-wide Black on 24 files outside the Wave 3 touched-file set.

Unresolved risks:

- Repository-wide `./scripts/validate` remains blocked by unrelated pre-existing Black formatting drift outside Wave 3 files.
- No further adversarial review was run after these fixes because the user explicitly disabled adversarial reviews.

