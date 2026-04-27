# Wave 10 Legacy Path Retirement And Hardening — Handoff

Wave completed: yes

Files: `src/tradingx/legacy_retirement.py` (new),
`schemas/quant/legacy_artifact_migration_report.schema.json` (new),
`tests/unit/test_legacy_retirement_wave10.py` (new), 1 new blocker
seed in `src/tradingx/promotion.py`, five report files.

Validation: 9 focused tests; 1178 total; ruff/mypy/black/check_index clean.

Reviews: combined adversarial pass.

Residual risks: CLI wiring, operator-manual updates, per-kind
staleness checks (see implementation report).
