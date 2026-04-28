# TradeX View Flavor Control Center — Implementation Handoff

Date: 2026-04-27
Branch: `prototype/tradex-view-flavor-ui-gemini`
Plan: [2026-04-27-view-flavor-control-center-plan.md](2026-04-27-view-flavor-control-center-plan.md)

## Summary

The TradeX webapp now uses the Canvas-first + Settings defaults architecture
described in the plan. The shell is implemented inside `webapp/src/control-center/`
and replaces the previous `App.tsx` workspace UI. All six view flavors are
selectable, the Operator Command Rail is live with safety-gated actions and a
collapsible emergency strip, the View Defaults drawer persists preferences via
validated localStorage, and Cmd+1 through Cmd+6 switch the active flavor when
the operator is not interacting with text inputs or dialogs.

The implementation is wired to existing production data sources only. No new
backend routes were created. Where a backend capability is missing (Kill Switch,
Flatten All, per-strategy approval write, per-gate run, per-symbol OHLC), the
UI shows the safety-theatre flow but disables the destructive button and names
the missing capability.

## Files changed

### Removed (old workspace UI)
- `webapp/src/App.css` — global stylesheet for the prior shell
- `webapp/src/App.test.tsx` — integration tests for the old `App.tsx`
- `webapp/src/platform/ui.tsx` — Panel/StatusBadge/EmptyState primitives bound to old CSS
- `webapp/src/platform/charts.tsx` — chart helpers used only by old workspaces
- `webapp/src/platform/mission-control.tsx`
- `webapp/src/platform/portfolio.tsx`
- `webapp/src/platform/research.tsx`

### Updated
- `webapp/src/App.tsx` — now a thin re-export of `ControlCenterApp`
- `webapp/src/index.css` — minimal reset + Inter font load (Canela headings dropped)
- `webapp/src/test/setup.ts` — adds `cleanup()` and a `MapStorage` polyfill (Node 22's experimental localStorage shadows jsdom's; the polyfill restores standard Storage semantics)
- `webapp/package.json` — adds `lucide-react@^0.460.0`

### Preserved (unchanged)
- `webapp/src/api.ts` — signed-write fetch client
- `webapp/src/types.ts` — backend contract types
- `webapp/src/main.tsx` — root mount
- `webapp/src/platform/format.ts` — formatters (`prettyLabel`, `toCurrency`, `formatTimestamp`, …)
- `webapp/vite.config.ts`, `tsconfig.app.json`, `eslint.config.js`, `index.html`

