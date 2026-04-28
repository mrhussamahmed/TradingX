# TradeX View Flavor Control Center Plan

Date: 2026-04-27
Status: Adversarial review incorporated
Scope: Frontend UX and implementation plan for a clean-sheet TradeX operator interface with selectable center-canvas view flavors.

## 1. Goal

Build a usable TradeX control center where the operator keeps one stable supervision shell while switching the middle of the screen between specialized, fully workable views.

The recommendation is **Canvas-first + Settings defaults**:

- The center canvas owns the primary `View Flavor` switcher.
- The switcher is visible during normal work and changes the active operational view immediately.
- Settings stores defaults, density, accent theme, auto-switch behavior, and pinned safety preferences.
- Emergency controls, runtime health, paper/live posture, risk status, alerts, and account state remain visible outside the canvas.

This avoids a settings-heavy UI while still giving the operator persistent customization.

## 2. Product Principles

1. **One shell, many operational lenses**
   The sidebar, top status strip, and right command rail stay stable. Only the center canvas changes.

2. **Controls before decoration**
   Every visible card, chart, timeline, badge, and action must answer an operator question or enable a real workflow.

3. **Safety is persistent**
   Paper-only/live state, runtime health, gate status, kill switch, flatten, resume, and alerts are never hidden by flavor changes.

4. **Dense but legible**
   The app should feel like a professional trading terminal, not a marketing page or generic crypto dashboard.

5. **Future expansion by flavor**
   New workspaces such as options, multi-account, live promotion, model library, or broker reconciliation should become new canvas flavors or sub-flavors, not new shell layouts.

## 3. Information Architecture

### Stable Shell

The shell is always visible:

- Left navigation rail
- Top status strip
- Center canvas with `View Flavor` switcher
- Right operator command rail
- Compact `View Defaults` settings drawer

### Left Navigation

Primary items:

- Mission Control
- Runtime Host
- Paper Only
- Gate 3 Readiness
- Portfolio
- Strategies
- Proposal Studio
- Scheduler
- Evidence
- Alerts
- Reports
- Research
- Settings
- System

Navigation rules:

- `Mission Control` opens the same shell with the last active view flavor.
- `Portfolio`, `Strategies`, `Evidence`, and `Scheduler` can either open their dedicated pages or switch the center canvas to the closest view flavor, depending on route depth.
- `Settings` opens the settings area, but `View Defaults` remains accessible as a compact drawer from the canvas.
- Alerts badge is visible on both left nav and right rail.

### Top Status Strip

Cards shown left to right:

- Market Status: `Market Open`, since time, data-health dot.
- Time: current market time and date.
- Runtime Host: host id, health, heartbeat sparkline.
- Account Mode: `Paper Only` or live state, with live-execution lock detail.
- Account Equity: equity and cash.
- Daily P&L: value and percent.
- Risk Status: normal/watch/risk, gate summary.
- Buying Power: amount and utilization.
- Message/notification/user controls.

Top status logic:

- Cards are read-only except notification and profile controls.
- Risk and runtime cards can deep-link to the relevant panel.
- Any risk state above normal changes its card accent to amber or red.
- In mobile or narrow desktop, cards collapse into a status ticker and priority cards.

### Right Operator Command Rail

Default behavior:

- The rail is **expanded by default** on desktop widths >= 1440px.
- The rail is **collapsible** at all desktop widths.
- The rail auto-collapses into a command drawer below 1280px unless a critical alert, active incident, kill-switch state, or confirmation dialog is present.
- The `Operator Commands` group never disappears. When collapsed, it becomes a vertical emergency strip with icon buttons and severity color.
- `Pin Emergency Controls` keeps the full rail expanded when there is enough width. On narrow screens it pins the emergency strip, not the full rail.

Sections:

- Operator Commands
  - `Kill Switch` red destructive action.
  - `Flatten All` amber high-risk action.
  - `Resume Runtime` blue recovery action.
- Runtime Status
  - status, host, uptime, heartbeat, last restart.
  - `View Runtime Host` button.
- Gate Status
  - gate rows with pass/ready/fail.
  - `View Gate Report` button.
- Active Alerts
  - top alerts, severity, timestamp.
  - `Open Alerts Center` button.

Action safety:

- `Kill Switch` requires typed confirmation phrase: `KILL TRADINGX`.
- `Flatten All` requires confirmation and shows expected affected positions.
- `Resume Runtime` requires runtime health and gate status checks before enabling.
- Disabled actions must explain why.
- Disabled `Resume Runtime` copy must name the blocking condition, for example: `Resume blocked: Gate 2 Risk Limits is failing. Open Risk Core to inspect required action.`

## 4. Center Canvas Framework

### Canvas Header

The center canvas begins with the `View Flavor` switcher.

Controls:

- Large selectable flavor cards:
  - Market Chart
  - Strategy Forge
  - Market Day Ops
  - Risk Core
  - Portfolio Constellation
  - Evidence Replay
- Overflow arrow for future flavors.
- Keyboard shortcuts shown as hints: `Cmd+1 Chart`, `Cmd+2 Forge`, `Cmd+3 Ops`, `Cmd+4 Risk`, `Cmd+5 Portfolio`, `Cmd+6 Evidence`.
- `View Defaults` button/icon to open compact settings drawer.

Behavior:

- Selecting a flavor immediately replaces the center canvas content.
- Selection is saved as the session view.
- If `Apply to Mission Control` is on, selection becomes the default Mission Control view.
- If `Auto-switch by Workflow` is on, workflow signals may suggest a flavor change. First release uses suggestion-only behavior unless the operator explicitly enables automatic switching.
- Auto-switch suggestions never appear while the operator is actively typing, confirming a command, or has interacted with the current flavor in the last 60 seconds.
- Manual selection overrides auto-switch until the market session changes, the operator clicks `Resume auto-switch`, or the browser session is reloaded.
- Every switch shows a 4-second transition badge, for example: `Switched to Risk Core - Gate 2 degraded`.
- Active flavor card uses a filled blue/black background, bright border, left-edge accent bar, and selected checkmark. It must be distinguishable without reading the label.
- First release shows all six flavors in the switcher. Full-depth flavors are enabled normally. Functional-v1 flavors are enabled and clearly labeled `v1`; no primary flavor appears as disabled unless the backend capability is completely absent.

### Canvas Density

Density affects every flavor:

- `Compact`: fewer cards, smaller charts, denser tables, right rail prioritized.
- `Balanced`: default. Full chart and secondary cards.
- `Cinematic`: large primary visualization, fewer secondary widgets, stronger spacing.

Density must not hide safety controls.

Per-flavor density matrix:

| Flavor | Compact | Balanced | Cinematic |
| --- | --- | --- | --- |
| Market Chart | Chart, risk strip, compact evidence table | Chart, indicators, portfolio/risk cards, evidence table | Large chart and indicator stack; portfolio/risk cards collapse to drawer; evidence timeline becomes overlay |
| Strategy Forge | Candidate table and inspector | Candidate table, weights, backtest, inspector, evidence | Backtest/compare focus; weights and evidence collapse into tabs |
| Market Day Ops | Timeline lanes plus right summary | Timeline, positions, exposure, scheduler, digest | Full-width timeline; positions and digest collapse below |
| Risk Core | Gate list plus detail | Radial core, gate detail, incidents, evidence | Large radial core; incident stack becomes overlay drawer |
| Portfolio Constellation | Allocation table fallback | Graph, attribution, risk budget, benchmark | Large graph; attribution/risk panels become drawers |
| Evidence Replay | Timeline and table | Timeline tracks, table, event inspector | Large replay timeline; table/inspector become split drawer |

### Evidence Layer

When enabled:

- Charts and timelines show evidence markers.
- Events link to artifacts, reports, logs, or replay records.
- Hover/click exposes source, timestamp, category, and related action.

When disabled:

- Views remain operational but show less provenance detail.

## 5. View Flavor Details

### 5.1 Market Chart

Purpose:
Live market and portfolio supervision for the active symbol.

Primary questions:

- What is the selected symbol doing now?
- Is the bot allowed to trade?
- What is exposure and P&L?
- What risk gates apply?
- What evidence/events are happening around this symbol?

Main content:

- Symbol header: symbol, company label, price, change, OHLC, volume.
- Timeframe buttons: `1m`, `5m`, `15m`, `1H`, `4H`, `1D`, `1W`, `1M`.
- Chart toolbar:
  - `Indicators`
  - `Compare`
  - chart type buttons
  - fullscreen
  - reset zoom
- Main price chart with volume.
- RSI or selected indicator strip.
- Portfolio Summary card.
- Performance Today card.
- Risk Gates Live card.
- Exposure card.
- Evidence Timeline table.

