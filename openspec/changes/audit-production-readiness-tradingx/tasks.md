## 1. OpenSpec Setup

- [x] 1.1 Verify `openspec/` was absent before initialization.
- [x] 1.2 Run `openspec init`.
- [x] 1.3 Create change `audit-production-readiness-tradingx`.
- [x] 1.4 Create proposal, design, tasks, and ten subsystem spec files.
- [x] 1.5 Validate the OpenSpec change with `openspec validate audit-production-readiness-tradingx --strict`.

## 2. Project Mapping

- [x] 2.1 Read root README, package manifests, key runtime docs, and architecture map.
- [x] 2.2 Map CLI commands, Python entry points, backend API surface, frontend contract, and runtime lifecycle.
- [x] 2.3 Map paper/live broker boundary, authorization model, and web write-action signing model.
- [x] 2.4 Map persistence, evidence, scheduler, automation, recovery, and validation gate lifecycles.
- [x] 2.5 Record architecture map updates in `design.md`.

## 3. Safe Verification

- [x] 3.1 Check dependency state and install with `uv sync --all-groups` only if needed.
- [x] 3.2 Check frontend dependency state and run `npm --prefix webapp install` only if needed.
- [x] 3.3 Run `config-summary` and `live-disable-status` with redacted result notes.
- [x] 3.4 Run `./scripts/validate-fast`.
- [x] 3.5 Run `npm --prefix webapp test`.
- [x] 3.6 Run `npm --prefix webapp run build`.
- [x] 3.7 Run `uv build`.
- [x] 3.8 Run `./scripts/validate` if safe and record skipped smoke gates.

## 4. Critical User Flows

- [x] 4.1 Review safe-config verification flow.
- [x] 4.2 Start the local Control Center backend safely and inspect read APIs; record visual UI inspection as not verified.
- [x] 4.3 Review Runtime Host start/stop flow without unbounded automation.
- [x] 4.4 Review manual paper cycle and recurring service safety for `SPY,QQQ,IWM`.
- [x] 4.5 Review bounded market-day automation and recurring scheduler safety.
- [x] 4.6 Review evidence, recovery/drills, and validation artifact flows.
- [x] 4.7 Record unavailable flows as `not verified` with reasons.

## 5. Deep Review

- [x] 5.1 Review live-trading fail-closed controls and broker submission paths.
- [x] 5.2 Review duplicate paper submission and idempotency controls.
- [x] 5.3 Review web write authorization and request signing controls.
- [x] 5.4 Review scheduler lifecycle, stop conditions, and market-calendar logic.
- [x] 5.5 Review evidence integrity, path stability, and secret redaction.
- [x] 5.6 Review persistence behavior across legacy local and optional Postgres modes.
- [x] 5.7 Review frontend/backend API contract and UI safety states.
- [x] 5.8 Review test coverage and identify missing critical coverage.

## 6. Fixes

- [x] 6.1 Prioritize findings in `design.md`.
- [x] 6.2 Select highest-impact fixes that are safe, scoped, and locally verifiable.
- [x] 6.3 Add failing tests before production code for any bug fix.
- [x] 6.4 Implement safe fixes.
- [x] 6.5 Rerun focused and relevant broader verification.
- [x] 6.6 Address follow-up Gate 4 artifact schema review finding.

## 7. Reports

- [x] 7.1 Produce the engineering findings report.
- [x] 7.2 Produce the prioritized fix plan.
- [x] 7.3 Produce the non-technical summary.
- [x] 7.4 Produce the adversarial reviewer committee report.
- [x] 7.5 Update OpenSpec tasks and final audit log.