### New: control-center layer
| Path | Purpose |
| --- | --- |
| `src/control-center/ControlCenterApp.tsx` | Top-level providers, shell composition, dialog orchestration |
| `src/control-center/state/types.ts` | `ViewFlavor`, `CanvasDensity`, `AccentTheme`, `FLAVORS`, `SYSTEM_DEFAULTS`, `AutoSwitchSuggestion` |
| `src/control-center/state/PreferencesContext.tsx` | Validated localStorage preferences + manual-override flag + save/reset |
| `src/control-center/state/DataContext.tsx` | Centralized API fetcher (15 endpoints), refresh interval, signed-write unlock, `runAction` wrapper |
| `src/control-center/state/ToastContext.tsx` | 4-tone toast feed (info / good / watch / risk) |
| `src/control-center/state/useFlavorShortcuts.ts` | Cmd/Ctrl+1–6 with input/textarea/select/dialog suppression |
| `src/control-center/state/useAutoSwitchSuggestion.ts` | Suggestion-only auto-switch with 60-second activity gate |
| `src/control-center/styles/tokens.css` | Color/typography/spacing/density tokens (lifted verbatim from prototype) |
| `src/control-center/styles/global.css` | Utility classes, panel/badge/button styling |
| `src/control-center/shell/Brand.tsx` | TradeX logo (lifted from prototype) |
| `src/control-center/shell/LeftNav.tsx` | Real navigation: 14 items, flavor mapping, environment card from `ConfigSummary` |
| `src/control-center/shell/TopStatusStrip.tsx` | 8 status cards from `CommandCenter`/`ConfigSummary`/`RuntimeHeartbeat`/`Incidents` |
| `src/control-center/shell/OperatorRail.tsx` | Operator commands, runtime/gate/alert sections, collapsibility, `deriveResumeBlocker` |
| `src/control-center/shell/Shell.module.css` | Shell grid, nav, top strip, rail (with collapsed mode) |
| `src/control-center/canvas/Canvas.tsx` | Switcher + flavor renderer + transition badge + override pill + suggestion banner + system defaults hint |
| `src/control-center/canvas/Canvas.module.css` | Canvas chrome, drawer, toasts, mini-thumbnails |
| `src/control-center/canvas/ViewFlavorSwitcher.tsx` | Six tab cards with shortcuts (lifted + adapted) |
| `src/control-center/canvas/ViewDefaultsDrawer.tsx` | Default flavor / density / theme / 4 toggles + Save/Reset, no preset name (prototype-only field removed) |
| `src/control-center/canvas/Toasts.tsx` | Toast renderer |
| `src/control-center/dialogs/ConfirmDialog.tsx` | Generic alertdialog with focus management, ESC-to-close |
| `src/control-center/dialogs/KillSwitchDialog.tsx` | Typed-phrase confirmation (`KILL TRADINGX`), gates on backend + already-active state |
| `src/control-center/dialogs/FlattenAllDialog.tsx` | Typed-phrase confirmation (`FLATTEN ALL`), shows affected positions |
| `src/control-center/dialogs/Dialog.module.css` | Dialog scrim, header, body, footer styling |
| `src/control-center/flavors/Flavor.module.css` | Flavor layouts, panels, charts, timelines, gate nodes, constellation nodes |
| `src/control-center/flavors/FlavorPlaceholder.tsx` | Shared placeholder card |
| `src/control-center/flavors/EvidenceTimeline.tsx` | Filterable, paginated timeline (>100 rows → pagination) used by 3 flavors |
| `src/control-center/flavors/MarketChartFlavor.tsx` | Symbol picker, equity-curve chart, KPIs, gate cards, exposure, evidence |
| `src/control-center/flavors/StrategyForgeFlavor.tsx` | Candidate table, model weights, opportunity ranking, inspector with approval gate |
| `src/control-center/flavors/MarketDayOpsFlavor.tsx` | Multi-lane operations timeline, operator action grid wired to existing endpoints, daily digest export |
| `src/control-center/flavors/RiskCoreFlavor.tsx` | Custom SVG radial gate graph (1- or 2-ring layout), inspector, incidents, promotion readiness |
| `src/control-center/flavors/PortfolioConstellationFlavor.tsx` | Custom SVG account → sleeves → symbols layout with table-first fallback for sparse data |
| `src/control-center/flavors/EvidenceReplayFlavor.tsx` | Multi-track replay timeline + event inspector + evidence table |

### Test suite (58 tests across 6 files)
- `src/control-center/__tests__/ControlCenterApp.test.tsx`
- `src/control-center/state/__tests__/PreferencesContext.test.tsx`
- `src/control-center/state/__tests__/useFlavorShortcuts.test.tsx`
- `src/control-center/shell/__tests__/derive.test.ts`
- `src/control-center/dialogs/__tests__/KillSwitchDialog.test.tsx`
- `src/control-center/flavors/__tests__/EvidenceTimeline.test.tsx`

## Prototype reuse

### Reused verbatim
- `tokens.css` and `global.css` — color, spacing, typography, density tokens; data-theme/data-density attribute system
- `Shell.module.css` (shell grid, rail, status card, operator command, gate row, alert row)
- `Canvas.module.css` (flavor bar, drawer, transition badge, mini-thumbnails)
- `Flavor.module.css` (panels, simple table, evidence filters, timeline, replay tracks, constellation/gate nodes)
- `Brand.tsx`
- `ViewFlavorSwitcher.tsx` shape (with the six FLAVORS metadata)
- The shape of `PreferencesContext`, `ToastContext`, and `useFlavorShortcuts`

