# Wave 1A Review Package - Blocker Registry, Canonical Hashing, Schema Strategy, CAS

Roadmap slice: Wave 1A.

Files in scope:

- `src/tradingx/authority.py`
- `src/tradingx/promotion.py`
- `schemas/quant/blocker_registry.schema.json`
- `schemas/quant/promotion_manifest.schema.json`
- `tests/unit/test_authority.py`
- `tests/unit/test_blocker_registry.py`
- `tests/unit/test_promotion.py`
- `tests/fixtures/promotion/`

Implemented evidence:

- `canonical_json_dumps` and `canonical_payload_hash` normalize sorted keys, UTC datetimes, decimals as strings, and content-addressed refs.
- `FileContentAddressedStore` writes canonical JSON by SHA-256 digest using temp file, file fsync, atomic rename, and directory fsync.
- `validate_quant_artifact` is a closed-world validator with explicit supported schema keywords and format checks for decimal strings, SHA-256 refs, content-addressed refs, and UTC datetimes.
- `BLOCKER_REGISTRY` maps every first-slice blocker code to max state, condition, remediation, migration behavior, schema field, evaluator, fixture, red test, CLI output, and runtime enforcement fields.
- `blocker_registry_coverage_rows` provides the generated coverage matrix data used by registry coverage tests.

Validation evidence:

- `uv run pytest tests/unit/test_authority.py tests/unit/test_blocker_registry.py tests/unit/test_promotion.py`
- `uv run ruff check .`
- `uv run mypy src/tradingx`

