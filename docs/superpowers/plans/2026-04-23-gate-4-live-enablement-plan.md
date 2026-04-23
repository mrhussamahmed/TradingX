# Gate 4 Live Enablement Implementation Plan

> **For agentic workers:** keep this branch narrow and fail-closed.
> This plan lands the missing Gate 4 live-enablement code, but it does
> **not** complete Gate 4 operational sign-off and it does **not** turn
> live trading on by default.

**Goal:** land the one remaining required engineering tranche for v1:
the live-enablement control plane. When this branch is done, TradingX
should be **live-capable in code** while still defaulting to paper mode
until the later Gate 4 evidence/sign-off lane is complete.

This implementation plan covers four tightly scoped outcomes:

1. preserve file-vs-env provenance for the live-control layers;
2. centralize broker-mode selection so production entrypoints stop
   hardcoding `paper=True`;
3. require request signing plus idempotency across the **entire** web
   write surface; and
4. expose explicit machine-readable “why live is still blocked” status
   without pretending that Gate 4 sign-off is already complete.

## Authority

1. [.specify/memory/constitution.md](/.specify/memory/constitution.md)
2. [docs/validation/acceptance_gates.md](/docs/validation/acceptance_gates.md)
3. [docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md](/docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md)
4. [docs/superpowers/plans/2026-04-23-gate-2-gate-3-gate-4-readiness-plan.md](/docs/superpowers/plans/2026-04-23-gate-2-gate-3-gate-4-readiness-plan.md)
5. [docs/operations/operator_manual.md](/docs/operations/operator_manual.md)
6. [docs/archive/implementation_constraints.md](/docs/archive/implementation_constraints.md)

## Activation contract

This branch is **not** “flip live trading on.” It is “make live trading
possible to enable later, while keeping the shipped defaults fail-closed
today.”

After this branch lands:

- explicitly paper-named command paths remain paper-only wrappers;
- generic runtime/operator entrypoints become broker-mode aware through
  one shared policy/helper instead of scattering `paper=True` or
  `paper=False` throughout constructors;
- requesting live mode never silently falls back to paper mode;
- web POST routes require:
  - `write_mode_enabled`,
  - a valid request signature,
  - a fresh request timestamp, and
  - a valid idempotency key;
- duplicate signed POSTs with the same request fingerprint return the
  stored first response instead of replaying the action;
- reused idempotency keys with a different request fingerprint are
  rejected; and
- `live-disable-status` plus `/api/config/summary` expose explicit
  machine-readable disable reasons.

This branch still does **not** do the later Gate 4 evidence/sign-off
work:

- it does not certify the 7-day monitoring window;
- it does not certify fresh SMTP or kill-switch drill evidence;
- it does not approve live capital;
- it does not change Gate 2 / Gate 3 evidence requirements; and
- it does not auto-enable live orders on merge.

## Review-sensitive locks

These are the likely adversarial-review churn points. Treat them as
non-negotiable:

1. **Preserve provenance for the control layers.**
   `TradingConfig.from_env_file(...)` currently collapses dotenv and
   process env into one mapping. That is not sufficient for Gate 4,
   because `config_enabled` and `env_enabled` need different sources.
   The implementation must preserve source provenance explicitly.
2. **Keep explicitly paper-named paths paper-only.**
   `paper-loop`, `paper-recover`, `run-paper-service`,
   `build_default_paper_service(...)`, and
   `build_runtime_host_paper_service(...)` should remain explicit paper
   wrappers. Live capability should land through generic mode-aware
   helpers, not by silently mutating every “paper” path.
3. **No direct `TradingClient(..., paper=False)` scatter.**
   Live/paper client selection must be centralized in one shared helper
   or factory. Every production entrypoint should consume that seam.
4. **The web-auth boundary is the full POST surface.**
   This branch may not secure only one “future live toggle” route.
   Every shipped write endpoint in `src/tradingx/web/app.py` must pass
   through the same signature + idempotency guard.
5. **The shipped browser client needs a real signing path.**
   The current SPA in `webapp/src/api.ts` sends bare JSON POSTs. The
   implementation must therefore add an explicit browser-side signing
   flow; it may not “solve” this by bundling the signing secret into the
   frontend build.
