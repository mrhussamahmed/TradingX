# TradingX End-to-End Review and Fix Report

Review date: 2026-05-02

Scope: full repo map, local run checks, backend and frontend validation, API/UI smoke testing, safety boundary review, prioritized fix plan, and highest-impact safe fixes.

## Project Map

- Stack: Python 3.11/3.12, FastAPI/Uvicorn, Alpaca paper broker integration, SQLAlchemy/Postgres optional control plane, filesystem artifacts by default, React 19 + TypeScript + Vite + Vitest.
- Python entrypoint: `src/tradingx/__main__.py`.
- Local web/API entrypoint: `src/tradingx/web/app.py`; runtime action adapter: `src/tradingx/web/runtime.py`; read models: `src/tradingx/web/readmodels.py`; write authorization: `src/tradingx/web/security.py`.
- Trading/runtime core: `src/tradingx/controller.py`, `src/tradingx/service.py`, `src/tradingx/runtime_host.py`, `src/tradingx/scheduler.py`, `src/tradingx/automation.py`.
- Validation and promotion: `src/tradingx/validation.py`, `src/tradingx/evaluation.py`, `src/tradingx/promotion.py`, `src/tradingx/promotion_bundle_builder.py`.
- Strategy registry: `src/tradingx/strategy.py`.
- Persistence: default local artifacts under `artifacts/` and `data/`; optional Postgres paths under `src/tradingx/persistence`.
- Auth model: no normal login. The web app is intended as local-only. GET endpoints are unauthenticated. Write endpoints require `TRADINGX_WEB_WRITE_MODE_ENABLED=true`, `TRADINGX_WEB_WRITE_SIGNING_SECRET`, timestamp, idempotency key, and HMAC signature.
- Deployment assumption: local operator appliance on `127.0.0.1`; no cloud hosting assumptions found.

## Confirmed Findings

### Critical

1. Duplicate signed web writes could race and execute twice. Fixed.

- Files: `src/tradingx/web/security.py:176`, `src/tradingx/web/security.py:296`, `src/tradingx/web/security.py:312`; regression test at `tests/unit/test_web_security.py:182`.
- What was wrong: the previous idempotency flow checked for an existing file, executed the action, then wrote the response file. Two concurrent requests with the same idempotency key could both pass the empty check before either wrote the record.
- Why it matters: this is directly in the "no duplicate paper submissions" safety boundary. A double click or retry storm could start duplicate service actions or submit duplicate paper cycles.
- Reproduce or verify: the new test first authorizes a signed request and then re-authorizes the same request before storing a response. It now gets HTTP 409 instead of a second authorization.
- Fix: idempotency keys are now atomically reserved with `O_EXCL`; in-progress duplicates return 409; completed duplicates replay the stored response.
- Residual risk: if an action crashes after reservation, the idempotency key remains in progress. This is safer than double execution, but the operator may need a cleanup/recovery command for stale pending records.

### High

2. Web action inputs accepted impossible or dangerous runtime values. Fixed.

- Files: `src/tradingx/web/app.py:59`, `src/tradingx/web/app.py:307`, `src/tradingx/web/app.py:372`, `src/tradingx/web/app.py:458`, `src/tradingx/web/app.py:475`; regression test at `tests/unit/test_web_app.py:1096`.
- What was wrong: write models accepted empty symbols, zero or negative intervals, zero quantities, and invalid sizing values. The service loop sleeps on `interval_seconds` at `src/tradingx/service.py:162`, so bad intervals could create tight loops or broken automation.
- Why it matters: the Runtime Host, recurring service, scheduler, paper-loop, and market-day endpoints are operator controls. They must reject impossible values before starting background work.
- Reproduce or verify: signed POST `/api/actions/service/start` with `interval_seconds=0` now returns 422. A fresh local server on port 8876 returned 422 for this exact check.
- Fix: added symbol normalization, positive decimal validation, positive interval/cadence constraints, and non-empty symbol lists to web write request models.

3. Gate 1 validation could crash instead of producing fail-closed evidence when more than two sleeves exist. Fixed.