### Reused with adaptation
- `LeftNav` — replaced mock NAV_ITEMS with a real ID-based map; clicks set the active flavor when the nav item is flavor-mapped, open the View Defaults drawer for Settings, and surface trading mode + write mode from `ConfigSummary`. Active selection auto-syncs to `prefs.activeFlavor` when shortcuts fire.
- `TopStatusStrip` — replaced ENVIRONMENT mock with `CommandCenterSnapshot`, `ConfigSummary`, `RuntimeHeartbeatSnapshot`, and `IncidentRecord[]`. Added `deriveRiskTone`, `deriveRuntimeTone`, and `describePnl` helpers (also used for tests).
- `OperatorRail` — added real gating via `deriveResumeBlocker`, collapsibility based on viewport + pin-emergency-controls preference, and an `onCollapsedChange` callback that drives the shell grid.
- `Canvas` — added auto-switch suggestion banner, manual-override pill with Resume auto-switch, system-defaults hint banner, dismiss button, and density-aware sub-title.
- `ViewDefaultsDrawer` — kept default flavor select, density toggle, theme toggle, and the four preference toggles. Removed the prototype-only "preset name + save preset" inert field. Surfaces a watch banner when localStorage is unavailable.
- `Toasts` — broadened from prototype's two tones to four (info / good / watch / risk) and supports click-to-dismiss + keyboard activation.
- The six flavor visual layouts were rewired to consume real API snapshots rather than mock arrays. Where a prototype feature has no backing data (per-symbol OHLC, RSI strip, replay playback, model backtest series), the related controls are disabled with explanatory copy rather than rendering fake data.

### Discarded
- `webapp-prototype/src/mock/index.ts` and every prototype usage of it
- The prototype's preset-name save field in the drawer (was inert)
- The prototype's "evidence-on/off" canvas button that did nothing — replaced with a real toggle bound to `prefs.showEvidenceLayer`
- The prototype's per-row mock evidence inspector content; replaced with real `OperatorTimelineEvent` rendering
- The prototype's replay playback (Play/Pause/Step) is shown but disabled with a clear note that the backend currently exposes a static replay snapshot

## View flavor coverage

### Market Chart (full)
- **Production data:** `commandCenter.watchlist`, `commandCenter.account_summary`, `commandCenter.gate_statuses`, `commandCenter.exposure_breakdown`, `portfolio.equity_curve.points`, `runtimeHeartbeat`, `incidents`, `replay.events`, `explorer`
- **Empty states:** "No symbols configured" if watchlist is empty; equity-curve panel falls back to `commandCenter.equity_curve` then to the `portfolio.equity_curve.headline/detail` empty card; "No gate evidence yet" and "No active exposure" panels
- **Interactions:** Symbol picker chips select active symbol; timeframe buttons (only `1D` interactive — backend has daily granularity only); evidence timeline filters/search/pagination; evidence layer toggle reflects in the table
- **Limitations:** Per-symbol OHLC, RSI, and Compare/Indicators panels are disabled with the note "(per-symbol OHLC not in current API)" until the backend exposes a time-series endpoint

### Strategy Forge (v1)
- **Production data:** `research.candidate_summaries`, `runtimeModel.weights`, `runtimeSelection.ranked_opportunities`, `gate3Readiness`
- **Empty states:** "No candidates yet" lists `research.decision_summary`; "No model weights yet"; "No opportunities ranked"
- **Interactions:** Candidate row click selects, inspector renders metrics + adversarial checks; Approve / Reject / Simulate buttons exist with explicit blocked-reason copy
- **Limitations:** No `New Strategy`, `Approve`, `Reject`, or `Simulate` write endpoints exist — buttons are disabled. `Approve` shows the canonical message "Approval blocked: your operator role cannot approve strategy promotion. Request review from an authorized approver." It also blocks if adversarial checks or gate evidence is incomplete.

### Market Day Ops (full)
- **Production data:** `schedulerState`, `runtimeState`, `runtimeHeartbeat`, `replay.events` (lane-bucketed), `portfolio.positions_panel`, `commandCenter.exposure_breakdown`, `digest`, `commandCenter.service_status`, `incidents`
- **Empty states:** "No timeline events yet" with start-the-runtime guidance; "No open positions" from portfolio detail; "No digest available yet"
- **Interactions:** Six operator actions wired to existing endpoints (`postSessionPreopen`, `postSessionHeartbeat`, `postRuntimeHostStart`, `postRuntimeHostStop`, `postSessionClose`, plus client-side digest export). Timeline shows a live "NOW" marker and a 24-tick header.
- **Limitations:** Operator action buttons are disabled with the write-mode reason when web writes are locked. Timeline playback (play/pause/step) is intentionally not exposed because the data is a snapshot, not a stream.