6. **Idempotency is request-fingerprint aware.**
   Exact duplicate signed POSTs should replay the stored first result.
   Same key + different request fingerprint must reject with conflict.
   This matters because `/api/config/proposals` returns
   `ConfigProposal`, not `WebActionResult`, so the idempotency store
   must preserve generic serialized JSON responses.
7. **`live_disable_report()` keeps legacy keys stable.**
   Existing readmodels/alerts depend on `paper_only_mode`,
   `live_trading_enabled`, and `manual_kill_switch_active`.
   The report may grow richer, but those keys must stay valid.
8. **Risk remains fail-closed.**
   Requesting live mode without complete readiness must block with an
   explicit reason. It must not degrade to paper execution.
9. **Do not overclaim Gate 4 sign-off in this branch.**
   Fresh drill windows, monitoring observation, and operator approval
   stay in the later evidence lane.
10. **Do not spend this branch on naming cleanup.**
   Repo-wide renames of `PaperOnlyRiskEngine`,
   `AlpacaPaperExecutionGateway`, and similar compatibility names are
   out of scope unless a thin alias is required for clarity. The target
   is correct control behavior, not global rename churn.

## Scope

### In scope

- preserve separate dotenv-file and process-env inputs inside config
  loading;
- parse live credentials and explicit broker-mode intent;
- centralize live/paper trading-client selection;
- wire all generic runtime/operator entrypoints through that shared
  broker-mode policy;
- enforce request signing + idempotency across the web POST surface;
- expose explicit live-disable / live-block reasons in config summary
  and CLI status;
- keep paper-only wrappers stable;
- add operator/docs/env examples for the new control surface; and
- add a dedicated Gate 4 live-enablement ADR in the same branch.

### Out of scope

- Gate 2 robustness evidence;
- Gate 3 paper-evidence generation;
- Gate 3 two-sleeve report fixes;
- actual Gate 4 operator sign-off;
- live capital sizing or rollout percentage enforcement;
- Kelly sizing, new sleeves, new strategies, or universe expansion;
- auto-enabling live orders after merge; and
- repo-wide class/module renames for “paper” terminology.

## Modified files

- `.env.example`
- `src/tradingx/config.py`
- `src/tradingx/live_enablement.py` (new)
- `src/tradingx/risk.py`
- `src/tradingx/controller.py`
- `src/tradingx/service.py`
- `src/tradingx/automation.py`
- `src/tradingx/supervisor.py`
- `src/tradingx/__main__.py`
- `src/tradingx/web/app.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/web/security.py` (new)
- `webapp/src/api.ts`
- `webapp/src/App.tsx`
- `webapp/src/types.ts`
- `docs/adrs/ADR-NNNN-gate4-live-enablement-control-plane.md`
- `docs/INDEX.md`
- `docs/operations/operator_manual.md`
- `tests/unit/test_config.py`
- `tests/unit/test_live_enablement.py` (new)
- `tests/unit/test_web_security.py` (new)
- `tests/unit/test_risk.py`
- `tests/unit/test_service.py`
- `tests/unit/test_automation.py`
- `tests/unit/test_supervisor.py`
- `tests/unit/test_main.py`
- `tests/unit/test_web_app.py`
- `tests/unit/test_web_runtime.py`
- `tests/contract/test_local_web_app_api_contract.py`
- `tests/contract/test_day0_web_surface.py`
- `webapp/src/App.test.tsx`

Only plan files under `docs/superpowers/plans/` are exempt from
frontmatter indexing. The implementation branch must allocate the next
free ADR number at execution time and add the corresponding row to
`docs/INDEX.md`.

## Implementation shape

The branch should land as one coherent control-plane hardening change
with four moving parts:

1. **Mode-aware config + client factory**
   Add a single broker-mode policy helper that knows:
   - the requested broker mode,
   - whether live credentials are real,
   - whether the file/env control layers are enabled, and
   - whether live should be blocked with explicit reasons.
   Every generic production entrypoint should use that helper instead of
   constructing `TradingClient(..., paper=True)` inline.
   This also requires a new **generic mode-aware service-builder seam**
   so generic entrypoints stop hardwiring
   `build_default_paper_service(...)` /
   `build_runtime_host_paper_service(...)` one layer up.