- Files: `src/tradingx/validation.py:882`, `src/tradingx/validation.py:1174`, `src/tradingx/validation.py:1189`.
- What was wrong: Gate 1 marginal contribution was hard-coded to raise `NotImplementedError` unless exactly two sleeve-backed candidates were present. The current registry returns four sleeve-backed candidates at `src/tradingx/strategy.py:39`, so several Gate 1 flows crashed.
- Why it matters: operators need validation artifacts even when validation is incomplete. A crash hides the blocker; a pending criterion makes the blocker reviewable.
- Reproduce or verify: full validation originally had 21 failures, many from this crash. After the fix, Gate 1 produces pending marginal contribution results for unsupported sleeve counts.
- Fix: unsupported marginal contribution now becomes a pending criterion, so the report remains fail-closed instead of throwing.
- Follow-up: marginal contribution remains intentionally scoped to the evaluated trend/vol pair; incomplete or unsupported pairs produce pending fail-closed evidence instead of a crash.

4. Backtest reference generation failed for plain OHLCV data when a sleeve had no allowed instruments. Fixed.

- File: `src/tradingx/automation.py:728`.
- What was wrong: a candidate with an empty allowed-instrument set could lead to an empty `bars_by_symbol` input and `ValueError("bars_by_symbol must not be empty.")`.
- Why it matters: benchmark/reference artifact generation is one of the required validation artifact workflows.
- Reproduce or verify: `uv run pytest tests/unit/test_automation.py::test_backtest_reference_generation_accepts_plain_ohlcv_bars -q` passes.
- Fix: skip sleeve candidates with no allowed instruments when building reference returns.

5. Promotion posture is inconsistent with tests and documented gate progress. Fixed.

- Files: `tests/unit/test_main.py:130`, `docs/validation/acceptance_gates.md`.
- What changed: `promotion-check --strategy-id trend-following-v1` is now treated as the source of truth for the default artifact root. It returns `requested_state: "paper_trading"`, `max_state: "paper_trading"`, and empty blocker lists.
- Why it matters: the project now explicitly allows local paper-only trials without implying live trading approval.
- Verify: `uv run tradingx promotion-check --strategy-id trend-following-v1` and the updated CLI tests pass. `live-disable-status` still proves paper promotion does not enable live trading.

6. Mandatory candidate registry contract is inconsistent across validation tests. Fixed.

- Files: `src/tradingx/strategy.py`, `src/tradingx/validation.py`, `src/tradingx/controller.py`, runtime/readmodel callers, and registry-related tests.
- What changed: mandatory evaluation candidates now exclude `baseline-long-only-v1`; runtime/reference registries include it with `status: "reference"`.
- Why it matters: validation evidence counts, CPCV/PBO, and runtime strategy resolution now use explicit registries instead of conflicting positional assumptions.
- Verify: full validation passes, and a targeted `rg` scan found no accidental positional `build_mandatory_candidate_registry(...)[0]` or `[1]` test usage.

### Medium

7. Mobile/narrow UI layout is effectively unusable. Fixed.

- Files: `webapp/src/control-center/ControlCenterApp.tsx`, `webapp/src/control-center/shell/Shell.module.css`, `webapp/src/control-center/canvas/Canvas.module.css`.
- What changed: narrow screens now use explicit navigation and operator-rail drawer controls, a scrim, responsive shell columns, and safe canvas/header wrapping.
- Why it matters: the operator canvas owns the viewport at 390px wide, while stop/recovery controls remain reachable through the rail drawer.
- Verify: Browser Use interactions passed; exact viewport screenshots are recorded at `/Users/ahmedabd/Desktop/AI Projects/TradingX/artifacts/verification/2026-05-02-responsive-shell/tradingx-desktop-1440x900.png` and `/Users/ahmedabd/Desktop/AI Projects/TradingX/artifacts/verification/2026-05-02-responsive-shell/tradingx-mobile-390x844.png`.

8. Desktop top-right status action can clip at viewport edge.

