# Gate 2 / Gate 3 / Gate 4 Readiness Master Plan

> **For agentic workers:** this is a master readiness plan, not a
> single narrow code-only branch. Treat the four lanes separately:
> one remaining development lane, two evidence lanes, and one final
> sign-off lane. Do not blur evidence gathering into product changes,
> and do not enable live trading early “just to test.”

**Goal:** finish the remaining work between the now-merged tranche 2
foundation and a real Gate 4 go/no-go decision. This master plan covers:

1. **Gate 4 live enablement development**
2. **Gate 2 robustness evidence**
3. **Gate 3 paper evidence**
4. **Gate 4 operational sign-off evidence**

The important framing is:

- the core research/runtime hardening work is now merged on `main`;
- the only clearly-required **development** arc left is Gate 4 live
  enablement;
- Gate 2 and Gate 3 are mostly **evidence** lanes, not new platform
  engineering; and
- the final “project done” state is: live-ready, safely controlled,
  documented, and sign-offable.

## Authority

1. [.specify/memory/constitution.md](/.specify/memory/constitution.md)
2. [docs/validation/acceptance_gates.md](/docs/validation/acceptance_gates.md)
3. [docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md](/docs/superpowers/specs/2026-04-21-tranche-1-planning-brief.md)
4. [docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md](/docs/superpowers/specs/2026-04-22-tranche-2-planning-brief.md)
5. [docs/operations/operator_manual.md](/docs/operations/operator_manual.md)
6. [docs/archive/implementation_constraints.md](/docs/archive/implementation_constraints.md)

## Completion target

The project is operationally “done” for v1 when all of the following are
true:

- Gate 0, 0.5, 1, 2, and 3 have passing evidence;
- Gate 4-specific live enablement code has landed;
- live trading remains fail-closed until the operator explicitly performs
  the Gate 4 sign-off flow;
- the live-enablement checklist is completed with fresh evidence; and
- the operator has a complete package to make a real go/no-go decision.

## Workstream ranking

| Priority | Workstream | Type | Can start now? | Hard dependencies | Primary output |
|---|---|---|---|---|---|
| 1 | Gate 4 live enablement development | Development | Yes | Current `main` only | Merged live-enable code behind fail-closed controls |
| 2 | Gate 2 robustness evidence | Evidence | Yes | Current `main` only | Gate 2 validation report |
| 3 | Gate 3 paper evidence | Evidence / calendar time | Almost — after one small-but-real report-path fix tranche | Current `main` + a Gate 3 two-sleeve evidence-reader fix | Gate 3 validation report + package |
| 4 | Gate 4 operational sign-off evidence | Operational evidence | No, final lane | Gates 0–3 passing evidence + Gate 4 code merged | Live-enablement checklist + sign-off package |

## Dependency graph

- **Gate 4 live enablement development** can begin immediately.
- **Gate 2 robustness evidence** can begin immediately and can complete
  independently of Gate 4 coding.
- **Gate 3 paper evidence** can begin operationally on the current
  two-sleeve paper runtime, but the governed report/package builder
  still needs one prerequisite fix tranche: the shipped Gate 3
  readiness path both (a) defaults to the legacy single-strategy
  reference `baseline-long-only-v1` in `src/tradingx/gate3.py`, and
  (b) still aggregates whole-book `execution_lifecycles` and
  `closed_trades` instead of building the per-sleeve live fill/notional
  profile that the two-sleeve design expects. So the runtime can keep
  accruing evidence now, but the formal Gate 3 report/package lane
  should not be considered clean until that governed per-sleeve reader
  fix is merged.
- **Gate 4 operational sign-off evidence** must wait until:
  - Gate 2 evidence is complete,
  - Gate 3 evidence is complete,
  - Gate 4 live enablement code is merged, and
  - fresh preflight checks (SMTP, kill switch, monitoring) are run
    inside the required time window.
- **The 7-day monitoring-confirmation clock should start as soon as the
  post-merge Gate 4 code path is in its final intended posture**, not at
  the very end of the sign-off lane. Checklist assembly and operator
  approval stay final, but the observation window should overlap the
  post-merge evidence period instead of adding an extra idle week to the
  critical path.

