---
id: REPORT-0004
title: Headless control plane Wave 2 foundation implementation adversarial review handoff
version: 1.0.0
status: draft
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# Headless Control Plane Wave 2 Foundation Implementation Adversarial Review Handoff

## Scope

This report prepares the first Wave 2 implementation slice for
adversarial review. It covers code changes only, not another planning
round.

This slice starts `PLAN-0014` by landing the low-risk prerequisites that
later Postgres storage work depends on:

1. the new control-plane config surface with legacy-safe defaults
2. redacted Postgres DSN handling for safe summaries and future logging
3. the `tradingx.persistence` module-to-package conversion required
   before adding `tradingx.persistence.*` submodules

It does not yet add live Postgres engines, migrations, repositories,
projectors, or route pivots.

## Files To Review

- `src/tradingx/config.py`
- `src/tradingx/persistence/__init__.py`
- `src/tradingx/persistence/postgres.py`
- `tests/unit/test_postgres_config.py`
- `tests/unit/test_persistence_namespace.py`
- `docs/superpowers/plans/2026-04-23-wave2-postgres-projections-foundation-review-handoff.md`
- `docs/INDEX.md`

## What Changed

### Control-plane config defaults are now explicit

`TradingConfig` now carries a frozen `ControlPlaneConfig` with the Wave 2
environment surface from `PLAN-0013`:

- `TRADINGX_POSTGRES_DSN`
- `TRADINGX_CONTROL_PLANE_STORE`
- `TRADINGX_CONTROL_PLANE_DOMAIN_STORES`
- `TRADINGX_POSTGRES_REQUIRED`
- `TRADINGX_PROJECTION_MODE`
- `TRADINGX_PROJECTION_BATCH_SIZE`
- `TRADINGX_LEGACY_BRIDGE_MODE`
- `TRADINGX_LEGACY_BACKFILL_ENABLED`
- `TRADINGX_LEGACY_BACKFILL_BATCH_SIZE`
- `TRADINGX_PROJECTION_MAX_LAG_SECONDS`

Defaults preserve existing local behavior: legacy mode remains the
default, projections stay disabled, and no database is required unless an
operator opts in.

### Safe summaries redact Postgres credentials

`TradingConfig.to_safe_summary()` now reports whether Postgres is
configured and includes only a redacted DSN string. Raw credentials do
not appear in the summary output.

### `tradingx.persistence` is now a package entry point

The old `src/tradingx/persistence.py` module was converted into
`src/tradingx/persistence/__init__.py` so the repo can safely add
`tradingx.persistence.postgres` and future submodules without Python
shadowing the legacy import surface.

The public `from tradingx.persistence import FilesystemArtifactStore`
contract remains intact.

### Postgres helper module started small on purpose

`src/tradingx/persistence/postgres.py` currently adds the DSN redaction
helper used by tests and config summaries. It is intentionally narrow:
engine/session helpers and migrations are deferred to the next slice.

## Review-Sensitive Locks

### Legacy mode must still boot without Postgres

The new config fields must not force a database in default local mode.
If an empty environment now changes startup expectations anywhere, that
is a bug.

### The namespace conversion must not break existing imports

Any import path that previously resolved `FilesystemArtifactStore` from
`tradingx.persistence` must keep working after the package conversion.
The move should be invisible to the rest of the codebase.

### Safe summaries must stay secret-safe

No raw Postgres password should appear in config summaries, exception
messages, or helper outputs introduced by this slice.

### This slice should be prerequisite-only

The implementation should not accidentally smuggle in behavior changes
to routing, storage selection, or runtime writes beyond the approved
foundation scope.

## Reviewer Focus Areas

Please challenge this slice on:

1. whether the `tradingx.persistence` package conversion misses any
   compatibility behavior the existing module shape provided
2. whether any current import or test harness can still break because
   Python now resolves a package instead of a module
3. whether `ControlPlaneConfig` parsing or defaults are inconsistent
   with `PLAN-0013` / `PLAN-0014`
4. whether `TRADINGX_CONTROL_PLANE_DOMAIN_STORES` parsing is too loose
   or too strict for the documented migration use cases
5. whether `to_safe_summary()` can still leak raw DSN credentials
6. whether the slice introduced hidden coupling that will complicate the
   upcoming SQLAlchemy/Alembic work

## Known Deferrals

Still pending after this slice:

- Postgres project dependencies in `pyproject.toml`
- engine/session helpers with timeout settings
- Alembic configuration and initial schema migration
- Postgres repository contracts
- outbox/checkpoint/source-readiness storage
- legacy bridge and projectors
- Postgres read model and domain router
- `/api/v1` route and SSE pivots

## Verification Run

This slice was verified with:

```bash
uv run pytest tests/unit/test_postgres_config.py -q
uv run pytest tests/unit/test_persistence_namespace.py -q
uv run pytest tests/unit/test_config.py -q
uv run pytest tests/unit/test_persistence.py -q
uv run pytest tests/contract/test_local_web_app_api_contract.py -q
uv run ruff check src/tradingx/config.py src/tradingx/persistence tests/unit/test_postgres_config.py tests/unit/test_persistence_namespace.py
git diff --check
```

## Review Outcome Requested

Please return:

1. P0/P1/P2 findings with exact file and line references.
2. Confirmation that the prerequisite slice preserves current import
   behavior and legacy local mode.
3. Confirmation that the branch is ready to continue into Postgres
   connection/migration work once findings are addressed.
