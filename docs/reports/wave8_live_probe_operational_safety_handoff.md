# Wave 8 Live Probe And Operational Safety — Handoff

Wave completed: yes

## Files changed

Source: `src/tradingx/live_probe_governance.py` (new),
`src/tradingx/promotion.py`.

Schemas (new): `authority_boundary`, `pre_trade_control_manifest`,
`operational_safety_drill`, `live_probe_plan`, `live_probe_run_record`,
`live_probe_recertification_report`,
`broker_timeout_state_transition`, `runtime_override_event`,
`reconciliation_incident`.

Tests: `tests/unit/test_live_probe_governance_wave8.py` (new).

Reports: implementation/handoff/loop1/loop2 + fix reports under
`docs/reports/wave8_live_probe_operational_safety_*.md`.

## Validation

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_live_probe_governance_wave8.py -q`: 21 passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_promotion.py tests/unit/test_blocker_registry.py -q`: passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit tests/contract tests/integration -q`: 1151 passed, 98 skipped.
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`: clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/tradingx`: clean.
- `UV_CACHE_DIR=/tmp/uv-cache uv run black --check <touched files>`: clean.
- `python3 scripts/check_index.py`: passed.

## Reviews

Two adversarial review loops completed. Critical/high findings fixed
or deferred with documented rationale. Runtime-execution red tests
explicitly out of scope (residual risk #1).

## Accepted residual risks

See `wave8_live_probe_operational_safety_implementation_report.md`.
Key items: runtime-execution path tests deferred; recertification
freshness window absent; CLI subcommands not wired; disable-verb list
duplicated; `run_refs` cross-linkage not validated; `./scripts/validate`
unrelated Black drift.
