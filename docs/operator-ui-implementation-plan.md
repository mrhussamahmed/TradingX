# TradingX Operator UI Implementation Plan

Date: 2026-04-28
Status: ready for adversarial review

## Objective

Make the TradingX web app useful to a real trader/operator under time
pressure. The first screen must answer whether the bot is running, safe,
allowed to trade, fresh, blocked, profitable, exposed, and explainable.
The UI must not show green status from declared config alone.

## Approved Scope

1. Restore and make Mission Control the default operator home.
2. Reframe navigation around operator questions instead of internal
   architecture.
3. Add evidence-first safety logic for the main verdict.
4. Add drill-down paths from summary cards into the existing detailed
   views.
5. Preserve existing specialized views and backend API contracts.
6. Label missing/stale backend evidence explicitly instead of inventing
   synthetic healthy state.

## Implemented Work

### Mission Control

- Added `OperatorMissionControlFlavor`.
- Added first-60-seconds cards:
  - Bot runtime
  - Allowed to trade
  - Today P&L
  - Open risk
  - Operator attention
  - Evidence freshness
  - Last trade decision
  - Next evaluation
- Added attention queue for kill switch, failing/degraded gates,
  incidents, stale evidence, and missing decision evidence.
- Added Evidence Trust Ledger covering:
  - Declared config
  - Calculated state
  - Measured result
  - Research/backtest evidence
  - Paper/live-shadow/live result class
  - Missing evidence

### Safety Verdict Model

- Added `OperatorMissionControlModel`.
- Safety severity order:
  1. Manual kill switch
  2. Failing risk gates
  3. Degraded/watching gates
  4. Runtime failed/halted/error
  5. Live trading flag enabled
  6. Required safety evidence stale or missing
  7. Paper-only allowed state
  8. Ambiguous mode review
- Live-enabled config remains risk-level even when evidence is stale.
- Runtime unhealthy state cannot show a green paper-only verdict.
- Evidence freshness is derived from required safety evidence classes,
  not the newest timestamp from any source.

### Required Safety Evidence Classes

Mission Control now requires these classes before allowing a current
evidence posture:

- Heartbeat evidence
- Gate evidence
- Portfolio evidence
- Decision evidence

Gate evidence is present only when actual gate statuses or Gate 3
criteria exist. A fresh command-center timestamp with no gates does not
count.

The clock advances while Mission Control is open, so stale evidence can
age past the threshold without a page reload.

### Navigation

- Default flavor changed to Mission Control.
- Existing route labels now match trader intent:
  - What is happening now
  - Is the bot safe
  - What did it do
  - Why did it happen
  - What risk is open
  - Is it working
  - Which strategy next
  - What can I do
  - Can I trust it
- Shortcut mapping updated for seven operator views.
- Legacy stored `market-chart` startup preferences migrate to Mission
  Control.

### Preferences and Settings

- Preference schema migration added for legacy startup defaults.
- Save-defaults flow now returns the persisted preference shape.
- Save confirmation now reports the newly selected startup view instead
  of stale context state.

## Data/API Assumptions

- The frontend uses existing local APIs only.
- No fake backend behavior was added.
- Missing backend fields are surfaced as missing, stale, or unavailable.
- Paper/live-shadow/live distinction remains limited by current API
  contracts.

## Backend Gaps Still Blocking Full Fidelity

- No structured decision detail endpoint with:
  - Signal inputs
  - Regime inputs
  - Risk checks
  - Decision result
  - Execution result
  - Evidence reference
  - Related logs/events
  - Data freshness at decision time
  - Paper/live-shadow/live mode
- No dedicated system-health endpoint for:
  - Market data feed freshness
  - Broker/API connection health
  - Scheduled job health
  - Cache freshness
  - Manifest validation
  - Broken evidence files
- No separate result ledgers for backtest, paper, live-shadow, and live.
- No first-class week/month/month-to-date P&L contract in current
  frontend types.

## Files Changed

- `docs/operator-ui-redesign-plan.md`
- `docs/operator-ui-implementation-plan.md`
- `webapp/src/control-center/flavors/OperatorMissionControlFlavor.tsx`
- `webapp/src/control-center/flavors/OperatorMissionControlModel.ts`
- `webapp/src/control-center/flavors/__tests__/OperatorMissionControlFlavor.test.ts`
- `webapp/src/control-center/canvas/Canvas.tsx`
- `webapp/src/control-center/canvas/ViewFlavorSwitcher.tsx`
- `webapp/src/control-center/canvas/ViewDefaultsDrawer.tsx`
- `webapp/src/control-center/shell/LeftNav.tsx`
- `webapp/src/control-center/state/types.ts`
- `webapp/src/control-center/state/PreferencesContext.tsx`
- `webapp/src/control-center/__tests__/ControlCenterApp.test.tsx`
- `webapp/src/control-center/state/__tests__/PreferencesContext.test.tsx`
- `webapp/src/control-center/state/__tests__/useFlavorShortcuts.test.tsx`

## Test Coverage Added

- Mission Control renders as default.
- Trader-intent navigation labels are present.
- Drawer startup-view persistence reports the newly saved value.
- Legacy `market-chart` startup preferences migrate to Mission Control.
- Shortcut mapping covers Mission Control through Evidence & Why.
- Runtime failure cannot produce a green safety verdict.
- Live-enabled config remains risk-level even with stale evidence.
- Required safety evidence becomes stale after the threshold.
- Fresh noncritical evidence cannot replace required safety evidence.
- Empty gate data does not count as gate evidence.
- Gate status data can count as gate evidence.
- Synthetic UI refresh timestamps do not count as source evidence.

## Verification

Latest local verification:

```bash
npm --prefix webapp test
npm --prefix webapp run lint -- --quiet
npm --prefix webapp run build
```

Expected build note: Vite still reports the existing chunk-size warning
after production build. This is not introduced as a functional failure.

## Adversarial Review Packet

Reviewers should try to break the implementation with these questions:

1. Can any known risk-level condition be downgraded by missing or stale
   evidence?
2. Can any declared config alone produce a green safety state?
3. Can a fresh but irrelevant timestamp make required safety evidence
   look current?
4. Can empty gate data satisfy the gate evidence requirement?
5. Does the verdict change if the dashboard remains open beyond the
   stale threshold?
6. Does a runtime failure, halt, or error ever show as safe to run?
7. Does live trading enabled ever show below risk severity?
8. Do old localStorage preferences keep existing users away from the new
   Mission Control default?
9. Do every major summary card and attention item drill into a useful
   detailed view?
10. Does the UI clearly label backend/API gaps instead of pretending the
    data exists?

## Known Residual Risks

- Decision evidence is still coarse because the backend does not expose
  a structured decision-detail contract.
- Gate evidence can prove that a gate record exists, but it cannot yet
  prove complete per-gate calculation lineage without a richer backend
  payload.
- Evidence age updates once per minute while Mission Control is mounted,
  so sub-minute stale threshold behavior is intentionally not modeled.
- The existing production bundle remains above Vite's default chunk-size
  warning threshold.
