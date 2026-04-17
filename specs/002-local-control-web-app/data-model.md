---
id: DATAMODEL-0002
title: TradingX local control web app data model
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# Data Model

## WebAppConfig

| Field | Type | Notes |
| ----- | ---- | ----- |
| `host` | string | Default `127.0.0.1` |
| `port` | int | Local port for the site |
| `write_mode_enabled` | bool | Off by default |

## DashboardSnapshot

| Field | Type | Notes |
| ----- | ---- | ----- |
| `service_status` | object | Running, stopped, last cycle |
| `account_summary` | object | Cash, equity, buying power, daily PnL |
| `positions` | array | Current open positions |
| `alerts` | array | Latest operator alerts |
| `gate_statuses` | object | Latest known gate states |
| `recommendations` | object | Latest evaluation recommendation counts |
| `document_summary` | object | Session/handover counts and latest state |

## WebActionResult

| Field | Type | Notes |
| ----- | ---- | ----- |
| `action_id` | string | Stable UI-facing id |
| `action_type` | string | `paper_service_start`, `paper_recover`, etc. |
| `status` | string | `accepted`, `completed`, `failed`, `blocked` |
| `message` | string | Human-readable summary |
| `evidence_refs` | array | Artifact paths created or updated |

## ConfigProposal

| Field | Type | Notes |
| ----- | ---- | ----- |
| `proposal_id` | string | Timestamp-based id |
| `target_area` | string | Runtime, alerts, symbols, etc. |
| `proposed_values` | object | Structured proposal payload |
| `diff_preview` | string | Rendered change preview |
| `output_path` | string | File written under `config/proposals/` |

## DocumentRecord

| Field | Type | Notes |
| ----- | ---- | ----- |
| `doc_id` | string | Session/state/index identifier |
| `title` | string | Display label |
| `path` | string | Local file path |
| `preview` | string | Short preview text |
| `kind` | string | `handover`, `session_log`, `state`, `index` |