2. **Signed/idempotent web write guard**
   Add one shared FastAPI-side write authorizer that sits in front of
   every POST route and enforces:
   - write mode enabled,
   - HMAC signature present and valid,
   - request timestamp within the allowed skew window,
   - idempotency key present, and
   - duplicate semantics based on request fingerprint.
   Pair that with an explicit SPA signing flow so the shipped browser
   client can continue to use write actions without exposing the signing
   secret in the build output.
3. **Fail-closed live readiness reporting**
   Extend `live-disable-status` and the web config summary so the
   operator can see exactly which layer is still preventing live mode.
   This is still config/control readiness, not final Gate 4 approval.
4. **Docs + ADR + env/operator guidance**
   Update `.env.example`, operator manual instructions, and a dedicated
   ADR so the control-plane behavior is documented at merge time.

The branch should not try to solve the later evidence/sign-off lane.

---

## Task 1 — Preserve control-layer provenance and centralize broker-mode selection

**Goal:** replace ad-hoc `paper=True` construction with one shared
mode-selection seam while preserving the difference between config-file
opt-in and real environment opt-in.

### Files

- `src/tradingx/config.py`
- `src/tradingx/live_enablement.py`
- `src/tradingx/service.py`
- `src/tradingx/automation.py`
- `src/tradingx/supervisor.py`
- `src/tradingx/controller.py`
- `src/tradingx/__main__.py`
- `src/tradingx/web/runtime.py`
- `tests/unit/test_config.py`
- `tests/unit/test_live_enablement.py`
- `tests/unit/test_service.py`
- `tests/unit/test_automation.py`
- `tests/unit/test_supervisor.py`
- `tests/unit/test_main.py`
- `tests/unit/test_web_runtime.py`

### Required behavior

- `TradingConfig` must parse:
  - `ALPACA_LIVE_API_KEY`
  - `ALPACA_LIVE_API_SECRET`
  - `TRADINGX_BROKER_MODE` (`paper` by default, `live` only when
    explicit)
  - `TRADINGX_LIVE_CONFIG_ENABLED` from the dotenv/config-file side
  - `TRADINGX_ENABLE_LIVE_TRADING` from real process env only
- `LiveTradingControls.code_enabled` becomes a real Gate 4 code-layer
  flag rather than a permanently-false placeholder. In this tranche it
  should evaluate to `True` because the branch itself is the code-layer
  enablement.
- `LiveTradingControls.broker_enabled` derives from requested broker
  mode (`live` vs `paper`), not from an unrelated boolean.
- generic production entrypoints must route through a single helper in
  `src/tradingx/live_enablement.py`, not inline `TradingClient(...)`
  constructors.
- generic production entrypoints that are currently paper-bound through
  `build_default_paper_service(...)` or
  `build_runtime_host_paper_service(...)` must gain a new mode-aware
  service-builder seam instead of silently changing those explicit paper
  wrappers.
- explicitly paper-named paths remain paper-only wrappers.

### TDD steps

- [ ] Add failing tests in `tests/unit/test_config.py` for:
  - file-vs-env provenance:
    `TRADINGX_LIVE_CONFIG_ENABLED` in `.env` does **not** satisfy the
    process-env layer;
  - live credentials parse separately from paper credentials;
  - `TRADINGX_BROKER_MODE=paper` keeps `broker_enabled=False`;
  - `TRADINGX_BROKER_MODE=live` sets `broker_enabled=True`;
  - `live_disable_report()` keeps legacy keys and adds explicit reasons.
- [ ] Add failing tests in `tests/unit/test_live_enablement.py` for:
  - requested paper mode returns a paper client decision;
  - requested live mode with missing live credentials blocks with
    explicit reasons;
  - requested live mode with controls incomplete blocks without silently
    downgrading to paper;
  - requested live mode with all control layers complete returns a live
    decision.
- [ ] Add failing integration-style constructor tests in:
  - `tests/unit/test_service.py`
  - `tests/unit/test_automation.py`
  - `tests/unit/test_supervisor.py`
  - `tests/unit/test_web_runtime.py`
  - `tests/unit/test_main.py`
  proving that generic entrypoints stop hardcoding `paper=True`.