- File: `webapp/src/control-center/shell/Shell.module.css:387`.
- What is wrong: the status actions sit at the far right of a dense top strip; desktop screenshot shows the alert button partly clipped.
- Why it matters: alert/recovery controls must be visually reliable.
- Reproduce or verify: screenshot captured at `tradingx-desktop-home.png`.
- Suggested fix: constrain the top strip with safe padding and wrap/collapse low-priority status cards before action controls clip.

9. Runtime heartbeat mixes active runtime symbols with activation/config symbols. Suspected UX risk.

- File: `src/tradingx/web/readmodels.py:3241`.
- What is wrong: runtime state reported active symbols `SPY,QQQ,IWM`, while heartbeat rows also included `XLE,XLF,XLK,EEM,TLT` from activation/config history.
- Why it matters: an operator could think the supervised runtime is watching/trading more symbols than it actually is.
- Reproduce or verify: `curl /api/runtime-host/state` and `curl /api/runtime-host/heartbeat` on the local server returned different symbol universes.
- Suggested fix: split heartbeat symbol rows into "active runtime universe" and "activation coverage" instead of merging them into one operational list.

10. Full API docs/OpenAPI are enabled by default. Suspected local-exposure risk.

- File: `src/tradingx/web/app.py:500`.
- What is wrong: `FastAPI(title=...)` uses default docs and OpenAPI routes. This is acceptable on loopback, but risky if the host is changed.
- Why it matters: the app has sensitive operational read endpoints and signed write endpoints. Accidental non-loopback exposure should not advertise the full control surface.
- Suggested fix: disable docs by default in production/local operator mode or require an explicit dev flag.

### Low

11. Config permits non-loopback web host even though product intent is local-only.

- Files: `src/tradingx/config.py:344`, `tests/unit/test_config.py:150`.
- What is wrong: `TRADINGX_WEB_HOST=0.0.0.0` is accepted and tested.
- Why it matters: write signing still protects POSTs, but GET endpoints expose operational state and evidence.
- Suggested fix: require an explicit unsafe/external bind flag for non-loopback hosts.

12. Vite production bundle is large.

- File: `webapp/dist/assets/index-*.js` from build output.
- What is wrong: build warns the JS chunk is about 731 kB, gzip about 212 kB.
- Why it matters: local-only mitigates network latency, but first-load performance and browser memory can degrade.
- Suggested fix: split large chart/report views with dynamic imports.

## Suspected Risks Requiring More Evidence

- Real Alpaca paper smoke tests were not run through order submission because they can place paper orders and market-hours availability is variable.
- Postgres integration paths were not verified because `TRADINGX_TEST_POSTGRES_DSN` was not provided.
- Recovery/drill flows were reviewed at code/test level, but not all were executed manually because they can mutate operator artifacts and runtime state.
- CLI write/action validation may still accept bad intervals or quantities outside the web API path.
- Stale in-progress web idempotency records need an operator-safe cleanup policy.

## Fixes Implemented

- Atomic web write idempotency reservation and in-progress replay rejection.
- Web action validation for symbols, quantities, intervals, cadences, max-cycle fields, and sizing decimals.
- Frontend lint fix for the holdings donut render path in `webapp/src/control-center/flavors/MarketChartFlavor.tsx:436`.
- Backtest reference generation now skips sleeves with no allowed instruments.
- Gate 1 unsupported marginal contribution now records a pending criterion instead of crashing.
- Paper-only promotion semantics now match the CLI: paper trials are allowed while live remains fail-closed.
- Baseline reference construction is split from evaluated candidate construction.
- Runtime/readmodel paths use the runtime registry so the baseline remains selectable and labeled as a reference.
- Gate 1 marginal/CPCV evidence is scoped to the evaluated trend/vol pair; mean reversion receives pass-through criteria where appropriate.
- The Control Center shell now has responsive drawers for narrow screens.
- Static validation blockers fixed in JSON typing, protocol stubs, runtime readmodel casts, and formatting-only files.

## Prioritized Fix Plan

P0:

- Add stale in-progress idempotency cleanup with audit trail.

P1:

- Make CLI service/scheduler inputs enforce the same positive interval and quantity rules as web writes.
- Split runtime heartbeat symbol lists into active runtime universe and activation/config coverage.
- Disable docs/OpenAPI unless a development flag is explicitly enabled.