So the practical order is:

1. start Gate 4 development,
2. run Gate 2 evidence in parallel,
3. accumulate Gate 3 evidence in parallel,
4. finish with the Gate 4 sign-off package.

## Review-sensitive locks

These are the places most likely to create churn if they are not made
explicit up front:

1. **Keep evidence and development separate.** Gate 2 / Gate 3 should
   not smuggle in new feature work unless a real blocker is found.
2. **Gate 4 code must stay fail-closed.** Landing live-enable code does
   not mean turning live trading on. Default behavior remains disabled.
3. **Web/operator write paths need real authentication semantics across
   the full write surface before any live-control flag is accepted.**
   `write_mode_enabled` alone is not sufficient for Gate 4, and the
   requirement applies to web write endpoints broadly, not only a future
   live-toggle endpoint.
4. **Do not reopen strategy development.** New sleeves, Kelly sizing,
   options, meta-labeling, and other future-feature items are out of
   scope for this master plan.
5. **Use existing evidence engines where they already exist.** Gate 2,
   Gate 3, replay-slippage, drift, and report generation should be
   exercised through the shipped paths rather than copied into new ad-hoc
   scripts.
6. **Operator sign-off is a real gate, not a rubber stamp.** The final
   Gate 4 lane is documentation plus fresh evidence plus explicit human
   approval.

---

## Workstream 1 — Gate 4 Live Enablement Development

**Why this is priority 1:** it is the only clearly-required engineering
arc still missing. The repo is still intentionally paper-only, and the
Gate 4 pass criteria explicitly require live-control hardening before
live credentials or live mode can be accepted.

### Goal

Add the missing live-enablement code while keeping every path fail-closed
until operator sign-off happens later.

### Required scope

1. **Live broker/client selection**
   - Add an explicit paper-vs-live broker selection seam.
   - Keep paper as the default.
   - Fail closed if live credentials or preflight requirements are
     missing.

2. **Four-layer live control activation**
   - Use the existing `LiveTradingControls` model in
     [src/tradingx/config.py](/src/tradingx/config.py).
   - Implement the real code paths that decide whether live trading is
     allowed.
   - Preserve the current behavior where orders are blocked unless every
     layer is explicitly enabled.

3. **Secure write path for the full web write surface**
   - Add request signing for web write endpoints broadly.
   - Add idempotency-key handling across the write surface so replayed
     POST actions fail closed.
   - Do not scope this only to a future live-toggle path; the Gate 4
     boundary is the current write surface in `src/tradingx/web/app.py`.

4. **Live-mode preflight / readiness checks**
   - Verify credentials, broker mode, kill switch state, monitoring
     readiness, and any live-mode invariants before activation.
   - Produce explicit machine-readable reasons when live mode is blocked.

5. **Live control-plane tests**
   - Add focused unit/integration tests for:
     - unsigned request rejection,
     - duplicate idempotency-key handling,
     - broad write-surface enforcement rather than one special endpoint,
     - fail-closed live-control enablement,
     - paper/live client selection,
     - blocked live activation when preflight is incomplete.

### Likely file scope

- `src/tradingx/config.py`
- `src/tradingx/risk.py`
- `src/tradingx/controller.py`
- `src/tradingx/service.py`
- `src/tradingx/automation.py`
- `src/tradingx/__main__.py`
- `src/tradingx/web/app.py`
- `src/tradingx/web/runtime.py`
- tests around config, risk, web actions, controller/service startup

### Suggested task breakdown

1. Write a dedicated Gate 4 live-enablement design/implementation plan.
2. Add the live-mode configuration and broker-selection seams.
3. Add request signing + idempotency-key enforcement across the web
   write surface.
4. Add preflight checks and explicit blocked reasons.
5. Add tests for fail-closed behavior.
6. Merge the code while keeping live mode disabled by default.

### Exit criteria

- No live-affecting path can execute without all live-control layers
  enabled.
- Unsigned or replayed live write requests are rejected.
- Live enablement can be tested in code and in live-paper without
  turning real live trading on.

---

## Workstream 2 — Gate 2 Robustness Evidence

**Why this is priority 2:** it is required for Gate 4, but it is not a
new engineering tranche. The shipped adversarial harness already exists.