### Risk Core (full)
- **Production data:** `commandCenter.gate_statuses`, `gate3Readiness.criteria`, `gate3Package`, `incidents`, `configSummary.live_disable_report`
- **Empty states:** "No gate evidence yet" + "No incidents recorded"; if `manual_kill_switch_active` is true, a dedicated red panel surfaces "Kill Switch is active"
- **Interactions:** Click any gate node to populate the inspector with status, threshold, observed value, and evidence refs. `Generate Gate 3 Report` calls `postGate3Report`. Each incident has an `Acknowledge` action that calls `postAcknowledgeIncident`. Filter dropdown narrows nodes by tone (pass / watch / fail / pending).
- **Limitations:** `Run Gate Check` is disabled with note "(no per-gate endpoint)"; `Create Blocker` is not implemented (no endpoint).

### Portfolio Constellation (v1 with sparse fallback)
- **Production data:** `portfolio.positions_panel.positions`, `portfolio.strategy_panel.strategies`, `portfolio.benchmark_panel.benchmark_rows`, `portfolio.diagnostics`
- **Empty states:** Sparse mode (≤1 position, no strategies) hides the constellation graph and renders the table-only fallback per the plan. Strategy attribution and benchmark panels each show their own headline + detail empty cards.
- **Interactions:** Long/Short/Flat filter; Risk Budget toggle; refresh; positions table; strategy attribution table; benchmark table; diagnostics panel
- **Limitations:** No graph library is used — the layout is a custom static SVG (account → sleeves → symbols). This is intentional per the plan: "Pick the simplest option that satisfies the current plan." `Rebalance Proposal` and `Run Impact Simulation` buttons are disabled with the note "(no proposal endpoint)".

### Evidence Replay (v1)
- **Production data:** `replay.events`, `incidents`, `explorer`, `documents`, `digest`
- **Empty states:** "Replay unavailable" with `replay.summary`; "No evidence yet" in the timeline
- **Interactions:** Click a marker to load the inspector. Inspector shows event metadata, related IDs, artifact path, and `Open Artifact` (opens HTTP URLs; flags local paths as runbook-only) + `Copy Ref` (clipboard). Evidence timeline merges incidents + replay + explorer + documents into a unified, filterable, paginated table.
- **Limitations:** Play / Pause / Step are visible but disabled with note "(replay is static)" — the backend exposes a single replay snapshot rather than a stream.

## Safety behavior

### Kill Switch
- Right rail button always visible (icon-only when collapsed, full button otherwise) and clickable
- Clicking opens `KillSwitchDialog` (role=alertdialog) which:
  - Lists the four expected effects of the action
  - Shows current runtime status + active symbols
  - Requires the operator to type the exact phrase `KILL TRADINGX`
  - Disables `Confirm` until the phrase matches AND the backend endpoint is supported AND the kill switch is not already active
  - Shows a callout naming the disabled-confirm reason
- `KILL_SWITCH_ENDPOINT_AVAILABLE` is `false` in `ControlCenterApp.tsx`. Flipping that flag (when a server endpoint lands) plus wiring the confirmation handler to the new endpoint is all that is needed to enable the action.

### Flatten All
- Right rail button always visible. Clicking opens `FlattenAllDialog` which:
  - Lists effects and renders the live `portfolio.positions_panel.positions` table
  - Requires the typed phrase `FLATTEN ALL`
  - Disables `Confirm` until the phrase matches AND there are open positions AND the endpoint is supported
- `FLATTEN_ALL_ENDPOINT_AVAILABLE` is `false`; same pattern as Kill Switch when wiring the future endpoint.

### Resume Runtime
- The rail button is disabled if any of these blockers fire (each with explicit copy):
  - `web_write_mode_enabled` is false → "Resume blocked: server write mode is disabled."
  - Web writes not unlocked in this browser session → "Resume blocked: enter the local signing secret to unlock writes."
  - `manual_kill_switch_active` is true → "Resume blocked: manual kill switch is active. Clear the kill-switch evidence before resuming."
  - Runtime is already running/starting → "Resume blocked: runtime host is already running."
  - Any gate is failing → "Resume blocked: <Gate Name> is failing. Open Risk Core to inspect required action."
- Clicking the enabled button opens a generic `ConfirmDialog` showing the symbol universe + cadence; on confirm it calls `postRuntimeHostStart` via the data context's signed-write `runAction` wrapper.

