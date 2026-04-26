# Wave 1C Review Package - Promotion Evaluation, Contracts, CLI

Roadmap slice: Wave 1C.

Files in scope:

- `src/tradingx/promotion.py`
- `src/tradingx/__main__.py`
- `schemas/quant/promotion_manifest.schema.json`
- `tests/unit/test_promotion.py`
- `tests/unit/test_main.py`
- `tests/unit/test_blocker_registry.py`
- `tests/fixtures/promotion/`

Implemented evidence:

- `evaluate_promotion_manifest` loads fixture artifacts, applies deterministic strictest-cap logic, and emits blockers for missing key/WORM policy, missing replay input, unsupported negative target weights without short capability, and explicit fixture blockers.
- `validate_state_action_contracts` rejects action permissions above each promotion state.
- `promotion-check` emits JSON by default and a human-readable summary with `--format summary`.
- Golden fixture directories exist for valid, legacy, stale, invalid, projection drift, unsigned approval, key-policy missing, sequence gap, missing replay input, unsupported short side, and paper-shadow placeholder cases.

Validation evidence:

- `uv run pytest tests/unit/test_promotion.py tests/unit/test_main.py::test_promotion_check_reports_blockers_from_fixture_artifacts tests/unit/test_main.py::test_promotion_check_summary_format_reports_state_and_blockers tests/unit/test_blocker_registry.py`
- `uv run ruff check .`
- `uv run mypy src/tradingx`

