# Headless Control Plane Implementation Plan

> **For agentic workers:** this plan is the execution bridge from
> `DESIGN-0022` into staged implementation. Keep the migration
> incremental, fail-closed, and compatible with the current local
> appliance until the new control plane is fully proven.

**Goal:** turn the approved headless-control-plane architecture into a
production-grade implementation path without a rewrite. When this plan
is complete, TradingX should have:

1. a canonical `/api/v1` control plane;
2. Postgres-backed command/session/audit state;
3. a worker split between API/control-plane and runtime/job execution;
4. a locally runnable multi-service stack that matches cloud contracts;
5. staging-ready deployment topology; and
6. a frontend that can begin migrating onto the new contracts without
   depending on legacy artifact parsing.

This plan is intentionally broad because the architecture change is
cross-cutting. It should still be executed in narrow, reviewable waves.

## Authority

1. [.specify/memory/constitution.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/.specify/memory/constitution.md)
2. [docs/architecture/TradingX_Headless_Control_Plane_Architecture.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/architecture/TradingX_Headless_Control_Plane_Architecture.md:1)
3. [docs/architecture/TradingX_Frontend_Design.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/architecture/TradingX_Frontend_Design.md:1)
4. [docs/architecture/TradingX_Dashboard_And_Design_System.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/architecture/TradingX_Dashboard_And_Design_System.md:1)
5. [docs/adrs/ADR-0016-local-trading-appliance-runtime-host.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/adrs/ADR-0016-local-trading-appliance-runtime-host.md:1)
6. [docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/adrs/ADR-0025-gate4-live-enablement-control-plane.md:1)
7. [docs/validation/acceptance_gates.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/validation/acceptance_gates.md:1)
8. [docs/architecture/CURRENT_ARCHITECTURE.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/architecture/CURRENT_ARCHITECTURE.md:1)

## Planning Contract

This plan must preserve the following invariants throughout the
migration:

1. **Fail-closed live posture remains mandatory.**
   No branch in this plan may introduce a bypass around signed writes,
   command sessions, kill switches, dry-run posture, or governance
   sign-off checks.
2. **The current local app must remain usable until cutover.**
   New `/api/v1` contracts may coexist with legacy routes, but the
   frontend should not be stranded between two incomplete worlds.
3. **Commands remain explicit governed transactions.**
   No resource-specific mutation helper is allowed to drift from the
   canonical command/session/idempotency/audit path.
4. **Postgres becomes the operational source of truth.**
   Redis, local files, and object storage may support the system, but
   they do not become the canonical command or operator-state store.
5. **One runtime worker per environment.**
   Lease fencing must exist before cloud runtime cutover.
6. **Frontend contracts come before frontend redesign.**
   The backend control plane must be authoritative before the frontend
   relies on it.

## Out of Scope

- Android implementation
- visual redesign implementation
- new strategy research or new sleeves
- discretionary trading UI
- full microservice breakup by every domain
- live-capital rollout and Gate 4 final operational sign-off

## Review-Sensitive Locks

These are the most likely adversarial-review churn points. Treat them as
non-negotiable:

1. **`/api/v1` lands before worker split.**
   Do not start by moving runtime execution into a separate worker while
   the canonical control-plane contract is still undefined.
2. **Commands are the only canonical governed mutation path.**
   Incident acknowledgement, replay creation, and similar writes may
   gain convenience wrappers later, but they must remain strict aliases
   over the command path and never drift into a second write model.
3. **Command concurrency is precondition-based, not last-writer-wins.**
   Safety-critical state transitions must name expected resource version
   and expected current state.
4. **Cloud command sessions must preserve Gate 4 write semantics.**
   The session model may change how signing material is sourced, but it
   may not weaken the signed-write, freshness, idempotency, or
   fail-closed guarantees from `ADR-0025`.
5. **Control posture must remain remediation-grade.**
   The backend must expose both aggregate posture and layer-by-layer
   blockers, including governance sign-off state.
6. **Portfolio, validation, replay, and incident views must gain real
   canonical APIs.**
   The frontend migration may not quietly fall back to artifact parsing
   once the new control plane exists.
7. **Lease fencing is required before cloud runtime cutover.**
   A separate worker without fencing is not an acceptable intermediate
   state.
8. **Migration must bridge old audit history into Postgres.**
   Command history, runtime audit, and operator events cannot become
   split-brain between old local stores and the new control plane.

## Technical Translation

The approved architecture should land in the codebase as:

- a new control-plane-oriented backend package surface
- a Postgres-backed persistence layer for commanding and projections
- one runtime worker process separated from the API process
- one job-worker process family for replay/validation/reporting
- a local compose stack that runs these services together

Suggested target source structure:

```text
src/tradingx/
├── controlplane/
│   ├── api_v1.py
│   ├── commands.py
│   ├── command_sessions.py
│   ├── posture.py
│   ├── incidents.py
│   ├── runtime_views.py
│   ├── portfolio_views.py
│   ├── validation_views.py
│   ├── replay_views.py
│   └── projections.py
├── persistence/
│   ├── postgres.py
│   ├── migrations/
│   ├── repositories/
│   └── outbox.py
├── workers/
│   ├── runtime_worker.py
│   ├── job_worker.py
│   ├── lease.py
│   └── dispatch.py
└── web/
    ├── app.py
    ├── runtime.py
    ├── readmodels.py
    └── security.py
```

The plan does **not** require moving every existing module immediately.
It does require creating clean seams that future work can target.

## Modified Files and Areas

Expected implementation touchpoints:

- `src/tradingx/web/app.py`
- `src/tradingx/web/runtime.py`
- `src/tradingx/web/readmodels.py`
- `src/tradingx/web/security.py`
- `src/tradingx/config.py`
- `src/tradingx/live_enablement.py`
- `src/tradingx/runtime_host.py`
- `src/tradingx/service.py`
- `src/tradingx/supervisor.py`
- `src/tradingx/automation.py`
- `src/tradingx/controller.py`
- `src/tradingx/journal.py`
- `src/tradingx/snapshots.py`
- `src/tradingx/reporting.py`
- new `src/tradingx/controlplane/` package
- new `src/tradingx/persistence/` package
- new `src/tradingx/workers/` package
- `webapp/src/api.ts`
- `webapp/src/types.ts`
- `webapp/src/platform/*.tsx`
- new local infra files:
  - `docker-compose.yml`
  - `.env.local.example`
  - optional service entrypoints/scripts
- test suites across `tests/unit/`, `tests/contract/`, and selected UI
  tests

## Delivery Strategy

Implementation should proceed in seven waves. Each wave must leave the
repo in a working state.

### Wave 1 — Canonical contracts inside the existing FastAPI surface

**Goal:** add the new `/api/v1` control-plane routes without yet
splitting the runtime process.

**Work:**

1. Add `/api/v1/control-posture`
2. Add `/api/v1/command-sessions`
3. Add `/api/v1/commands`
4. Add `/api/v1/runtime`
5. Add `/api/v1/incidents` and `/api/v1/events`
6. Add `/api/v1/portfolio`, `/api/v1/portfolio/performance`,
   `/api/v1/portfolio/positions`, `/api/v1/portfolio/execution-quality`
7. Add `/api/v1/validation/readiness` plus criterion/history surfaces
8. Add `/api/v1/investigations`, `/api/v1/replays/{id}`, and
   `/api/v1/documents`

**Important rule:** in this wave, the APIs may still read from existing
artifacts where necessary, but they must hide that behind canonical
contracts.

**Exit criteria:**

- frontend has a stable `/api/v1` surface to target
- legacy routes remain functional
- no new UI requirement depends on direct artifact parsing

### Wave 2 — Postgres operational store and outbox/projection layer

**Goal:** move operator-critical state into Postgres.

**Work:**

1. Introduce Postgres connection/config layer
2. Create schemas for:
   - `access`
   - `commanding`
   - `runtime`
   - `incidents`
   - `portfolio`
   - `validation`
   - `investigations`
   - `documents`
   - `system`
3. Add migration tooling
4. Add `system.outbox_event`
5. Add projection checkpoints and projector worker/background runner
6. Start dual-writing canonical command/session/audit/runtime summaries
   into Postgres

**Migration lock:**

- legacy local audit artifacts may continue to exist, but `/api/v1`
  reads should pivot to Postgres as soon as their canonical projection
  exists

**Exit criteria:**

- command/session state no longer depends on local SQLite/file storage
- projections exist for Mission Control, Command Center, and control
  posture

### Wave 3 — Signed command sessions and governed command model

**Goal:** harden the command plane so cloud/mobile can use it safely.

**Work:**

1. Implement command-session lifecycle:
   - create
   - refresh
   - revoke
   - introspect
2. Implement canonical governed write headers:
   - `X-TradingX-Command-Session`
   - `X-TradingX-Timestamp`
   - `X-TradingX-Idempotency-Key`
   - `X-TradingX-Signature`
3. Implement mutation preconditions:
   - `target_resource_id`
   - `expected_resource_version`
   - `expected_state`
   - `requested_transition`
4. Ensure all command-side mutations flow through `POST /api/v1/commands`
5. Normalize `acknowledge_incident`, `create_replay`, and similar writes
   onto the command path
6. Preserve compatibility with the existing Gate 4 local browser-signing
   flow while making the signing-material source session-based

**Exit criteria:**

- no governed write path bypasses command sessions
- last-writer-wins is not legal for safety-critical state
- command history is durable and resumable across reconnects