- [ ] In `src/tradingx/config.py`, split config loading into a
  source-aware helper such as `from_sources(file_values, env_values)` so
  provenance is not lost.
- [ ] Add `LiveCredentials` and broker-mode parsing.
- [ ] Add `has_real_live_credentials()` alongside the existing paper
  helper.
- [ ] Expand `live_disable_report()` so it preserves the old keys while
  also reporting the specific disabled layers / missing prerequisites.
- [ ] Create `src/tradingx/live_enablement.py` with a narrow shared
  helper such as:
  - `BrokerModeDecision`
  - `resolve_broker_mode(config, *, explicit_mode: str | None = None)`
  - `build_trading_client_for_mode(config, decision)`
- [ ] In `src/tradingx/service.py`, add a new generic, mode-aware
  service-builder seam such as:
  - `build_default_trading_service(config, *, broker_mode: str | None = None, opportunity_selector: ... = None)`
  - `build_runtime_host_trading_service(config, *, broker_mode: str | None = None)`
  while keeping `build_default_paper_service(...)` and
  `build_runtime_host_paper_service(...)` as explicit paper wrappers
  that delegate to the new generic builders with `broker_mode="paper"`.
- [ ] Replace generic production `TradingClient(..., paper=True)` call
  sites **and generic paper-service-builder callsites** with the shared
  helper / new service-builder seam in:
  - `src/tradingx/service.py`
  - `src/tradingx/automation.py`
  - `src/tradingx/supervisor.py`
  - `src/tradingx/controller.py`
  - `src/tradingx/__main__.py`
  - `src/tradingx/web/runtime.py`
- [ ] Add tests proving the generic entrypoints no longer remain
  paper-bound through `build_default_paper_service(...)` /
  `build_runtime_host_paper_service(...)` one layer above client
  construction.
- [ ] Keep explicit paper wrappers stable:
  - `paper-loop`
  - `paper-recover`
  - `run-paper-service`
  - `build_default_paper_service(...)`
  - `build_runtime_host_paper_service(...)`
- [ ] Re-run the Task 1 slice until green.

### Lock

This task must not silently reinterpret every paper-named path as
potentially live. Generic mode-aware helpers are in scope; mutating the
semantics of explicit paper wrappers is not.

---

## Task 2 — Enforce signed and idempotent writes across the full web POST surface

**Goal:** replace the current `write_mode_enabled`-only guard with one
shared signed/idempotent authorizer for all FastAPI write endpoints.

### Files

- `src/tradingx/config.py`
- `src/tradingx/web/security.py`
- `src/tradingx/web/app.py`
- `webapp/src/api.ts`
- `webapp/src/App.tsx`
- `webapp/src/types.ts`
- `tests/unit/test_config.py`
- `tests/unit/test_web_security.py`
- `tests/unit/test_web_app.py`
- `tests/contract/test_local_web_app_api_contract.py`
- `tests/contract/test_day0_web_surface.py`
- `webapp/src/App.test.tsx`

### Required behavior

- every POST route in `src/tradingx/web/app.py` must require:
  - `TRADINGX_WEB_WRITE_MODE_ENABLED=true`
  - a shared-secret HMAC signature
  - a timestamp header
  - an idempotency-key header
- GET routes remain unaffected.
- exact duplicate signed POSTs return the first stored serialized
  response payload.
- same idempotency key + different request fingerprint returns conflict.
- missing/invalid signature, missing idempotency key, or stale
  timestamp returns reject/forbidden rather than falling through to the
  action runner.

### Browser client architecture

The shipped browser SPA must remain usable after this branch. To avoid
putting the signing secret in the bundle, the browser-side contract
should be:

- the operator manually unlocks web writes inside the local SPA by
  entering `TRADINGX_WEB_WRITE_SIGNING_SECRET` at runtime;
- the SPA keeps that secret only in in-memory state or
  `sessionStorage`, never in source, bundle output, or committed config;
- `webapp/src/api.ts` signs every POST request client-side with the same
  canonical string the server verifies;
