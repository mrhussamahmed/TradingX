# Wave 4 Statistical Evidence Engine Implementation Report

Wave name: Statistical Evidence Engine

Roadmap requirements covered:

- Added threshold-justification artifacts; missing threshold emits `pending_threshold`.
- Added HAC-aware effective sample size and power reports with `effective_sample_size <= n_observations` and lag sensitivity.
- Added paired benchmark uncertainty reports for cash, 60/40, static sleeve baseline, and no-trade baselines.
- Added deterministic stationary block bootstrap reports with fixed seed, block-length sensitivity, and tail-stability status.
- Added statistical validation reports that require Wave 3 trial-universe DSR inputs.
- Added PBO full CPCV matrix reference threading and validation-report enforcement.
- Added promotion blocker consumption for underpowered, unstable, incomplete, exploratory, legacy, or pending statistical evidence.
- Added `statistical-report` CLI generation path.

Files changed:

- `src/tradingx/stats.py`
- `src/tradingx/promotion.py`
- `src/tradingx/__main__.py`
- `src/tradingx/pbo.py`
- `src/tradingx/persistence/__init__.py`
- `src/tradingx/types.py`
- `schemas/quant/threshold_justification.schema.json`
- `schemas/quant/power_analysis_report.schema.json`
- `schemas/quant/bootstrap_report.schema.json`
- `schemas/quant/paired_benchmark_uncertainty_report.schema.json`
- `schemas/quant/statistical_validation_report.schema.json`
- `tests/unit/test_statistical_evidence_wave4.py`
- `tests/unit/test_pbo_compute.py`
- `tests/unit/test_pbo_report.py`
- `tests/unit/test_main.py`
- `docs/reports/tradingx_quant_hardening_execution_tracker.md`
- `docs/reports/tradingx_quant_hardening_handover.md`

Tests added or updated:

- Added `tests/unit/test_statistical_evidence_wave4.py`.
- Updated `tests/unit/test_pbo_compute.py`.
- Updated `tests/unit/test_pbo_report.py`.
- Updated `tests/unit/test_main.py`.

Validation commands run:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_statistical_evidence_wave4.py tests/unit/test_pbo_compute.py tests/unit/test_pbo_report.py tests/unit/test_main.py -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_stats.py tests/unit/test_statistical_evidence_wave4.py tests/unit/test_promotion.py tests/unit/test_pbo_compute.py tests/unit/test_pbo_report.py tests/unit/test_main.py tests/unit/test_evaluation_evidence_pbo_fields.py -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`
- `UV_CACHE_DIR=/tmp/uv-cache uv run black --check src/tradingx/__main__.py src/tradingx/pbo.py src/tradingx/persistence/__init__.py src/tradingx/promotion.py src/tradingx/stats.py src/tradingx/types.py tests/unit/test_statistical_evidence_wave4.py tests/unit/test_pbo_compute.py tests/unit/test_pbo_report.py tests/unit/test_main.py`
- `python3 scripts/check_index.py`
- `UV_CACHE_DIR=/tmp/uv-cache ./scripts/validate`

Validation results:

- Focused Wave 4 tests passed.
- Affected statistical, promotion, PBO, CLI, and evidence tests passed.
- Full unit, contract, and integration suite exited 0; only existing `httpx` deprecation warnings were emitted.
- Ruff passed.
- Mypy passed.
- Touched-file Black check passed.
- Artifact index validation passed.
- `./scripts/validate` passed index and Ruff, then failed at repo-wide Black because of 24 unrelated pre-existing files outside Wave 4 touched files.

Failures found and fixed:

- The initial complete statistical-validation fixture was still underpowered under HAC effective sample-size adjustment. The fixture minimum effective sample-size requirement was corrected.
- Ruff required `zip(..., strict=True)` and line wrapping in new Wave 4 code.
- Black required formatting in `src/tradingx/stats.py`.

Assumptions made:

- The paired benchmark report treats missing or length-mismatched required baselines as incomplete evidence.
- Underpowered power reports, unstable bootstrap reports, missing DSR inputs, and missing PBO matrix references all map to `dsr_pbo_inputs_incomplete`, which caps promotion at `paper_shadow`.
- Legacy metric-only statistical payloads are classified as `legacy_statistical_evidence`.

Unresolved risks:

- Repo-wide `./scripts/validate` remains blocked by unrelated Black formatting drift outside Wave 4 files.
- No adversarial review was performed because the user explicitly stopped all adversarial reviews.

Commit hash:

- Pending at report creation.
