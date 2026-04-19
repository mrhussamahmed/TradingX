---
id: RUNBOOK-0005
title: Week 1 rehearsal and gates
version: 1.2.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: RUNBOOK-0005@1.1.0
superseded_by: null
author_session: SESS-2026-04-19-026
---

# TradingX Week 1 Rehearsal And Gates

## Purpose

This runbook defines the Sunday-evening rehearsal, the Monday dry-run
review flow, and the Tuesday earliest-go-live gate.

## Sunday rehearsal checklist

1. Generate the Sunday rehearsal artifacts and record the paper-account
   starting state:

```bash
uv run tradingx week1-rehearsal --env-file .env --output-dir artifacts/ops
```

2. Start the runtime or paper loop in dry-run posture and verify policy
artifacts, decision snapshots, and the SQLite journal are being written.

3. Exercise the stop path:
`/kill` or the documented CLI/OS fallback stop path.

4. Exercise the flatten path:
`/flatten` or the documented CLI fallback exit path.

5. Manually inspect the latest journal rows and reconciliation artifacts.

6. Run the synthetic drills:
- HALT drill
- REJECT drill
- RECOVERY drill

7. Verify these rehearsal artifacts exist under `artifacts/ops/`:
- `operator_control_verification.json`
- `sunday_rehearsal.json`
- `premortem_review.json`
- `reconciliation_review.json`
- `paper_account_starting_state.json`

## Monday dry-run review commands

Generate the Monday report:

```bash
uv run tradingx dry-run-report \
  --paper-artifact-root artifacts/paper_loop \
  --snapshot-root data/snapshots \
  --journal-path data/journal.db \
  --output-dir artifacts/dry_run_reports
```

Evaluate the Tuesday gate:

```bash
uv run tradingx gates-0001-status \
  --dry-run-report-path artifacts/dry_run_reports/dry-run-report-2026-04-20.json \
  --ops-artifact-root artifacts/ops
```

## GATES-0001 criteria

All of these must be `pass` before any Tuesday submission session is
considered:

1. `zero_unhandled_exceptions`
2. `zero_unresolved_reconciliation_discrepancies`
3. `blocked_intents_have_documented_reasons`
4. `cycles_within_budget`
5. `operator_control_path_verified`
6. `premortem_review_complete`
7. `major_path_coverage_complete`
8. `sunday_rehearsal_complete`

If any criterion is not `pass`, Tuesday remains dry-run.

## Required operator artifacts

The gate evaluator reads these files:

- `artifacts/ops/operator_control_verification.json`
  Required field:
  `{"status":"pass"}`

- `artifacts/ops/premortem_review.json`
  Required field:
  `{"reviewers":["snooze","solo","week1"]}`

- `artifacts/ops/sunday_rehearsal.json`
  Required field:
  `{"status":"pass"}`

- `artifacts/ops/reconciliation_review.json`
  Required field:
  `{"unresolved_discrepancy_count":0}`

- `artifacts/ops/paper_account_starting_state.json`
  Informational artifact recording the Sunday paper-account baseline.

## Notes

- No dry-run-to-live flip after `08:00 ET`.
- Monday, April 20, 2026 is dry-run only.
- Tuesday, April 21, 2026 is only the earliest possible submit date,
  not a promise to submit.
- If Telegram credentials are configured, the week-1 operator supervisor
  now exposes:
  - `/status`
  - `/positions`
  - `/today`
  - `/halt`
  - `/resume`
  - `/flatten`
  - `/kill`
- CLI fallback operator controls for week 1:
  - status: `SIGUSR1` to write the current state snapshot
  - clean stop: `SIGTERM`
  - force stop: `SIGKILL`
  - halt request: `touch data/halt_request`
  - clearance request: `touch data/clearance_request`
  - flatten: run the dedicated flatten CLI path when available
- Canonical week-1 storage paths:
  - `data/journal.db`
  - `data/snapshots/`
  - `data/policy/policy_snapshot_<hash>.yaml`