P2:

- Add Postgres CI job with `TRADINGX_TEST_POSTGRES_DSN`.
- Add API-level tests for non-loopback host guardrails.
- Code split large frontend chunks.
- Add browser screenshot regression checks for desktop and mobile operator pages.

## Commands Run and Results

- `uv --version`: `uv 0.10.12`.
- `node --version`: `v25.9.0`.
- `npm --version`: `11.12.1`.
- `uv run tradingx config-summary --env-file .env`: passed; live disabled, paper credentials present, write signing configured.
- `uv run tradingx live-disable-status --env-file .env`: passed; live disabled by broker/config/env/credential blockers.
- `./scripts/validate-fast` baseline: failed Black, then failed promotion posture test.
- `./scripts/validate-fast` current: passed. Index validation, Ruff, Black, and mypy passed; focused backend tests reported 164 passed and 12 warnings.
- `./scripts/validate` current: passed. Unit/contract/integration coverage gate reported 1459 passed, 98 skipped, 18 warnings in 430.63s, with coverage 84.66% against the 80% threshold. Smoke gate reported 1 skipped because regular US market hours were closed.
- `npm --prefix webapp run lint`: passed with no diagnostics.
- `npm --prefix webapp test`: 10 test files passed; 108 tests passed.
- `npm --prefix webapp run build`: passed with the existing large chunk warning; JS chunk is 732.57 kB, gzip 212.39 kB.
- `uv build`: passed.
- Fresh local web smoke on `127.0.0.1:8876`: `/api/config/summary` returned 200; signed invalid service start returned 422.
- Browser Use in-app verification passed for mobile nav drawer, operator rail drawer, scrim close, and reachable kill/flatten/resume controls. Exact viewport screenshots were captured with Chrome/CDP fallback because Browser Use exposed no viewport resizing API in this session.

## Adversarial Reviewer Committee Packet

Questions reviewers should press:

- Can any operator action still execute twice with the same command intent? Focus on idempotency stale-pending behavior, action exceptions, and write endpoints that may bypass web authorization.
- Does the project have one source of truth for promotion state, or are tests/docs/artifacts disagreeing? Current answer: `promotion-check` paper state is accepted for paper-only trials, and docs/tests now agree.
- Should `baseline-long-only-v1` be part of mandatory Gate 1/2 validation, or is it a runtime control/baseline that should be excluded from CPCV/PBO counts? Current answer: it is a runtime/reference baseline and is excluded from mandatory validation counts.
- Is "pending marginal contribution" an acceptable fail-closed state, or must Gate 1 hard-fail until a 4-sleeve marginal model exists?
- Can a non-loopback bind expose operational data to the network?
- Does the operator UI show exactly what the runtime supervises, or does it blend historical activation coverage into active runtime state?

Evidence to review:

- Atomic idempotency implementation: `src/tradingx/web/security.py:176`.
- Web validation models: `src/tradingx/web/app.py:307`.
- Gate 1 pending marginal behavior: `src/tradingx/validation.py:882`.
- Split registry contract: `src/tradingx/strategy.py`.
- Current passing validation output from `./scripts/validate`.
- Screenshots: `/Users/ahmedabd/Desktop/AI Projects/TradingX/artifacts/verification/2026-05-02-responsive-shell/tradingx-desktop-1440x900.png`, `/Users/ahmedabd/Desktop/AI Projects/TradingX/artifacts/verification/2026-05-02-responsive-shell/tradingx-mobile-390x844.png`.

## Nontechnical Summary

The live-trading wall still appears closed: the app reports paper mode, no live credentials, and live enablement disabled. I fixed the most dangerous local-control issue: the same signed command can no longer slip through twice while the first one is still running. I also made the web controls reject bad values like zero-second loops and zero-share orders before they can start anything.

The project now has a clean paper-only promotion story for local trials, a split registry contract for baseline reference versus evaluated candidates, and a responsive Control Center shell for narrow screens. Full validation passes. Remaining product hardening work is mainly around stale idempotency cleanup, heartbeat symbol clarity, external-bind guardrails, and optional bundle/code-splitting work.
