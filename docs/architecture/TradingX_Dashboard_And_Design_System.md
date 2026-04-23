---
id: DESIGN-0021
title: TradingX dashboard and design system
version: 1.0.0
status: active
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# TradingX Dashboard & Design System

## 1. Visual Thesis
**Obsidian Pulse**
TradingX is not a generic SaaS app, nor is it a traditional spreadsheet-heavy fintech terminal. The visual thesis is "Obsidian Pulse" — an immersive, premium, dark-futuristic control environment. It evokes the feeling of a mission-critical aerospace command center or an advanced algorithmic trading floor. It is dark and high-contrast to reduce eye strain during prolonged monitoring, utilizing vibrant, intentional accent glows to guide attention instantly to state changes and fail-closed events. It feels expensive, highly intelligent, and alive.

## 2. Brand / Mood / Experience Goals
- **Immersive & Focused:** The interface recedes; the data and control posture glow. No bright, distracting white backgrounds.
- **Cinematic but Disciplined:** Micro-animations and ambient "heartbeats" make the system feel alive, but they never distract from operational clarity.
- **Authoritative:** Typography and layout are ruthlessly aligned and mathematically precise, inspiring trust in the bot's execution.
- **Legible Density:** High information density without feeling cluttered, achieved through rigorous spatial grouping and semantic depth (using pure black vs. elevated dark grays).

## 3. Design Principles
1. **Color is Semantics, Not Decoration:** Glowing colors are reserved exclusively for state, status, and urgency.
2. **Depth is Context:** Z-index and panel elevation indicate the level of action. Base layers are pure black; floating panels and dialogs are frosted or elevated.
3. **Motion is Meaning:** If something moves, it means state is changing, the bot is evaluating, or a countdown is running. No decorative bouncing.
4. **Explain Everything:** Every chart and metric card has an unobtrusive "Explainability Pattern" affordance.

## 4. Theme and Design Tokens
- **Backgrounds:**
  - `bg-void`: Pure black (`#000000`) for the canvas.
  - `bg-panel-1`: Very dark slate (`#0F1115`) for base widget cards.
  - `bg-panel-2`: Elevated slate (`#1A1D24`) for hover states and interactive strips.
- **Accents (Neon Glows):**
  - `accent-live`: Cyan/Electric Blue (`#00E5FF`) — Indicates active, nominal heartbeat or processing.
  - `accent-pass`: Emerald (`#00FF88`) — Validation passed, safe.
  - `accent-pending`: Amber (`#FFB300`) — Evidence maturing, active evaluation, or countdowns.
  - `accent-fail`: Crimson (`#FF3366`) — Hard fail-closed, policy block, or negative criteria.
- **Borders & Dividers:** Subtle glass-like borders (`rgba(255, 255, 255, 0.05)`) to separate widgets without visual noise. No hard gray lines.

## 5. Typography System
- **Primary Font:** **Inter** (or a similar high-legibility geometric sans-serif). Used for all UI text, labels, and paragraph content.
- **Numerals/Data Font:** **JetBrains Mono** (or similar monospaced font). Used strictly for metrics, financial figures, timestamps, and `command_id` hashes to ensure perfect tabular alignment.
- **Hierarchy:**
  - *Hero Metrics:* 48px, bold, tracked tight.
  - *Panel Headers:* 14px, uppercase, 2px letter-spacing, muted gray.
  - *Body Data:* 13px, standard weight.
  - *Micro Context:* 11px, muted.

## 6. Color System
As defined in Design Tokens, colors are strictly semantic.
- *Data Visualization:* Uses a continuous chromatic scale from deep indigo (low/cold) to vibrant cyan (high/hot) for heatmaps. P&L charts use muted emerald for profit and muted crimson for loss, avoiding blinding primary greens/reds.
- *Typography Color:* Pure white (`#FFFFFF`) for primary data; Slate Gray (`#8A91A6`) for secondary labels.

## 7. Spacing / Layout / Grid Rules
- **Grid:** 12-column fluid grid with 16px gutters.
- **Rhythm:** Based on an 8px scale. Padding inside cards is standard 24px (`p-6`) for breathing room.
- **Density Controls:** The UI avoids clutter by strictly aligning card heights. Key performance indicators (KPIs) live in a top strip, while deep-dive data lives in lower, wider panels.

## 8. Widget and Card System
- **Card Anatomy:**
  - Top Left: Uppercase label (e.g., "CURRENT ACTIVITY").
  - Top Right: Status dot or `i` explainability icon.
  - Center: The data/chart visualization.
  - Bottom: Context strip (e.g., "Updated 2s ago").
- **Glassmorphism:** Used sparingly. Only active modals or dropdowns use background blur (`backdrop-blur-md` + `rgba(26, 29, 36, 0.8)`) to maintain focus.

## 9. Dashboard Composition Rules
Dashboards are composed in visual tiers:
1. **Global Control Strip (Top):** Ubiquitous Live Enablement Panel, connection status, and global filters.
2. **Hero Strip:** 3-4 key metric cards (e.g., Heartbeat, Next Action Countdown, Daily P&L).
3. **Primary Working Area:** The main charts or command tables.
4. **Context Panels (Right/Bottom):** Timeline feeds, event streams, or drill-down details.

## 10. Charting Language
Charts are semantic; variety is intentional.
- **Line Charts:** Used ONLY for continuous time-series data (e.g., Equity Curve). Must have a subtle gradient fill underneath fading to pure black.
- **Bar Charts (Vertical):** Used for discrete time buckets (e.g., P&L per day).
- **Bar Charts (Horizontal):** Used for ranking (e.g., Symbol performance best-to-worst).
- **Gauge Charts:** Used STRICTLY for utilization or boundary metrics (e.g., Risk Limit Usage, CPU Usage). Misleading for unbounded metrics like P&L.
- **Heatmaps:** Used for cross-sectional views (e.g., 2D grid of Symbol vs. Time of Day execution quality).
- **Sparklines:** Used inside tight tables to show 24-hour trend context without axes.
- **Status Ladders / Progress:** Used for workflow steps (e.g., Preopen -> Heartbeat -> Closeout).