Buttons and menus:

- `Indicators`: opens menu for RSI, moving averages, volatility, drawdown, spread, volume.
- `Compare`: add SPY/QQQ/IWM/benchmark or active strategy.
- `All Types`: evidence event filter.
- `All Sources`: evidence source filter.
- Search evidence.
- Auto-scroll toggle.
- Pause timeline.
- `More filters` overflow for low-priority filters on narrower screens.

Usable workflow:

1. Operator opens Mission Control.
2. Market Chart loads active symbol, or first active symbol if none selected.
3. Operator checks price, risk gates, exposure, and evidence.
4. Operator filters timeline to risk/execution events if investigating.
5. Operator opens `Indicators` or `Compare` for deeper context.
6. If risk is unacceptable, operator uses right rail actions.

Evidence timeline filter rule:

- At 1440px and below, show only `Type`, search, auto-scroll, and pause in the main toolbar.
- Move source, severity, date range, and tag filters into `More filters`.
- Timeline rows use pagination or virtualization once row count exceeds 100.

Data dependencies:

- Runtime heartbeat
- Command center watchlist
- Portfolio account summary
- Exposure breakdown
- Gate statuses
- Replay/evidence records
- Alerts/incidents

Empty states:

- If no market data: show chart placeholder with data-source status and recovery action.
- If no active symbol: show watchlist picker.
- If no evidence: show clear message, not a blank table.

### 5.2 Strategy Forge

Purpose:
Research, compare, approve, reject, and simulate strategies.

Primary questions:

- Which strategies are active, candidates, watch, research, or rejected?
- What changed between backtest and paper performance?
- What model weights and factors drive the strategy?
- Is this strategy ready for promotion?

Main content:

- Candidate Strategies table.
- Model Weights panel.
- Opportunity Selection panel.
- Backtest vs Paper chart.
- Portfolio Impact card.
- Evidence and Artifacts carousel/table.
- Replay Timeline.
- Right-side Evidence Inspector or proposal panel when selected.

Buttons and menus:

- `New Strategy`
- `All Sleeves` filter
- view toggle: grid/table/compare
- `Compare`
- strategy row overflow menu:
  - View details
  - Open evidence
  - Simulate
  - Draft proposal
  - Archive candidate
- `Approve`
- `Reject`
- `Simulate`
- `Open Proposal Studio`

Usable workflow:

1. Operator switches to Strategy Forge.
2. Selects a candidate strategy row.
3. The inspector shows recommendation, gate results, artifacts, and proposal status.
4. Operator compares backtest and paper results.
5. Operator simulates portfolio impact.
6. Operator drafts, approves, rejects, or requests changes.

Approval authority:

- `Approve` is disabled unless the current operator has strategy-approval authority.
- Promotion approval requires all mandatory gates to pass or a recorded exception with explicit evidence refs.
- Paper-only mode does not block strategy research approval, but it blocks any live deployment action.
- High-impact promotions require a second reviewer when policy says dual approval is required.
- Unauthorized approval copy: `Approval blocked: your operator role cannot approve strategy promotion. Request review from an authorized approver.`

Data dependencies:

- Research candidate summaries
- Gate summaries
- Runtime model snapshot
- Opportunity selection
- Documents/explorer records
- Gate 3 package/readiness

Empty states:

- If no candidates: show active strategy and `New Strategy` / `Import Evidence` actions.
- If no paper history: show backtest-only mode with warning.

### 5.3 Market Day Ops

Purpose:
Run the trading day as an operational timeline.

Primary questions:

- Where are we in the trading day?
- Did pre-open, heartbeat, trade decisions, incidents, closeout, and evidence refresh complete?
- What needs operator action now?

Main content:

- Market Day timeline with lanes:
  - Pre-open
  - Runtime
  - Decisions
  - Incidents
  - Evidence
  - Closeout
- Current-time vertical marker.
- Active Positions table.
- Exposure ring.
- Risk Metrics card.
- Market Overview chart.
- Command Center input bar for supported operator commands.

Buttons and menus:

- `Run Pre-open Checks`
- `Start Runtime`
- `Pause Runtime`
- `Resume Runtime`
- `Refresh Evidence Now`
- `Generate Manual Snapshot`
- `Sync Market Data`
- `Recalculate Risk`
- `Export Daily Digest`
- timeline playback controls:
  - play/pause
  - step back/forward
  - speed
  - jump to now

