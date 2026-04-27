# Wave 7 Short-Side Capability And Financing — Handoff

Wave completed: yes

## Files changed

Source:

- `src/tradingx/short_governance.py` (new)
- `src/tradingx/promotion.py`

Schemas (new):

- `short_capability_manifest`, `borrow_availability_snapshot`,
  `short_financing_model`, `short_risk_report`, `short_runtime_event`.

Tests:

- `tests/unit/test_short_governance_wave7.py` (new)

Fixtures:

- `tests/fixtures/short_side/short_capability_manifest_complete.json`

Reports:

- `wave7_short_side_financing_implementation_report.md`
- `wave7_short_side_financing_review_loop1_report.md`
- `wave7_short_side_financing_review_loop1_fix_report.md`
- `wave7_short_side_financing_review_loop2_report.md`
- `wave7_short_side_financing_review_loop2_fix_report.md`
- `wave7_short_side_financing_handoff.md`

## Validation

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_short_governance_wave7.py -q`: 25 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_promotion.py tests/unit/test_blocker_registry.py -q`: passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration -q`: 1130 passed, 98 skipped.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`: clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`: clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run black --check <touched files>`: clean.
- `python3 scripts/check_index.py`: passed.

## Reviews

Two adversarial review loops completed. Loop 1 raised eight high
findings; loop 2 raised four highs and four mediums. Critical and
high findings fixed except where deferred/rejected with documented
rationale (registry override metadata for new wave_7 codes,
fixture-set completion, locate-expiry empty-string).

## Accepted residual risks

See `wave7_short_side_financing_implementation_report.md` section
"Accepted residual risks". Key items:

- Wave 7 registry seeds have synthetic coverage metadata (deferred to
  Wave 9).
- Fixture set is incomplete (deferred to Wave 9 / Wave 10).
- `locate_expiry_utc` empty-string semantics not enforced.
- No CLI subcommands for short artifacts.
- No runtime wiring of manifest/borrow snapshot to `risk.py` /
  `execution.py` / `runtime_portfolio.py` (deferred to Wave 8).
- `./scripts/validate` continues to fail on unrelated Black drift.