### Goal

Produce the missing Gate 2 validation report for the shipped sleeves
using the existing validation machinery.

### Required scope

1. Run the already-shipped cost-stress checks.
2. Run the already-shipped parameter-perturbation checks.
3. Run the already-shipped rolling walk-forward checks.
4. Collect the results into a formal Gate 2 validation report.

### Primary sources already in repo

- [src/tradingx/validation.py](/src/tradingx/validation.py)
- [docs/validation/acceptance_gates.md](/docs/validation/acceptance_gates.md)
- [docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md](/docs/adrs/ADR-0022-gate1-reframe-benchmark-stack-and-robustness.md)

### Suggested task breakdown

1. Identify the exact commands/artifacts needed to run the existing
   robustness harness for `trend-following-v1` and `vol-target-v1`.
2. Execute the robustness runs on the current merged code.
3. Capture the resulting artifacts and summaries.
4. Write the Gate 2 validation report.
5. Patch any doc/index entries if the report is frontmatter-indexed.

### Exit criteria

- One governed Gate 2 validation report exists.
- The report cites the real shipped adversarial/evidence artifacts.
- Any failure is explained as evidence, not hidden by retuning.

---

## Workstream 3 — Gate 3 Paper Evidence

**Why this is priority 3:** it is required for Gate 4, but the main
constraint is runtime evidence accumulation, not coding.

**Important correction:** on current `main`, the evidence accumulation
can start immediately, but the formal Gate 3 report/package seam is not
yet fully aligned with the two-sleeve runtime. The current
`build_gate3_readiness_report(...)` path still:

- defaults to `baseline-long-only-v1` for its reference metrics; and
- aggregates the whole book's `execution_lifecycles` / `closed_trades`
  instead of deriving per-sleeve live fill profiles from
  `sleeve_attributions`, even though the two-sleeve design explicitly
  requires that comparison model.

Treat fixing that per-sleeve reader/report seam as a small-but-real
prerequisite tranche for the governed Gate 3 evidence lane.

### Goal

Accumulate the required paper-trading evidence under the now-merged
two-sleeve runtime and package it into the formal Gate 3 decision
artifacts.

### Required scope

1. Run the paper runtime long enough to satisfy:
   - at least 180 calendar days, or
   - at least 100 closed trades,
   whichever comes first.
2. Patch the Gate 3 report/package path so it evaluates the real
   two-sleeve runtime rather than the legacy single-strategy reference
   **and** uses per-sleeve live fill/notional profiles derived from
   `sleeve_attributions`.
   Minimum scope:
   - `src/tradingx/gate3.py`
   - `src/tradingx/execution.py`
   - `src/tradingx/__main__.py`
   - `src/tradingx/web/runtime.py`
3. Preserve and review:
   - paper-trading logs,
   - reconciliations,
   - drift verdicts,
   - replay-slippage evidence,
   - recovery drills,
   - alert drills,
   - incident acknowledgements.
4. Ensure the evidence is gathered under the real two-sleeve runtime
   architecture, not the older single-active-sleeve assumption.
5. Produce the Gate 3 validation report and package.

### Primary sources already in repo

- [docs/validation/acceptance_gates.md](/docs/validation/acceptance_gates.md)
- [docs/operations/operator_manual.md](/docs/operations/operator_manual.md)
- [docs/superpowers/specs/2026-04-18-gate3-operations-evidence-design.md](/docs/superpowers/specs/2026-04-18-gate3-operations-evidence-design.md)
- [docs/superpowers/specs/2026-04-18-replay-slippage-evidence-design.md](/docs/superpowers/specs/2026-04-18-replay-slippage-evidence-design.md)

### Suggested task breakdown

1. Apply the Gate 3 two-sleeve package fix so the governed
   report/package builder:
   - points at the real two-sleeve runtime, and
   - computes per-sleeve live fill/notional profiles from
     `sleeve_attributions` rather than aggregating the whole book.
2. Freeze the runtime configuration used for the Gate 3 evidence window.
3. Run the paper session on that frozen configuration.
4. Schedule regular evidence refreshes:
   - replay-slippage
   - drift summaries
   - Gate 3 readiness rollups
