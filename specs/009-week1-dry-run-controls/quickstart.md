---
id: QUICKSTART-0010
title: TradingX week-1 dry-run controls quickstart
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-024
---

# Quickstart: TradingX week-1 dry-run controls

## Monday posture

- Run the appliance in `dry_run`.
- Trade `SPY` only.
- Confirm the policy snapshot for the session before 08:00 ET.
- Do not flip `dry_run` after 08:00 ET.

## Required artifacts

- policy snapshot
- decision snapshots
- OMS journal rows
- HALT / REJECT / RECOVERY drill artifacts
- Monday dry-run report
- Tuesday gate check artifact

## Minimum operator actions

- verify startup gate summary
- review post-close dry-run report
- review premortem and rehearsal checklist
- approve or deny Tuesday submit based on artifact-backed gates