### Strategy approval (Strategy Forge)
- `APPROVAL_AUTHORITY` flag in `StrategyForgeFlavor.tsx` is `false` for v1 (the API does not expose operator-role information). The Approve button is therefore disabled with the canonical copy "Approval blocked: your operator role cannot approve strategy promotion. Request review from an authorized approver."
- Even when authority is granted, approval is also blocked when `live_trading_enabled` is true ("Approval blocked: live trading is disabled. Paper-research approval is permitted but live deployment is not.") or when the candidate is missing adversarial checks / gate statuses ("Promotion blocked: candidate does not have complete adversarial checks or gate statuses. Run gate evaluation before approving.").

### Disabled-state reasons
Every disabled action surfaces *why* it is disabled — either inline as a `commandSub` for rail buttons or as a small `disabledNote` next to the button. No silent disables.

### Confirmation behavior
- `KillSwitchDialog` and `FlattenAllDialog` use a typed phrase + endpoint check.
- `ConfirmDialog` (used for Resume Runtime) shows tone-coloured header (info / watch / risk), focuses the confirm button on open, supports ESC to close, and disables both buttons while `busy=true` so the action cannot be submitted twice.

## Settings behavior

- **Persisted key:** `tradingx.viewFlavor.preferences` in `localStorage`
- **Validation:** `validateStoredPreferences` parses JSON, narrows each field to known enum values, and falls back to `SYSTEM_DEFAULTS` per-field when the value is unrecognised. Invalid JSON / non-object payloads return `null`, which surfaces the system-defaults flow.
- **Fallback:** When no preferences are stored, the canvas displays a non-blocking `Using system view defaults` banner. The hint dismisses on click and clears once the operator clicks `Save Defaults`. If `localStorage` is unavailable (private browsing / quota), saving raises a watch toast and the drawer surfaces a `Local storage is unavailable` banner.
- **Density behavior:** Compact / Balanced / Cinematic update `data-density` on `<html>`. Per-flavor density rules from `Flavor.module.css` adjust grid templates (e.g., Cinematic collapses Market Chart's 2-column grid to 1).
- **Theme behavior:** Blue/Red, Cyan/Amber, Purple/Teal, Green/Gray update `data-theme` on `<html>`. Risk = red and good = green are preserved across all themes; only emphasis (primary/secondary accents) shifts.
- **Manual override behavior:** Any manual flavor change (canvas switcher click, `Cmd/Ctrl+1..6`, left-nav click on a flavor-mapped item) sets `manualOverride = true`. The override pill `Manual view override active` appears with a `Resume auto-switch` button. Auto-switch suggestions and routing-based suggestions are suppressed until override is cleared (manually or on reload).
- **Auto-switch suggestion behavior:** Suggestion-only for v1. `useAutoSwitchSuggestion` evaluates four signals (open incidents, failing gates, scheduler pre-open window, Gate-3 promotion pending) and proposes a target flavor with a one-line reason. Suppressed when (a) the toggle is off, (b) manual override is active, (c) the operator interacted in the last 60 seconds (pointerdown/keydown), or (d) the suggested flavor is already active. The banner is purely advisory; nothing switches without an explicit click.

## Tests run

```text
$ npm run lint
> webapp@0.0.0 lint
> eslint .
(0 errors, 0 warnings)

$ npx tsc -b
(clean)

$ npm test
> webapp@0.0.0 test
> vitest run
 Test Files  6 passed (6)
      Tests  58 passed (58)

$ npm run build
> webapp@0.0.0 build
> tsc -b && vite build
dist/index.html                   0.66 kB │ gzip:   0.39 kB
dist/assets/index-…css           46.18 kB │ gzip:   9.01 kB
dist/assets/index-…js           676.97 kB │ gzip: 197.64 kB
✓ built in 316ms
```

Test coverage highlights:
- `validateStoredPreferences`: invalid JSON, non-object payloads, per-field substitution
- `PreferencesProvider`: load/no-load, manual vs. auto override, save/reset, save-failure-on-storage-throw
- `useFlavorShortcuts`: Cmd+1..6, ignored on 7/0, requires Cmd/Ctrl, suppressed on shift/alt, suppressed in inputs/textareas/dialog descendants
- `isShortcutBlockedTarget`: input/textarea/select/contenteditable/dialog
- `KillSwitchDialog`: typed phrase verification, endpoint-unavailable disablement, kill-already-active disablement, affected runtime summary
- `EvidenceTimeline`: empty state, 20-row table render, 500-row paginated render under 2s, severity/source/search filters, evidence-layer column hide, symbol prop filter
- `deriveRiskTone` / `deriveRuntimeTone` / `describePnl` / `deriveResumeBlocker`: all semantic tones and blocker reasons
- `ControlCenterApp` integration: shell composition, default flavor, manual-override pill on switch, system-defaults hint, drawer with all six flavors and density buttons, kill switch dialog opens with typed-phrase requirement, Resume Runtime disabled when writes locked, default-flavor persistence to localStorage

## Visual QA

| Viewport | Result |
| --- | --- |
| 1728×972 | Shell, all six flavors, View Defaults drawer, Kill Switch dialog, Resume confirmation dialog all render correctly. Right rail expanded by default. Top status strip shows all 8 cards without overlap. |
| 1440×900 | Same as above; rail stays expanded; some panels (Risk Core radial canvas) reach close to viewport height but do not clip. |
| 1024×768 | Right rail auto-collapses to a 56px-wide emergency strip with three icon buttons (Kill / Flatten / Resume) plus the expand chevron. The shell grid switches from `220px / 1fr / 320px` to `220px / 1fr / 56px` via `shellRailCollapsed`. Disabled-action visual treatment (opacity 0.45 + cursor not-allowed) was added in this pass. |

Issues found and fixed during QA:
1. Initial collapsed rail kept the shell grid at 320px wide — added an `onCollapsedChange` callback so the shell grid template updates with the rail's internal collapse decision.
2. Disabled state for collapsed-mode emergency icons had no visual treatment — added `.railCollapsedAction:disabled` rule.
3. Pre-build, the existing webapp had Canela serif headings via `index.css` — replaced with Inter to match the operator-terminal aesthetic.

The error banner visible at the bottom-left of every screenshot is the expected graceful-degradation behavior when no backend is running on `/api`. The shell still renders defaults; once a backend is reachable, the snapshots populate.

## Remaining risks

- **No per-symbol OHLC.** Market Chart's primary visualization is the portfolio equity curve; per-symbol candles, RSI, and Compare are disabled with explicit copy. When the backend exposes a candles endpoint, the timeframe bar can be wired and the recharts ComposedChart already in `MarketChartFlavor` is the natural mount point.
- **Kill Switch and Flatten All have no server endpoints.** The dialogs are fully built and tested but the `Confirm` button is disabled until `KILL_SWITCH_ENDPOINT_AVAILABLE` / `FLATTEN_ALL_ENDPOINT_AVAILABLE` are flipped to `true` and the corresponding `runAction` is wired. The plan's "If no safe production path exists, keep it disabled with clear copy" instruction is followed.
- **Strategy approval** has no write endpoint and `APPROVAL_AUTHORITY` is gated to `false`. Once both arrive the existing buttons can be wired.
- **Auto-switch is suggestion-only.** Plan resolution #2 asks to keep this for the first release; the hook returns a suggestion, the canvas surfaces it, and acceptance requires a click. Promoting to fully automatic switching would only require calling `setActiveFlavor(suggestion.flavor, 'auto')` on a debounce.
- **Portfolio Constellation** does not link strategy sleeves to symbols because the API does not yet expose sleeve-attribution-by-symbol. The graph renders sleeves and symbols as siblings off the account node; the plan's table-first fallback covers the sparse case.
- **Recharts bundle size.** The production JS bundle is 677 KB (gzipped 198 KB) due to recharts. Acceptable for a single-page operator tool; can be code-split per flavor later if needed.
- **Approval authority is hard-coded.** Once an `/api/operator/me` endpoint exposes role + dual-review policy, the `APPROVAL_AUTHORITY` flag in `StrategyForgeFlavor` should be replaced with that runtime value.
- **Web writes unlock UI** is intentionally not exposed in the new shell yet (the previous shell had an inline secret input). The unlock flow is preserved in `DataContext.unlockWrites` / `lockWrites` and the right rail and Resume Runtime button surface "enter the local signing secret to unlock writes" copy. Adding a Settings sub-panel for the secret unlock is a small follow-up.
- **Node 22 + jsdom** ships an experimental empty `localStorage` that shadows jsdom's; the test setup polyfills with a `MapStorage`. If Node ships a complete implementation later, the polyfill may need to be revisited.