Usable workflow:

1. Operator opens Market Day Ops before market open.
2. Runs pre-open checks.
3. Timeline records checks and readiness.
4. Runtime heartbeats and decisions populate lanes.
5. Incidents are highlighted in red and linked to evidence.
6. At close, operator runs closeout and evidence refresh.
7. Daily digest is exported or reviewed.

Data dependencies:

- Scheduler state
- Runtime host heartbeat/state
- Daily session digest
- Incidents
- Replay events
- Portfolio positions and exposure
- Evidence documents

Empty states:

- Pre-market: show upcoming schedule and checklist.
- Post-market: show digest and replay.
- No scheduler: show setup instructions and manual run actions.

### 5.4 Risk Core

Purpose:
Visual risk authority and gate supervision.

Primary questions:

- Are all trading permissions valid?
- Which risk gate is blocking or degraded?
- What is the relationship between runtime, data, strategy, execution, and paper/live safety?

Main content:

- Central radial/hexagonal risk core.
- Gate nodes:
  - Market Data
  - Risk Limits
  - Strategy Health
  - Paper Environment
  - Live Disabled
  - Runtime Lock
  - Drift
  - Slippage Replay
  - Kill Switch
- Gate detail side panel.
- Incident stack.
- Approval/promotion readiness.
- Evidence links per gate.

Buttons and menus:

- `View Gate Report`
- `Run Gate Check`
- `Open Evidence`
- `Acknowledge Incident`
- `Create Blocker`
- `Refresh Risk`
- gate node click
- gate filter: all/pass/watch/fail

Usable workflow:

1. Operator switches to Risk Core.
2. Scans radial status for pass/watch/fail nodes.
3. Clicks a degraded node.
4. Reads required operator action and evidence refs.
5. Runs or schedules checks.
6. Escalates using incidents/blockers if necessary.

Data dependencies:

- Gate statuses
- Gate 3 readiness
- Incidents
- Runtime state
- Config summary/live disable report
- Validation and evidence records

Empty states:

- If gate data missing: show pending state and required artifact path/action.
- If no incidents: show clean state, not empty whitespace.

### 5.5 Portfolio Constellation

Purpose:
Portfolio-first supervision across symbols, sleeves, risk budgets, and future multi-strategy expansion.

Primary questions:

- Where is capital allocated?
- Which strategy sleeve owns each exposure?
- What risk budget/drawdown is concentrated?
- What rebalance or proposal should be considered?

Main content:

- Central network/constellation graph:
  - account node
  - strategy sleeve nodes
  - symbol nodes
  - risk/evidence nodes
- Allocation path thickness indicates exposure.
- Node color indicates health/risk.
- Bottom attribution table.
- Equity/benchmark chart.
- Risk budget card.
- Rebalance proposal card.

Buttons and menus:

- `Rebalance Proposal`
- `Run Impact Simulation`
- `View Account`
- `Expand Sleeve`
- `Collapse Sleeve`
- `Filter: Long/Short/Flat`
- `Show Risk Budget`
- `Show Evidence Links`

Usable workflow:

1. Operator switches to Portfolio Constellation.
2. Scans allocations and risk concentrations.
3. Clicks sleeve or symbol node.
4. Inspector shows exposure, P&L, drawdown, evidence, and owner strategy.
5. Operator runs impact simulation or opens proposal.

Data dependencies:

- Portfolio workspace snapshot
- Positions panel
- Strategy panel
- Benchmark panel
- Diagnostics
- Runtime activation/model

Empty states:

- If flat: show empty constellation with account node, available cash, and watchlist.
- If no sleeve attribution: group by symbol and mark sleeve as unknown.

### 5.6 Evidence Replay

Purpose:
Artifact-backed investigation and replay of decisions, trades, alerts, and gate events.

Primary questions:

- What happened?
- In what order?
- Which artifact proves it?
- Which incident, trade, gate, or proposal is related?

Main content:

- Replay timeline with tracks:
  - Trades
  - Signals
  - Risk
  - Events
  - Drawdown
  - Documents
- Evidence table.
- Selected event inspector.
- Artifact preview card.
- Related IDs/links.
- Search and filters.

Buttons and menus:

- `Play`
- `Pause`
- `Step`
- `1x/2x/4x speed`
- `Jump to Now`
- `Export Replay`
- `Open Artifact`
- `Copy Evidence Ref`
- filters:
  - symbol
  - category
  - severity
  - source
  - date range

Usable workflow:

1. Operator switches to Evidence Replay.
2. Selects symbol/date/category.
3. Plays or scrubs timeline.
4. Clicks an event.
5. Inspector shows event details, artifact path, related incident/proposal/trade.
6. Operator exports replay or opens source evidence.

Data dependencies:

- Replay session
- Explorer records
- Document records
- Incidents
- Daily digest
- Gate reports

Empty states:

- If replay unavailable: show search prompt and latest available evidence.
- If artifact missing: show broken provenance state and incident creation option.

## 6. View Defaults Settings Drawer

The drawer is secondary. It should not cover the primary canvas unless the screen is narrow.

Fields:

- `Default startup view`
  - Market Chart
  - Strategy Forge
  - Market Day Ops
  - Risk Core
  - Portfolio Constellation
  - Evidence Replay
- `Canvas Density`
  - Compact
  - Balanced
  - Cinematic
- `Accent Theme`
  - Blue / Red
  - Cyan / Amber
  - Purple / Teal
  - Green / Gray
- Toggles:
  - Auto-switch by Workflow
  - Pin Emergency Controls
  - Show Evidence Layer
  - Apply to Mission Control
- Buttons:
  - Save Defaults
  - Reset to System Defaults

Settings logic:

- Changing active flavor in the canvas updates session state immediately.
- `Save Defaults` persists default settings to local storage first.
- Later backend persistence can save per-operator preferences.
- `Reset to System Defaults` restores:
  - default flavor: Market Chart
  - density: Balanced
  - accent theme: Blue / Red
  - auto-switch: on
  - pinned controls: on
  - evidence layer: on
  - apply to Mission Control: on

## 7. UI State Model

Recommended frontend state:

```ts
type ViewFlavor =
  | 'market-chart'
  | 'strategy-forge'
  | 'market-day-ops'
  | 'risk-core'
  | 'portfolio-constellation'
  | 'evidence-replay'

type CanvasDensity = 'compact' | 'balanced' | 'cinematic'

type AccentTheme = 'blue-red' | 'cyan-amber' | 'purple-teal' | 'green-gray'

type ViewFlavorPreferences = {
  activeFlavor: ViewFlavor
  defaultFlavor: ViewFlavor
  density: CanvasDensity
  accentTheme: AccentTheme
  autoSwitchByWorkflow: boolean
  pinEmergencyControls: boolean
  showEvidenceLayer: boolean
  applyToMissionControl: boolean
}
```

Persistence:

- Store preferences under `tradingx.viewFlavor.preferences`.
- Validate persisted values on load.
- Fall back to system defaults on invalid or missing data.
- On first load with no preferences, silently apply system defaults and show a dismissible `Using system view defaults` hint in the View Defaults drawer.
- Do not block the operator with a setup prompt before showing the control center.

Auto-switch rules:

- Pre-open/checklist workflow suggests `Market Day Ops`.
- Risk incident or gate failure suggests `Risk Core`.
- Strategy proposal/research route suggests `Strategy Forge`.
- Evidence/replay route suggests `Evidence Replay`.
- Portfolio route suggests `Portfolio Constellation`.
- Active symbol/normal supervision defaults to `Market Chart`.

Manual override:

- Manual view selection wins over auto-switch until the current market session changes, browser session reloads, or the operator clicks `Resume auto-switch`.
- Show subtle text: `Manual view override active` with a `Resume auto-switch` action.
- Provide `Resume auto-switch` action when auto-switch is enabled.

## 8. Design System

### Visual Tone

Keywords:

- dark
- futuristic
- professional
- operational
- high contrast
- blue/red
- dense
- credible

Avoid:

- marketing hero layouts
- decorative blobs/orbs
- beige/soft dashboard palettes
- playful crypto exchange visuals
- oversized empty cards
- low-contrast text
- rounded pill overload

### Color Tokens

Base:

- `--bg-root: #02060b`
- `--bg-shell: #050b12`
- `--bg-panel: #07111d`
- `--bg-panel-raised: #0a1726`
- `--border-muted: #183047`
- `--border-strong: #24527a`

Text:

- `--text-primary: #f4f8ff`
- `--text-secondary: #b6c4d6`
- `--text-muted: #72849a`