- GET requests remain unsigned;
- when the SPA has no unlocked secret, write actions stay disabled in
  the UI with an explicit “writes locked” state rather than emitting
  broken unsigned POSTs.

This preserves the acceptance-gate requirement for signed web writes
without bundling the secret or weakening the server-side verifier.

### Concrete protocol

Use one explicit header contract across the write surface:

- `X-TradingX-Timestamp`
- `X-TradingX-Idempotency-Key`
- `X-TradingX-Signature`

Recommended signature payload:

```text
{METHOD}\n{PATH}\n{TIMESTAMP}\n{IDEMPOTENCY_KEY}\n{BODY_SHA256}
```

with HMAC-SHA256 over that canonical string.

The idempotency store should live under:

- `data/control/web_write_idempotency/`

and should store:

- route/path
- idempotency key
- request fingerprint
- serialized response payload
- status code
- first-seen timestamp

Use durable JSON records in the dedicated web-security module rather
than widening `OperatorControlStore` for unrelated write-auth state.

### TDD steps

- [ ] Add failing tests in `tests/unit/test_web_security.py` for:
  - valid signature verification;
  - invalid signature rejection;
  - stale timestamp rejection;
  - exact duplicate replay returning the stored first result;
  - same key + different fingerprint rejecting with conflict.
- [ ] Add failing tests in `tests/unit/test_web_app.py` for:
  - unsigned POST rejection;
  - missing idempotency-key rejection;
  - signed POST success on an existing route;
  - duplicate signed POST short-circuiting to the stored response.
- [ ] Add failing frontend tests in `webapp/src/App.test.tsx` for:
  - write actions stay disabled until the operator unlocks the write
    secret locally;
  - unlocked write actions attach timestamp, idempotency key, and
    signature headers via `webapp/src/api.ts`;
  - the secret is never read from build-time config or rendered into the
    DOM.
- [ ] Add failing contract tests in:
  - `tests/contract/test_local_web_app_api_contract.py`
  - `tests/contract/test_day0_web_surface.py`
  proving that the shipped POST surface is covered broadly rather than
  one endpoint at a time.
- [ ] In `src/tradingx/config.py`, add web-write security settings:
  - `TRADINGX_WEB_WRITE_SIGNING_SECRET`
  - `TRADINGX_WEB_WRITE_MAX_AGE_SECONDS`
- [ ] Create `src/tradingx/web/security.py` with:
  - canonical request hashing
  - HMAC verification
  - durable idempotency record storage
  - duplicate / conflict decision helpers
- [ ] Update `create_app(...)` in `src/tradingx/web/app.py` to route
  every POST through one shared authorization helper.
- [ ] Update the shipped SPA in:
  - `webapp/src/api.ts`
  - `webapp/src/App.tsx`
  - `webapp/src/types.ts`
  so browser writes follow the runtime-unlocked signing flow described
  above.
- [ ] Preserve existing `write_mode_enabled` semantics as the first gate;
  do not remove it.
- [ ] Re-run the Task 2 slice until green.

### Lock

This task must secure the current write surface broadly. The branch is
not allowed to claim Gate 4 security while leaving a second class of
POST routes on the old `write_mode_enabled`-only behavior.

---

## Task 3 — Fail-closed live readiness, risk gating, and status exposure

**Goal:** make live readiness explicit and fail-closed in runtime code
without pretending the later Gate 4 evidence lane is already complete.

### Files

- `src/tradingx/live_enablement.py`
- `src/tradingx/risk.py`
- `src/tradingx/controller.py`
- `src/tradingx/__main__.py`
- `src/tradingx/web/app.py`
- `tests/unit/test_live_enablement.py`
- `tests/unit/test_risk.py`
- `tests/unit/test_main.py`

### Required behavior

- live mode must still block when:
  - live credentials are placeholder/missing;
  - the config-file control layer is off;
  - the real-env control layer is off;
  - requested broker mode is still paper;
  - web signed-write controls are not configured;
  - manual kill switch is active; or
  - dry-run mode is active.
- `live-disable-status` must expose those reasons directly.
- `/api/config/summary` must expose the same disable report.
- risk evaluation must remain fail-closed for live orders; the branch is
  allowed to approve live only through the new shared broker-mode/live
  readiness decision.
