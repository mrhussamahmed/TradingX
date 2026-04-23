---
id: DESIGN-0020
title: TradingX frontend UX and information architecture
version: 1.0.0
status: active
created: 2026-04-23
last_amended: 2026-04-23
supersedes: null
superseded_by: null
author_session: codex-gpt-5-2026-04-23
---

# TradingX Frontend UX & Information Architecture

## 1. Executive Summary
TradingX is evolving from a local trading appliance with a paper-only mindset into a headless, cloud-ready bot governed by a rigorous control plane. The frontend must decouple from legacy local assumptions (like SQLite artifacts and process management) and focus on presenting a stable abstraction layer. The new UI prioritizes safety, observability, evidence-based decision-making, and governed operational control. It treats live-enablement as a strict, fail-closed posture rather than a simple toggle, and enforces a secure, idempotent command model for all operator interactions.

For visual aesthetics, dashboard layout, and motion design, see the companion document: `TradingX_Dashboard_And_Design_System.md`.

## 2. Product Modes / Personas
The system caters to distinct modes of interaction, reflecting differing needs for safety and insight:
- **Observer / Researcher (Read-Only):** Focused on analyzing PBO reports, reviewing evidence, investigating incidents, and understanding strategy attribution. Needs deep drill-down capabilities without any risk of accidental mutation.
- **Operator (Bounded Controls):** The primary persona for daily interaction. Can acknowledge incidents, start/stop bounded paper loops, review readiness packages, and monitor the live-enablement posture. Actions are strictly gated by write-security policies and governed command-access rotation flows.
- **Administrator / Governor:** Configures system-level settings, unlocks short-lived command sessions or invokes governed rotation flows, edits kill switches, and approves gate promotions. No raw client-side secret configuration screens exist; this persona manages the write-security posture through the control plane.

## 3. Recommended Information Architecture
The top-level navigation moves away from generic "dashboards" and aligns with operational jobs-to-be-done:
- **Mission Control (Ops Pulse):** Real-time system health, live-enablement posture, active incidents, and runtime state.
- **Portfolio & Risk:** Exposures, position tracking, execution quality, and fail-closed events.
- **Validation & Gates (Evidence Browser):** Gate 1-3 readiness, CPCV cohort maturity, historical validation evidence, and PBO reports.
- **Command & Control (Action Center):** Dedicated workspace for safe actions, write authorization status, command history lists, and searchable command audit logs.
- **Investigations / Replay:** Deep dives into past sessions, drift analysis, and specific incident forensics.
- **Settings & Governance:** Config proposals, kill switch management, write-security posture, and governed command-access rotation flows.

## 4. Core Views and Their Purpose
- **The Live Enablement Panel (Ubiquitous):** A persistent header or side panel visible across operational views. It explicitly separates *requested mode* from *effective mode* and lists specific fail-closed blockers.
- **Validation Matrix View:** Replaces simple lists with a tri-state matrix showing candidate-level and criterion-level resources. Includes a clear "Blockers" drill-down for pending items.
- **Command Center Interface:** Exposes the command audit trail. Shows recent-command lists and per-command event timelines to track workflows across reconnects and multiple clients.
- **Incident Feed / Timeline:** A chronological stream of events, separating routine heartbeats from fail-closed live-order events and market-data degradation warnings.