### Wave 4 — Runtime worker split and lease fencing

**Goal:** separate the long-lived runtime loop from the API process.

**Work:**

1. Introduce a dedicated runtime worker entrypoint
2. Move scheduler-bound runtime execution out of the web process
3. Introduce distributed lease acquisition
4. Stamp runtime/order-path mutations with `lease_epoch`
5. Reject stale-epoch writes
6. Emit incidents on stale-epoch or lease-loss attempts
7. Ensure the control plane consumes runtime heartbeats from the worker,
   not from in-process assumptions

**Exit criteria:**

- runtime worker can run independently of the API service
- only one runtime worker may act for an environment at a time
- Mission Control uses canonical runtime heartbeats from the new seam

### Wave 5 — Job workers for replay, validation, and analytics

**Goal:** move long-running report/replay/analytics work out of the API
path.

**Work:**

1. Introduce a generic job dispatch layer
2. Create job workers for:
   - replay
   - validation packaging
   - PBO/CPCV materialization
   - portfolio analytics refresh
   - report/document generation
3. Materialize portfolio analytics into canonical tables/projections
4. Materialize validation history and evidence references into canonical
   read APIs
5. Materialize replay and investigation metadata into canonical read
   APIs

**Exit criteria:**

- Command Center can track long-running jobs truthfully
- Portfolio and Validation views no longer depend on ad hoc aggregation
- Replay creation is asynchronous and auditable

### Wave 6 — Local multi-service development stack

**Goal:** make the architecture runnable locally with cloud-like
contracts.

**Work:**

1. Add compose stack with:
   - `postgres`
   - `redis`
   - `minio`
   - `control-plane`
   - `runtime-worker`
   - `job-worker`
2. Add local env examples and bootstrap docs
3. Add optional observability profile
4. Ensure local command sessions and signed writes still apply
5. Add smoke verification scripts for local full-stack startup

**Exit criteria:**

- a developer can run the full control-plane topology locally
- local web app can hit the same `/api/v1` contracts used in cloud

### Wave 7 — Staging deployment and frontend cutover start

**Goal:** stand up a first real cloud staging environment and begin
frontend migration onto the canonical control plane.

**Work:**

1. Deploy control plane, runtime worker, job worker, Postgres,
   object-store, and queue to staging
2. Keep staging paper-only and fail-closed
3. Point web app staging build at the new `/api/v1` contracts
4. Migrate the frontend in slices:
   - control posture
   - command center
   - runtime/heartbeat
   - incidents/events
   - portfolio
   - validation
   - replay/investigations

**Exit criteria:**

- staging proves the topology and contracts
- web app can begin consuming the new control plane without legacy
  backend coupling

## Verification Plan

Minimum verification by wave:

### Wave 1

- contract tests for every new `/api/v1` route
- API snapshot tests for critical payloads
- no secret leakage through safe summaries

### Wave 2

- migration tests
- repository/integration tests against Postgres
- outbox/projection consistency tests

### Wave 3

- signed-write tests
- idempotency replay/conflict tests
- mutation-precondition tests
- command-session expiry/refresh/revoke tests

### Wave 4

- runtime worker lease tests
- stale-epoch rejection tests
- heartbeat freshness tests

### Wave 5

- async job lifecycle tests
- command-event timeline tests
- portfolio analytics correctness tests
- validation history and replay metadata tests

### Wave 6

- local compose bring-up smoke test
- end-to-end browser test against local full stack

### Wave 7

- staging health checks
- staging paper-trading smoke verification
- frontend integration checks against `/api/v1`

## Risks and Sequence Traps

1. **Starting with worker split before canonical contracts**
   will create churn in both backend and frontend.
   The `/api/v1` contracts must land first.
2. **Moving analytics before Postgres projections exist**
   will just recreate artifact-shaped reads in a new place.
3. **Adding cloud auth/session semantics without preserving local Gate 4
   compatibility**
   will break the current safe local write flow.
4. **Cutting the frontend over too early**
   will strand the web app between legacy readmodels and incomplete
   control-plane resources.

## Recommended Execution Order

1. Wave 1
2. Wave 2
3. Wave 3
4. Wave 4
5. Wave 5
6. Wave 6
7. Wave 7

This order matters. It reduces thrash and preserves operator truth while
the system is still half-migrated.

## Definition of Done

This implementation program is done when:

1. the web app can operate against the canonical `/api/v1` control plane
   rather than legacy backend coupling;
2. command/session/audit state is Postgres-backed;
3. runtime execution is separated from the API process with lease
   fencing;
4. replay, validation, and analytics run asynchronously through job
   workers;
5. the full architecture is runnable locally through a multi-service
   stack; and
6. a paper-only cloud staging environment is stable enough to support
   the next implementation waves and frontend migration.