5. Execute required restart/recovery drills.
6. Execute the required SMTP emergency round trip.
7. Generate the Gate 3 validation report.
8. Generate the Gate 3 evidence package.

### Exit criteria

- Gate 3 evidence is complete against the current acceptance-gate
  criteria.
- The report/package are built from persisted artifacts, not operator
  memory.
- The evidence window uses the real multi-sleeve runtime.
- The governed report/package path no longer depends on
  `baseline-long-only-v1` as its implicit reference.
- The governed Gate 3 reader compares each sleeve against its own
  backtest expectations using per-sleeve live fill/notional profiles,
  not a whole-book aggregate.

---

## Workstream 4 — Gate 4 Operational Sign-off Evidence

**Why this is priority 4:** this is the final gate, and it only becomes
valid after the other three workstreams are complete.

### Goal

Build the final operator-facing package that supports a real live
go/no-go decision.

### Required scope

1. Verify all prerequisite gates have passed:
   - Gate 0
   - Gate 0.5
   - Gate 1
   - Gate 2
   - Gate 3
2. Run the Gate 4 time-window-sensitive checks:
   - kill switch tested in live-paper within 7 days
   - monitoring confirmed for at least 7 days
   - SMTP emergency round trip passed within 7 days
3. Confirm starting live capital is <= 10% of paper-traded notional.
4. Confirm live-control code remains fail-closed until explicitly
   enabled.
5. Produce the live-enablement checklist and validation package.
6. Obtain explicit operator sign-off.

### Suggested task breakdown

1. Create a Gate 4 checklist artifact if one does not already exist.
2. As soon as the merged Gate 4 code path reaches its final intended
   posture, start the 7-day monitoring-confirmation window.
3. Populate the checklist from the passing Gate 0–3 evidence and fresh
   preflight checks.
4. Run the live-paper kill-switch drill inside the required time window.
5. Run a fresh SMTP round trip inside the required time window.
6. Confirm monitoring stability over the required time window.
7. Record capital allocation and final blocked/allowed live-control
   state.
8. Produce the final Gate 4 validation package for operator sign-off.

### Exit criteria

- A single package exists that a human operator can use to say “yes,
  we can enable live trading” or “no, not yet.”
- Every Gate 4 criterion in
  [acceptance_gates.md](/docs/validation/acceptance_gates.md) has
  evidence attached.
- The sign-off is explicit and auditable.

---

## Recommended execution order

### Phase A — Start now, in parallel

1. Open the **Gate 4 live enablement development** spec/plan and begin
   implementation.
2. Start **Gate 2 robustness evidence** using the existing harness.
3. Start runtime-level **Gate 3 paper evidence** accumulation on the
   current merged runtime.

### Phase B — Merge the last required code

4. Merge Gate 4 live-enablement code behind fail-closed controls.
5. Merge the Gate 3 two-sleeve package fix if it did not already land
   during the evidence lane.

### Phase C — Finish the evidence lanes

6. Start the Gate 4 monitoring-confirmation clock as soon as the merged
   Gate 4 posture is final.
7. Finish the Gate 2 validation report.
8. Let Gate 3 evidence mature until its pass criteria are satisfied.
9. Generate the Gate 3 report/package.

### Phase D — Final live decision package

10. Run the fresh Gate 4 preflight checks.
11. Build the Gate 4 checklist/package.
12. Obtain operator sign-off.

## Explicitly out of scope

This master plan does **not** include:

- fractional Kelly sizing;
- new sleeves or strategy families;
- options expansion;
- meta-labeling;
- HMM regime models;
- multi-account architecture;
- execution-model research beyond what Gate 4 needs.

Those remain future-feature work after v1 is already live-ready.

## Bottom line

For project completion, there is **one remaining major engineering
lane**, **one small-but-real Gate 3 prerequisite fix tranche**, and
**three readiness lanes**:

- build Gate 4 live enablement,
- patch the Gate 3 report/package seam so it uses the real two-sleeve
  runtime and per-sleeve live evidence,
- produce Gate 2 evidence,
- produce Gate 3 evidence,
- package Gate 4 sign-off.

That is the shortest honest path to “the project is done.”