## 11. Motion and Animation System
- **Ambient Heartbeat:** The main "Bot Status" indicator pulses with a subtle 2-second sine wave glow (Cyan) ONLY when tied to real, fresh backend telemetry. If the feed stalls, disconnects, or the scheduler misses a beat, the motion must halt and the visual must explicitly degrade to a stale, blocked, or disconnected state. It must never act as a decorative flourish that falsely implies health.
- **Transitions:** Page navigation uses a quick 150ms cross-fade. Chart data updates use fluid spring physics (no linear snapping).
- **State Changes:** When a command is accepted, it flashes briefly before settling. When a filter is applied, the analytical charts cascade into place.
- **Countdown Timer:** The "Next Action" timer ticks smoothly. In the final 10 seconds, the typography weight shifts to draw the operator's eye.

## 12. Explainability Pattern
Every widget, chart, and complex metric has an `i` (info) icon in the top right.
- **Interaction:** Hovering (web) or tapping (mobile) reveals a floating popover.
- **Content:** Uses simple language. Frame bot logic as: *"Current decision summary: The bot is holding positions because X exceeds Y. Next expected action: Re-evaluate at 10:00 AM."* No raw Python traces.

## 13. Filtering and Drilldown Behavior
- **Global Filters:** Located in the top strip (e.g., Time Range, Master Portfolio Slice). Changing these animates the downstream analytical panels. **Critical Rule:** Global filters must NEVER mutate or mask immutable operational-state strips (like Live Enablement, Heartbeat, or Next Action). Those widgets remain authoritative and unfiltered so the operator never confuses a scoped historical slice for the current control posture.
- **Local Filters:** Located inside a specific card (e.g., filtering a bar chart to show only top 5).
- **Drilldown:** Clicking a symbol in a heat map pushes the current view to a "Symbol Drilldown Panel." The global context remains, but the main workspace transitions (slide-in from right) to focus on the symbol. Back-navigation is a clear "← Back to Master Portfolio" breadcrumb.

## 14. Workspace-Specific Dashboard Specs

### Mission Control
- **Goal:** Real-time pulse and immediate operational awareness.
- **Mindset:** "Is the bot running safely?"
- **Top Strip:** Live Enablement Panel (Requested vs. Effective Mode, Explicit Blockers).
- **Core Widgets:** Live Heartbeat module (glowing Cyan), Next Action countdown, Current Activity panel, Recent Event Timeline.
- **Live vs Historical:** 90% Live/Streaming.

### Portfolio & Performance
- **Goal:** Financial and risk oversight.
- **Mindset:** "Are we making money safely?"
- **Core Widgets:** Equity curve (Line + Area gradient), Benchmark comparison visuals, Risk/Concentration gauges, Symbol-level performance horizontal bars.
- **Filters:** Symbol, Sleeves, Time Range.

### Validation & Gates
- **Goal:** Review evidence maturity and promotion readiness.
- **Mindset:** "Is the system rigorously validated to proceed?"
- **Core Widgets:** Validation Tri-State Matrix.
- **Design Rule:** `Pending` states (Amber) feature an explicit "Readiness Blocker" text block. `Fail` states (Crimson) feature fail-closed reasons.
- **Drilldown:** Clicking a criterion opens the Historical Evidence API view (Decision briefs, PBO audit trails).

### Command Center
- **Goal:** Safe, governed action execution and audit.
- **Mindset:** "I need to explicitly intervene or review past commands."
- **Core Widgets:** Command staging panel, Idempotency status tags (`Fresh`, `Replayed`, `Stale`, `Conflicting`, `Blocked`), and a searchable recent-command history list.
- **Visuals:** Highly structured, tabular layout for command history with monospaced `command_id` hashes.

### Investigations / Replay
- **Goal:** Post-incident forensics and drift analysis.
- **Core Widgets:** Timeline scrubbers, side-by-side comparison charts (Replay vs. Production).

### Settings & Governance
- **Goal:** Manage write-security posture and config.
- **Core Widgets:** Kill-switch toggles (requires explicit unlock step), governed command-access rotation flows.

## 15. Mobile Adaptation Rules
- **Layout:** 12-column grid collapses to a single column. Horizontal charts become vertical lists with sparklines.
- **Bottom Navigation:** Replaces the side-nav for the core workspaces.
- **Explainability:** Transitions from hover popovers to bottom-sheet modals.
- **Commands:** Complex workflows are hidden. The interface focuses on emergency actions (Kill Switch) gated by biometric step-ups.

## 16. Accessibility / Legibility / Operational Clarity Rules
- Contrast ratios must meet WCAG AA standards. Pure black backgrounds require high-luminance text.
- Crimson/Green status indicators must always be accompanied by iconography (e.g., an X or a Checkmark) so color-blind users can instantly read state.
- Flashing animations are strictly limited to critical alerts to avoid fatigue or accessibility triggers.

## 17. Relationship to the Frontend Architecture Doc
This document governs the visual and experiential layer of TradingX. All architectural requirements, safety constraints, and API contracts that power these visuals are strictly defined in `TradingX_Frontend_Design.md`.
- E.g., The *Command Center* visuals described here are powered by the `/api/v1/commands` endpoints defined in the architecture spec.
- E.g., The *Validation Matrix* colors (Amber for pending, Crimson for fail) reflect the explicit tri-state data model required by the `/api/v1/validation/readiness` API.