## 5. Command and Control UX Model
- **Explicit Operator Intent:** Commands never "just run." They are staged, signed, and transmitted.
- **Write Authorization (Session Model):** The UI requires an unlock step to open a short-lived command session, powered explicitly by a backend API (see `/api/v1/command-sessions`). The UI does not own or store long-lived signing secrets directly.
- **Idempotency & Replay Handling:** The UI distinguishes between *retrying a submission* (reusing the persisted command envelope's idempotency key to recover a dropped response) and *creating a new intent* (rotating to a fresh idempotency key).
- **Command Result States:** The UI strictly surfaces the full lifecycle of asynchronous operations:
  - **Accepted/Queued:** New action received by the control plane but not yet started.
  - **In-Progress:** Action is actively executing.
  - **Completed:** Action finished successfully.
  - **Failed/Canceled:** Action started but terminated abnormally or was explicitly aborted. The UI must expose explicit error details/reasons.
  - **Replayed:** Prior result replayed due to idempotency match.
  - **Stale:** Request rejected due to timestamp expiration.
  - **Conflicting:** Request rejected due to idempotency key collision with a different fingerprint.
  - **Blocked:** Request rejected by safety policy or fail-closed rules.

## 6. Data and State Presentation Rules
- **Validation Tri-State Behavior:**
  - **Pending (Yellow/Hourglass):** The criterion is active but evidence (like CPCV) is not mature. Accompanied by a explicit "Readiness Blocker" explanation.
  - **Fail (Red/X):** The criterion resolved negatively.
  - **Pass (Green/Check):** The criterion resolved positively.
  - **Unavailable (Gray/Dashed):** Data genuinely does not exist (e.g., legacy records, requiring effective status derivation for legacy `null` statuses).
- **Control Posture Modeling:** Live enablement is modeled as a rigorous, governed posture. Blockers are shown as explicit fail-closed reasons rather than generic warnings.
- **Bot Cognition:** Never expose raw chain-of-thought. Instead frame as: "current decision summary", "current evaluation state", "current activity", "next planned action", and "why the next step is expected".

## 7. Realtime and Notification Model
- **Streaming (WebSockets / SSE):** Crucial for runtime status changes, heartbeats, critical fail-closed events, and live-disable reason changes.
- **Polling / Refresh-Driven:** Gate status transitions, portfolio snapshots, and config summaries.
- **Local Cache:** Historical performance metrics, older PBO reports, and replay session data.
- **Offline/Disconnect State:** The UI must immediately indicate a "Stale / Disconnected" state if SSE drops.

## 8. Web vs Mobile Recommendations
- **Web App (Desktop):** The primary environment for deep investigation, replay diagnostics, validation matrix review, and complex governance actions.
- **Mobile App:** Focused on Mission Control, emergency actions, and alert acknowledgement.
  - *Command Safety on Mobile:* Must leverage native biometric step-ups (FaceID/TouchID) as an *unlock step* to gate access to a secure local/session-based signing path. Biometrics do not replace cryptographic request authentication.
  - *Network Resilience:* Must degrade gracefully to a clear "Last Updated at X" state.

## 9. Backend Capability Gaps / API Improvements
The backend must provide these strict abstractions to decouple the UI from legacy implementations:

- `/api/v1/control-posture`: Must explicitly require and return:
  - requested mode
  - effective mode
  - live allowed
  - market-data posture
  - explicit blockers
  - live-control layer states
  - write-signing configured
  - manual kill-switch state
  - dry-run state
  - explicit fail-closed reasons

- `/api/v1/validation/readiness` & **Historical Evidence APIs**:
  - Must expose candidate-level and criterion-level resources.
  - Must explicitly list readiness blockers and evidence maturity.
  - Must support effective status derivation for legacy `null` records.
  - Must include historical validation evidence endpoints (historical validation reports, decision briefs, PBO report audit trails).

- `/api/v1/command-sessions`:
  - Must define how a client creates, refreshes, expires, and introspects a short-lived command session.
  - Must explicitly define how the session satisfies the signed-write requirement (e.g., by minting ephemeral signing material or issuing short-lived nonces/proofs to the client).
  - Provides the sanctioned control-plane contract to power the unlock UI without falling back to client-managed secret state.

- `/api/v1/commands`:
  - Must support canonical command identity (`command_id` / `job_id`).
  - Must provide status-by-id lookups.
  - Must provide recent-command list/history endpoints.
  - Must provide per-command event retrieval.
  - Must return enough data for cross-client searchable audit trails and to resume workflows after reconnect.

- `/api/v1/portfolio` (or `/api/v1/analytics`):
  - Must provide canonical endpoints for benchmark comparisons, symbol/group performance over time, and P&L views.
  - Must mandate first-class surfaces for risk/concentration views, portfolio slices, and attribution logic.
  - Must power workspace-grade, filter-adaptive analytics natively to prevent the UI from re-deriving portfolio risk or resorting to ad hoc aggregation and artifact-parsing.

- `/api/v1/runtime` (or `/api/v1/heartbeat`):
  - Must provide a canonical stream or polling surface for bot liveness, current evaluation state, and next planned action to power Mission Control directly.

- `/api/v1/incidents` (and `/api/v1/events`):
  - Must provide a structured timeline of alerts, fail-closed events, and native acknowledgement tracking.

- `/api/v1/investigations` (or `/api/v1/replay`):
  - Must support fetching canonical replay sessions, drift analysis, and side-by-side production comparisons to power the Investigations workspace natively without artifact-parsing.

## 10. Risks, Ambiguities, and Open Questions
- **Future Auth Model:** Is the current session flow scalable for a multi-operator cloud environment, or do we need a more formalized RBAC system for command access?
- **Multi-Operator Collisions:** What happens if two operators attempt to unlock and send conflicting commands simultaneously?
- **Mobile Provisioning:** How is the signing session securely bootstrapped to a mobile device?

## 11. Relationship to the visual/dashboard companion doc
While this document outlines the rigorous architectural boundaries, safety invariants, and UX control models, the actual presentation of these concepts is governed by the `TradingX_Dashboard_And_Design_System.md` spec.

The companion document defines:
- The "Obsidian Pulse" dark-mode aesthetic and signature colors.
- How the Live Enablement Panel is visually rendered to emphasize fail-closed states.
- The motion system used to denote heartbeats, countdowns, and real-time streaming transitions.
- The exact charting language used in the Portfolio & Risk workspace.
- The component grammar for displaying validation tri-states without cluttering the UI.