Accent:

- `--blue: #147cff`
- `--blue-bright: #2ea1ff`
- `--cyan: #19d3ff`
- `--red: #ff3347`
- `--crimson: #c91f35`
- `--amber: #ffae2f`
- `--green: #28e078`

State colors:

- Good: green
- Info: blue/cyan
- Watch: amber
- Risk: red/crimson
- Disabled: muted gray

Accent theme token sets:

| Theme | Primary | Secondary | Risk | Warning | Good |
| --- | --- | --- | --- | --- | --- |
| Blue / Red | `#147cff` | `#19d3ff` | `#ff3347` | `#ffae2f` | `#28e078` |
| Cyan / Amber | `#19d3ff` | `#2e7dff` | `#ff4d5e` | `#ffb020` | `#2de086` |
| Purple / Teal | `#7c4dff` | `#18d6c2` | `#ff3b5f` | `#ffc247` | `#35db7a` |
| Green / Gray | `#28e078` | `#8ea3b8` | `#ff3347` | `#ffb238` | `#28e078` |

Theme rules:

- Risk/destructive actions always remain red across all themes.
- Good/pass states always remain green enough to be recognizable.
- Accent theme changes emphasis, charts, selected flavor state, and non-critical highlights.
- Accent theme must not change semantic safety colors into ambiguous colors.

### Typography

Recommended:

- UI/body: `Inter`, `IBM Plex Sans`, or existing system sans.
- Numeric/data: `IBM Plex Mono` or `Roboto Mono`.
- Avoid serif headings for this clean-sheet control-center direction.

Rules:

- No negative letter spacing.
- Use tabular numerals for money, prices, P&L, time, and ratios.
- Uppercase labels for small metadata only.
- Keep headings compact inside panels.

### Spacing and Shape

- Shell padding: 8-16px depending on viewport.
- Panel radius: 6-8px.
- Button radius: 6px.
- Dense cards: 10-14px padding.
- Major panels: 14-18px padding.
- Avoid cards inside decorative cards.
- Use grid tracks and fixed control heights to avoid layout jump.

### Components

Core components:

- AppShell
- LeftNav
- TopStatusStrip
- OperatorCommandRail
- ViewFlavorSwitcher
- ViewDefaultsDrawer
- CanvasRenderer
- StatusCard
- RiskBadge
- CommandButton
- EvidenceTimeline
- DataTable
- ChartPanel
- InspectorDrawer
- ConfirmationDialog
- EmptyState

Buttons:

- Primary: blue action.
- Destructive: red, requires confirmation.
- Warning: amber.
- Ghost/icon: transparent with border.
- Disabled: clear disabled reason.

Icons:

- Use lucide icons where available.
- Prefer icons for navigation and toolbar controls.
- Text+icon for dangerous or high-stakes commands.

## 9. UX Workflows

### Workflow A: Normal Supervision

1. Operator opens app.
2. Top strip shows market, runtime, paper-only, P&L, risk.
3. Center opens saved default flavor.
4. Operator switches views from the canvas flavor bar as needed.
5. Right rail remains available for safety actions.

### Workflow B: Investigate Alert

1. Alert appears in right rail.
2. Operator clicks alert.
3. If auto-switch is enabled, canvas suggests Risk Core or Evidence Replay.
4. Operator reviews gate/event details.
5. Operator opens evidence or acknowledges incident.
6. If needed, operator uses kill/flatten/pause controls.

### Workflow C: Run Trading Day

1. Operator switches to Market Day Ops.
2. Runs pre-open checks.
3. Starts runtime or confirms scheduler.
4. Monitors timeline lanes.
5. Handles incidents as they appear.
6. Runs closeout and evidence refresh.
7. Exports daily digest.

### Workflow D: Promote Strategy

1. Operator switches to Strategy Forge.
2. Selects candidate strategy.
3. Reviews backtest vs paper, model weights, opportunity selection, and evidence.
4. Opens proposal.
5. Runs simulation.
6. Approves, rejects, or requests changes.

### Workflow E: Portfolio Risk Review

1. Operator switches to Portfolio Constellation.
2. Clicks a sleeve or symbol.
3. Reviews exposure, drawdown, risk budget, and evidence links.
4. Opens rebalance proposal or impact simulation.

### Workflow F: Replay Incident

