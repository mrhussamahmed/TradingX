# Wave 3 Experiment Registration And Data Provenance Implementation Report

Wave: Wave 3 - Experiment Registration And Data Provenance

Roadmap requirements covered:

- Added append-only experiment registration, run lifecycle, amendment, and trial-universe manifest schemas.
- Added experiment ledger helpers with idempotent duplicate handling only when canonical payload hashes match.
- Added trial-universe construction scoped by `promotion_decision_scope`, including failed/canceled runs, missing-run detection, post-result contamination, unregistered metric-bearing artifact contamination, outside-exploration attestation checks, immutable source/output checks, and DSR universe statistics.
- Added explicit `MetricVisibilityContext` and metric-vault redaction helpers.
- Threaded metric visibility through `build_gate_report`, `GateValidationController.generate_gate_report`, `gate-report` CLI, web gate actions, web read models, and structured runtime logging.
- Made gate reports without experiment context exploratory and non-promotable.
- Made promotion-valid released gate reports require a dataset manifest ID; missing dataset provenance emits `point_in_time_data_incomplete`.
- Added dataset manifest, restatement report, dependency index, and invalidation schemas.
- Added dataset manifest replayability checks for point-in-time universe membership, symbol mapping, delisting inputs, bitemporal vendor timestamps, retained raw payload refs, normalized frame refs, and normalization/code/policy hashes.
- Added data restatement comparison and evidence invalidation helpers and CLI commands.
- Added promotion blocker evaluation for trial-universe, dataset, restatement, and invalidation artifacts.
- Added golden fixtures under `tests/fixtures/experiments/` and `tests/fixtures/data_fingerprints/`.

Files changed:

- `schemas/quant/experiment_registration.schema.json`
- `schemas/quant/experiment_run_record.schema.json`
- `schemas/quant/experiment_amendment_record.schema.json`
- `schemas/quant/trial_universe_manifest.schema.json`
- `schemas/quant/dataset_manifest.schema.json`
- `schemas/quant/data_restatement_report.schema.json`
- `schemas/quant/evidence_dependency_index.schema.json`
- `schemas/quant/evidence_invalidation_report.schema.json`
- `src/tradingx/experiments.py`
- `src/tradingx/data_fingerprint.py`
- `src/tradingx/trials.py`
- `src/tradingx/types.py`
- `src/tradingx/validation.py`
- `src/tradingx/controller.py`
- `src/tradingx/__main__.py`
- `src/tradingx/runtime_logging.py`
- `src/tradingx/promotion.py`
- `src/tradingx/web/app.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/web/readmodels.py`
- `tests/fixtures/experiments/`
- `tests/fixtures/data_fingerprints/`
- `tests/unit/test_experiments.py`
- `tests/unit/test_data_fingerprint.py`
- `tests/unit/test_trials.py`
- `tests/unit/test_validation.py`
- `tests/unit/test_controller_generate_gate_report_cpcv.py`
- `tests/unit/test_main.py`
- `tests/unit/test_promotion.py`
- `tests/unit/test_web_readmodels.py`

Tests added or updated:

- Added experiment/trial-universe tests for post-result contamination, failed/canceled omission, unregistered metric notebook contamination, metric-vault redaction, structured log redaction, ledger duplicate integrity, and schema fixture validation.
- Added data fingerprint tests for missing point-in-time data, replay-input missing hashes, restatement materiality, dependency index mapping, and schema fixture validation.
- Added tests for append-only run lifecycle events, schema-backed ledger rejection, orphan-run contamination, terminal-without-start contamination, metric context resolution, artifact writer metric-visibility enforcement, content hashing from retained input files, unresolved dependency indexes, and CLI/web fail-closed metric-context handling.
- Updated validation tests for exploratory non-promotable unregistered gate reports, unreleased metric-vault blocking, dataset-manifest enforcement, and legacy-trials exclusion for promotion-valid DSR paths.
- Updated controller, CLI, promotion, web runtime, web read model, and trial-ledger tests for Wave 3 behavior.

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
- Black check on Wave 3 touched Python files: passed.
- Artifact index validation: passed.
- `UV_CACHE_DIR=/tmp/uv-cache ./scripts/validate`: passed artifact index and Ruff, then failed at repository-wide Black check on 24 pre-existing files outside the Wave 3 touched-file set.

Failures found and fixed:

- Initial red tests failed for missing `tradingx.experiments`, `tradingx.data_fingerprint`, CLI arguments, metric visibility threading, and provenance blocker evaluation.
- Schema fixture validation initially failed because the local schema validator does not support `minLength`, `minimum`, or `date-time`; Wave 3 schemas were changed to supported keywords and `utc-datetime`.
- Existing `TrialsLedger` behavior silently ignored duplicate trial IDs with changed payloads; it now raises `TrialsLedgerIntegrityError`, and the existing ledger test was updated to distinguish idempotent identical duplicates from changed duplicates.
- Mypy initially rejected untyped redaction payloads and reused CLI local variable types; payload types and local variable names were fixed.
- Ruff initially found unused imports, long test names, and import sorting; these were fixed.
- Wave 3 review found nine issues covering fake release assertions, incomplete restatement comparison, fabricated data hashes, impossible run lifecycle progression, orphan runs, legacy DSR inputs, artifact metric leaks, unresolved invalidation indexes, and permissive schemas. These were fixed and covered by tests.
- Touched-file Black initially failed on Wave 3 files after review-fix edits; `src/tradingx/data_fingerprint.py`, `src/tradingx/experiments.py`, `src/tradingx/web/runtime.py`, `tests/unit/test_main.py`, and `tests/unit/test_web_runtime.py` were formatted.

Assumptions made:

- A `MetricVisibilityContext` with no experiment ID means exploratory/non-promotable evidence rather than promotion-valid evidence.
- A promotion-valid metric context requires both `metric_vault_release_status="released"` and a non-empty `metric_release_token_ref` before metrics can cross report, CLI, web, artifact, or log surfaces.
- A released promotion-valid gate report without a `dataset_manifest_id` is not promotion-valid and receives `point_in_time_data_incomplete`.
- Existing broad legacy `TrialsLedger` records are treated as historical exploratory records unless wrapped by Wave 3 experiment registration artifacts.

Unresolved risks:

- `./scripts/validate` remains blocked by repository-wide Black formatting drift in files not touched by Wave 3.
- Wave 3 implements deterministic local manifest and ledger enforcement; it does not add remote WORM storage, external metric-vault service integration, or broker/vendor raw-payload retention beyond content-addressed refs.

Commit hash:

- Not committed yet at report write time.