- the live-disable metric must stop being hardcoded to “disabled” when
  the config/report says otherwise.

### TDD steps

- [ ] Add failing tests in `tests/unit/test_live_enablement.py` for:
  - web signed-write config missing => live blocked;
  - manual kill switch active => live blocked;
  - dry-run active => live blocked;
  - all local prerequisites satisfied => report marks live-capable.
- [ ] Add failing tests in `tests/unit/test_risk.py` for:
  - explicit live order with incomplete readiness remains blocked;
  - explicit live order with complete readiness can pass the live gate
    and continue through the normal risk checks;
  - requested live mode never downgrades to paper mode silently.
- [ ] Add failing tests in `tests/unit/test_main.py` for
  `live-disable-status` showing the richer machine-readable report.
- [ ] In `src/tradingx/risk.py`, replace the current
  unconditional-live-block branch with a call into the shared
  live-enable decision helper while keeping the overall default
  fail-closed.
- [ ] In `src/tradingx/controller.py`, stop hardcoding
  `record_live_disable_state(True)` and instead use the effective
  disable report from config/live readiness.
- [ ] Keep `live_disable_report()` backward compatible at the key level
  so existing readmodels and alerts continue to render.
- [ ] Re-run the Task 3 slice until green.

### Lock

This task is about **code-local** readiness and explicit blocked
reasons. It must not claim that the later 7-day monitoring / fresh
SMTP / fresh kill-switch evidence lane is already satisfied.

---

## Task 4 — Operator/docs/ADR update and full verification

**Goal:** land the operator-facing contract for the new live-enablement
control plane in the same branch as the code.

### Files

- `.env.example`
- `docs/operations/operator_manual.md`
- `docs/adrs/ADR-NNNN-gate4-live-enablement-control-plane.md`
- `docs/INDEX.md`

### Required behavior

- `.env.example` must document the new live-control and web-signing
  variables without implying that live is enabled by default.
- the operator manual must describe:
  - which paths remain paper-only,
  - which entrypoints become broker-mode aware,
  - how signed web writes are formed,
  - how to read `live-disable-status`, and
  - that Gate 4 sign-off is still a later lane.
- the ADR must lock:
  - provenance-preserving config load,
  - explicit paper-wrapper stability,
  - centralized broker-mode selection,
  - full write-surface signing/idempotency, and
  - fail-closed live readiness without silent downgrade.

### TDD / verification steps

- [ ] Add/adjust tests first where the docs/CLI examples introduce new
  visible contract strings.
- [ ] Allocate the next free ADR number at implementation time.
- [ ] Add the ADR row to `docs/INDEX.md`.
- [ ] Run `python3 scripts/check_index.py`.

### Lock

Do not split the docs/ADR update into a follow-up. This is a control
plane change; the operator contract must land with the code.

---

## Verification

### Narrow loop

Use this during TDD:

```bash
uv run pytest -q \
  tests/unit/test_config.py \
  tests/unit/test_live_enablement.py \
  tests/unit/test_web_security.py \
  tests/unit/test_risk.py \
  tests/unit/test_web_app.py \
  tests/unit/test_service.py \
  tests/unit/test_automation.py \
  tests/unit/test_supervisor.py \
  tests/unit/test_main.py \
  tests/unit/test_web_runtime.py \
  tests/contract/test_local_web_app_api_contract.py \
  tests/contract/test_day0_web_surface.py
(cd webapp && npm test -- src/App.test.tsx)
```

### Full branch verification

Before review, all of these must pass:

```bash
uv run ruff check src/tradingx tests
uv run mypy src/tradingx
uv run pytest -q --deselect tests/contract/test_weight_snapshot_origin.py
(cd webapp && npm test)
(cd webapp && npm run build)
python3 scripts/check_index.py
./scripts/validate
```

## Done condition

This branch is done when all of the following are true:

- generic production entrypoints are broker-mode aware through one
  shared helper;
- paper-named wrappers remain explicitly paper-only;
- every shipped web POST route enforces signed/idempotent writes;
- live-disable status exposes concrete blocked reasons;
- live mode is still disabled by default and still fail-closed without
  complete readiness; and
- the ADR/operator/env docs land in the same branch.
