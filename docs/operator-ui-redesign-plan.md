# TradingX Operator UI Flow Map and Implementation Plan

Date: 2026-04-28

## Mental-Flow Map

| Use case | User goal | Starting point | Trader questions | Required data | Required UI | Navigation path | Expected action | Current support | Missing support | Recommended UI change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Quick status update | Decide if the bot can keep running | Mission Control | Is it running, safe, allowed to trade, stale, blocked, or degraded? | Runtime state, heartbeat, write mode, gates, incidents, data timestamps, next evaluation | First-60-second status cards, attention queue, safety verdict | What is happening now -> Is the bot safe | Continue, pause, inspect, or resume | Top strip and operator rail have fragments | No single explainable verdict; missing evidence freshness summary | Add Mission Control with safety verdict, blockers, freshness, last decision, next eval, drill-down buttons |
| Today's trading activity | Understand what happened today | Today's Activity | What opened, closed, skipped, rejected, or blocked? Why? | Replay events, digest, service cycles, execution events, blocked counts | Timeline lanes, decision summary, digest cards | What did it do -> Why did it happen | Investigate a trade/skip or export digest | Timeline exists | Needs stronger link from summary into replay/evidence | Mission Control should surface last decision and route to Today's Activity / Evidence & Why |
| Performance | Check if results are positive and meaningful | P&L / Positions | Today/week/month P&L, benchmark comparison, evidence mode | Account summary, portfolio analytics, benchmark rows, source notes | P&L cards, equity curve, benchmark table, data-mode badge | Is it working | Continue monitoring or investigate performance | Portfolio/performance views exist partly | Confidence/source context can be hard to find from home | Mission Control shows P&L with data mode/evidence label and routes to P&L / Positions |
| Risk | Inspect current exposure and controls | Risk & Safety / Open Risk | What is open, near limits, halted, concentrated? | Positions, exposure, gates, Gate 3 criteria, incidents, kill switch | Risk verdict, gates, positions, incident list, controls | Is the bot safe -> What risk is open | Pause, flatten, reduce risk, inspect gate | Risk Core and Open Risk exist | Home does not prioritize open risk and blockers | Add safety card, open-risk summary, active controls, blocker queue |
| Debug bot behavior | Explain a behavior | Evidence & Why | Was data stale, signal missing, risk block, execution fail? | Replay events, timeline, artifact path, related IDs | Decision explorer with selected event inspector | Why did it happen | Open artifact/runbook, fix data/config/process | Evidence Replay exists | No home route from last decision/skips; limited structured fields from backend | Add "Last decision" card with why route; note backend gap for structured decision payload |
| Strategy quality | Decide what strategy needs work | Strategy Quality | Which works, degrades, or lacks evidence? | Candidate summaries, gate statuses, model weights, support trades | Candidate table, inspector, blocked promotion explanations | Which strategy next | Promote/demote/quarantine/investigate | Strategy view exists | Home does not show strategy evidence posture | Add strategy evidence card and route to Strategy Quality |
| Market/regime context | Check regime inputs | Mission Control / Strategy Quality | What regime is active and what strategies are enabled? | Runtime heartbeat truth, opportunity scores, activation, selection | Regime/data card, signal ladder | What is happening now -> Which strategy next | Investigate missing/stale regime inputs | Runtime selection exists | No explicit regime monitor route/data contract | Surface available runtime truth; mark missing regime API as backend gap |
| System health | Check pipelines and scheduler | Today's Activity / Evidence & Why | Are feeds, jobs, broker/API, caches fresh? | Scheduler state, heartbeat, incidents, explorer/docs, generated timestamps | Freshness ledger, scheduler status, stale warnings | What needs my attention -> System/Audit | Restart scheduler or investigate stale evidence | Scheduler/top strip exist | Missing pipeline-level health endpoint | Add freshness ledger using available timestamps; document backend health gap |
| Operator decisions | Choose pause/resume/reduce/investigate | Operator rail / Mission Control | What can I safely do now? Why is a button disabled? | Write-mode state, kill switch, runtime state, gates, positions | Controls with blockers and route-to-fix | What can I do | Resume, stop, pre-open, close session | Operator rail exists | Decision support not centralized | Mission Control attention queue explains blocking reasons and routes to controls |
| Audit and evidence | Trust the dashboard | Evidence & Why | Is this declared, calculated, measured, paper, live-shadow, or stale? | Source notes, evidence refs, generated_at, artifact paths, report IDs | Evidence trust ledger, source labels, stale/missing badges | Can I trust it | Accept, refresh, inspect artifact, withhold confidence | Evidence timeline exists | Status can look green without evidence context | Add evidence trust ledger and never present missing evidence as healthy |

