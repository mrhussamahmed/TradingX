---
id: DATAMODEL-0010
title: TradingX operator control plane data model
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Data Model: TradingX operator control plane

## OperatorControlState

- `halt_requested`
- `kill_requested`
- `clearance_requested`
- `updated_at_utc`
- `last_command`

## SupervisorState

- `status`
- `child_pid`
- `child_status`
- `restart_count`
- `restart_policy_enabled`
- `halt_requested`
- `kill_requested`
- `clearance_requested`
- `last_command`
- `last_error`
- `updated_at_utc`

## TelegramCommandResult

- `command`
- `authorized`
- `status`
- `message`
- `recorded_at_utc`

## TodaySummary

- `session_date`
- `cycle_count`
- `decision_snapshot_count`
- `journal_event_count`
- `blocked_reason_counts`
- `anomalies`