1. Operator switches to Evidence Replay.
2. Filters by symbol/severity/date.
3. Plays timeline.
4. Opens artifacts and related incident IDs.
5. Exports replay if needed.

## 10. Implementation Phases

### Phase 1: Shell and Preference Model

Deliverables:

- Clean-sheet AppShell layout.
- Stable left nav, top status strip, right command rail.
- View flavor state model.
- Local storage persistence.
- View Defaults drawer.
- Placeholder canvas renderer.
- Collapsible right rail with pinned emergency strip.
- `Cmd+1` through `Cmd+6` shortcut handling.
- First-release switcher behavior with all six flavors selectable.

Acceptance criteria:

- User can switch flavors.
- User can save defaults.
- Reload opens saved default.
- Emergency controls remain visible.
- Active flavor has a visibly distinct selected treatment.
- Missing preferences apply system defaults with a non-blocking hint.
- Manual view switching suppresses auto-switch suggestions until override expires.

### Phase 2: Market Chart and Shared Canvas Components

Deliverables:

- Market Chart flavor.
- Shared chart panel, metric card, evidence timeline, risk gate card.
- Functional filters and toolbar placeholders wired to UI state.
- Evidence timeline pagination or virtualization above 100 rows.
- `More filters` overflow for lower-priority filters.

Acceptance criteria:

- Market Chart is usable with current backend data.
- Empty states are clear.
- Evidence layer can be toggled.
- Timeline remains responsive with 500+ rows in test data.

### Phase 3: Strategy Forge and Evidence Replay

Deliverables:

- Strategy Forge flavor.
- Evidence Replay flavor.
- Inspector patterns for strategy/evidence selection.
- Approval authority and blocked-action copy for strategy promotion actions.

Acceptance criteria:

- Strategy rows can be selected.
- Evidence/replay events can be filtered and inspected.
- Proposal buttons route or trigger safe placeholders until backend writes exist.
- Unauthorized or evidence-incomplete approvals are disabled with explicit reason text.

### Phase 4: Market Day Ops and Risk Core

Deliverables:

- Market Day timeline.
- Risk Core radial/gate view.
- Incident and gate detail interactions.

Acceptance criteria:

- Timeline lanes render from available events.
- Gate nodes show pass/watch/risk.
- Clicking a node/event opens details.

### Phase 5: Portfolio Constellation and Polish

Deliverables:

- Graph rendering spike comparing D3 force simulation, React Flow, and custom SVG/static radial layout.
- Portfolio constellation graph.
- Sleeve/symbol inspector.
- Density/theme refinements.
- Responsive behavior.

Acceptance criteria:

- Portfolio graph degrades to table/list when graph data is sparse.
- Density modes materially affect layout.
- No text overlap at common desktop sizes.
- Portfolio Constellation graph implementation is selected only after a spike comparing D3 force simulation, React Flow, and a custom SVG/static radial layout.

### Phase 6: Safety, Tests, and Review

Deliverables:

- Confirmation dialogs for destructive actions.
- Unit/component tests for preference persistence and view switching.
- Accessibility pass.
- Playwright visual smoke checks.
- Adversarial review report.

Acceptance criteria:

- All flavors are selectable and render without runtime errors.
- Safety actions cannot fire accidentally.
- Build, tests, and lint pass.

## 11. Testing Plan

Unit/component tests:

- Renders default flavor.
- Switches active flavor from canvas switcher.
- Persists default settings.
- Restores preferences after reload.
- Invalid local storage falls back safely.
- Density/theme controls update CSS classes.
- Emergency rail remains visible when pinned.
- Auto-switch suggestion does not override manual selection.

Interaction tests:

- `Cmd+1` through `Cmd+6` switch flavors only when focus is not inside a text input, select, textarea, slider, or confirmation dialog.
- Settings drawer opens/closes.
- Filters update visible evidence/timeline rows.
- Destructive actions require confirmation.
- Evidence timelines remain performant above 500 rows.

Visual tests:

- Desktop 1728x972.
- Laptop 1440x900.
- Narrow desktop/tablet 1024x768.
- Verify no overlapping text, clipped buttons, or blank canvases.

Accessibility checks:

- Keyboard navigable switcher.
- Clear focus rings.
- ARIA labels for icon buttons.
- Destructive actions announced clearly.
- Color is not the only status signal.

## 12. Risks and Mitigations