## Current UI Gap Analysis

- The app already has intent-oriented navigation labels and specialized views for P&L, strategy quality, today's activity, risk, open risk, and evidence replay.
- The default Mission Control route is wired in navigation and tests but the component file is missing, so the app cannot compile.
- The top strip and operator rail answer parts of "is it running?" and "is it safe?", but no main view synthesizes the first 60 seconds of operator questions.
- Existing green/risk cards often show state without a nearby evidence timestamp or source type.
- The app has replay events and artifact paths, but the dashboard does not route directly from the latest decision or blocker into the "why" surface.
- Current backend data does not expose a fully structured trade-decision object with signal inputs, regime inputs, risk checks, execution result, evidence ref, data freshness at decision time, and mode. The UI must label this as unavailable rather than inventing it.
- There is no dedicated pipeline-health contract for feed freshness, broker connection freshness, cache state, or manifest validation.
- Week/month P&L, live-shadow/live result separation, and confidence levels are not fully available in current frontend types.

## Proposed Routes and Views

- Keep existing flavor routes and rename/group them by trader intent:
  - Mission Control: What is happening now?
  - Risk & Safety: Is the bot safe?
  - Today's Activity: What did it do?
  - Evidence & Why: Why did it happen and can I trust it?
  - P&L / Positions: Is it working?
  - Strategy Quality: Which strategy next?
  - Open Risk: What risk is open?
- Add the missing `OperatorMissionControlFlavor` as the default view.
- Use existing APIs only. Any missing field appears as missing/stale/unavailable, not as a fake healthy status.

## Component Changes

- Add safety verdict cards for runtime, trade permission, gates, open risk, alerts, data freshness, evidence freshness, last decision, next evaluation, market/session state, and P&L.
- Add an attention queue that ranks blockers and degraded/missing evidence.
- Add drill-down buttons that switch to existing views using `setActiveFlavor`.
- Add an evidence trust ledger distinguishing calculated state, measured/paper result, declared config, research/backtest evidence, missing evidence, and stale/partial evidence.
- Preserve existing top strip, left nav, operator rail, and specialized views.

## Data Model and API Assumptions

- Existing frontend data is authoritative only for the fields returned by `DataContext`: command center, config summary, runtime state/heartbeat, incidents, replay, explorer, portfolio, research, Gate 3 readiness, runtime activation/model/selection, scheduler.
- Dashboard freshness is inferred from `generated_at_utc`, heartbeat timestamps, runtime update timestamps, and evidence/artifact timestamps.
- Current mode defaults to paper where `paper_only_mode` is true. Live/live-shadow/paper/backtest distinctions require backend fields before the UI can make stronger claims.
- Missing structured decision data is shown as missing evidence and linked to Evidence & Why.

## Mock-Data Strategy

- Do not add mock backend behavior.
- The UI uses existing default empty snapshots from `DataContext` and labels them as waiting, missing, unavailable, or no evidence yet.
- Any inferred status is phrased as an inference from available local evidence.

## Priority Order

1. Restore build by adding Mission Control.
2. Make Mission Control answer the first 60 seconds of operator questions.
3. Add drill-down paths into the existing specialized views.
4. Add evidence-type and freshness labels.
5. Document backend/API gaps that block full decision-explorer fidelity.

## Risks

- Some status remains inferred because backend contracts are not granular enough.
- Mission Control can become too dense; keep cards compact and route to detail views.
- Existing dirty frontend changes are preserved and built upon rather than reverted.

## Files Expected to Change

- `docs/operator-ui-redesign-plan.md`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`
- Existing modified navigation/preferences/test files are preserved.
