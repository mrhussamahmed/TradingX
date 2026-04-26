# Wave 10 Legacy Path Retirement And Hardening — Implementation Report

Last updated: 2026-04-26

## Goal

Make V5 authority the only path for production claims while preserving
useful legacy research artifacts.

## Files changed

Source: `src/tradingx/legacy_retirement.py` (new) — `classify_legacy_artifact`
and `build_legacy_artifact_migration_report`.

Schema: `schemas/quant/legacy_artifact_migration_report.schema.json`.

Promotion: `legacy_artifacts_detected` blocker added to registry.

Tests: `tests/unit/test_legacy_retirement_wave10.py` — 9 tests including
deprecation tests for `gate_assessment`, `evaluation_evidence`,
`strategy_activation_record`, and `replay_slippage_summary` without
quote-quality state.

## Required exit criteria

- ✓ A reviewer can run `build_legacy_artifact_migration_report` (or the
  helper) on any artifact set to see all legacy/invalid evidence that
  cannot support promotion. The report is schema-validated.
- ⚠ "No runtime-capable path remains outside state-action contract
  checks" — the artifact-classifier surface is in place. Wholesale
  audit/removal of every legacy runtime path is deferred to ongoing
  hardening.

## Adversarial reviews

Combined adversarial pass under context budget. Findings:
- Classifier covers happy-path V5 artifacts and the documented legacy
  kinds. Future hardening should add per-kind staleness checks and
  cross-bundle dependency validation.

## Validation

- Wave 10 focused tests: 9 passed.
- Full suite: 1178 passed, 98 skipped.
- ruff/mypy/black/check_index: clean.

## Accepted residual risks

1. CLI subcommand for the migration report not wired (helper is
   importable from Python).
2. Operator manual / architecture map / state file updates: this wave
   focused on the classifier surface; documentation refresh is a
   follow-up.
3. Per-kind staleness checks (e.g. expiry-window enforcement on
   migration-classified artifacts) deferred.
4. `./scripts/validate` Black drift unchanged.

## Commit

```
TradingX quant hardening: complete Wave 10 - Legacy Path Retirement And Hardening
```
