---
id: RESEARCH-0003
title: TradingX operator platform research
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# Research: TradingX operator platform

## Key choices

### 1. Refresh model

Use short-interval polling from the local SPA instead of websockets.
The operator platform is local-only, single-user, and artifact-driven.
Polling keeps the system simpler and easier to test while still
providing near-real-time supervision.

### 2. Timeline model

Use one normalized operator event model across service cycles, trade
intents, orders, risk events, reconciliations, alerts, validation
reports, and operator actions. This enables replay, incident
investigation, explainability, and audit trails without inventing
feature-specific storage formats.

### 3. Incident handling

Persist acknowledgment state and daily digests under
`artifacts/operator_platform/` so operator-facing state remains local,
auditable, and recoverable after restarts.

### 4. Visual layer

Keep the frontend dependency surface light and render charts with native
SVG/CSS instead of adding a heavyweight charting library. The app is
local, the datasets are modest, and custom SVG lets the UI stay dense
and intentional.

### 5. Session orchestration

Model day-operations as bounded commands rather than a second scheduler.
The backend can generate pre-open checks, intraday heartbeats, and
end-of-day digests without replacing the existing paper service.