Risk: Too many views create cognitive overload.
Mitigation: Keep switcher to six primary flavors, use clear labels/subtitles, and hide future views behind overflow.

Risk: Settings drawer still dominates the UI.
Mitigation: Keep it compact, secondary, and closable. Main switching stays on the canvas.

Risk: View flavors become static mockups.
Mitigation: Each flavor must have at least one usable primary workflow before it is considered done.

Risk: Backend data is incomplete for some views.
Mitigation: Build honest empty states and use existing evidence/runtime/portfolio data first.

Risk: Emergency controls compete with normal workflow.
Mitigation: Keep them visually distinct, right-rail pinned, and confirmation-gated.

Risk: Futuristic styling hurts readability.
Mitigation: Use restrained glow, high contrast, compact panels, and readable text sizes.

Risk: Portfolio Constellation becomes the highest-complexity view.
Mitigation: Run a graph-library spike before Phase 5 and keep a table/list fallback as a first-class implementation, not an afterthought.

Risk: Auto-switch disorients the operator.
Mitigation: Ship suggestion-only first, suppress suggestions during active work, show a switch reason badge, and provide explicit `Resume auto-switch`.

Risk: Strategy approvals bypass authority.
Mitigation: Gate approval buttons by operator role, gate status, evidence refs, and dual-review policy before any write action is exposed.

## 13. Adversarial Review Checklist

Use this section to challenge the plan before implementation.

### Product Challenge

- Does each view flavor solve a distinct operator problem?
- Are any flavors redundant enough to merge?
- Is six flavors too many for first release?
- Does the UI still work if the operator only uses Market Chart and Market Day Ops?
- Are future features added by flavor, menu, or route?

### Safety Challenge

- Can a user accidentally kill, flatten, or resume runtime?
- Are destructive controls too close to normal controls?
- Does any flavor hide paper/live state?
- Does any workflow allow promotion without evidence?
- Does auto-switch ever move the operator away from a critical view at the wrong time?

### UX Challenge

- Is the flavor switcher prominent enough?
- Is the settings drawer secondary enough?
- Can the operator understand what changed after switching views?
- Are empty states actionable?
- Does density change improve usability or just compress visuals?

### Data Challenge

- Which views can be fully powered by current APIs?
- Which views need backend additions?
- What data is stale versus live?
- Are evidence links trustworthy and inspectable?
- Are missing artifacts shown honestly?

### Engineering Challenge

- Can each flavor be implemented as an isolated component?
- Are shared shell components reusable without becoming too generic?
- Is preference persistence validated?
- Can visual density and accent theme be implemented without CSS chaos?
- Do tests cover the core behavior rather than screenshots only?

### Design Challenge

- Is the design futuristic without becoming decorative?
- Are red/blue accents meaningful and not overused?
- Are cards and tables readable under real data volume?
- Does the shell scale to smaller screens?
- Does the central canvas remain the visual focus?

## 14. Resolved Decisions and Remaining Questions

Resolved before Phase 1:

1. `Mission Control` opens the saved default flavor on first app load, then preserves the last manually selected session flavor until reload or market-session change.
2. Auto-switch is suggestion-only for the first release. Fully automatic switching can be added later behind an explicit preference.
3. Keyboard shortcuts use `Cmd+1` through `Cmd+6`, never bare number keys.
4. The right rail is collapsible, but the emergency command strip remains visible.
5. All six primary flavors appear in the switcher for the first release. Market Chart, Market Day Ops, and Risk Core receive full depth first; the other three ship as functional v1 views, not static mockups.
6. Kill Switch confirmation phrase is `KILL TRADINGX`.
7. Strategy promotion approval requires operator authority, gate/evidence validation, and dual-review support where policy requires it.

Remaining non-blocking questions:

1. Should `Strategy Forge` and `Proposal Studio` eventually merge into one route, or stay as separate route plus flavor?
2. Should per-operator preferences be added to the backend after localStorage proves useful?
3. Which graph library should power Portfolio Constellation after the Phase 5 spike?
4. Should automatic view switching graduate from suggestion-only after operators trust the behavior?

## 15. Recommended First Release

Build all six flavors as selectable, but stage their depth:

- Full: Market Chart, Market Day Ops, Risk Core.
- Functional v1: Strategy Forge, Evidence Replay.
- Functional v1 with graceful sparse-data state: Portfolio Constellation.

This preserves the product vision while keeping the first build realistic.
