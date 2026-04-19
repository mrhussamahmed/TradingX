---
id: RUNBOOK-0004
title: Week 1 premortem
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-025
---

# TradingX Week 1 Premortem

## Purpose

This document records the top ten ways the first paper-trading week can
fail, together with the control that is supposed to prevent, detect, or
contain each failure.

Reviewer set for week 1:

- `snooze`
- `solo`
- `week1`

If a future session changes any control below, this file and
[`gates-0001-status`](</Users/ahmedabd/Desktop/AI Projects/TradingX/src/tradingx/__main__.py:1>)
must be updated together.

## Failure modes and controls

1. Duplicate order after restart.
Control:
deterministic `client_order_id`, append-only SQLite journal, broker
query-before-resubmit, and startup reconciliation before trading.

2. Bot trades through a reconciliation divergence.
Control:
three-way reconciliation enters `recovery_required`, blocks new entries,
and only a clearance request followed by a clean reconciliation returns
the runtime to `nominal`.

3. Market-data stall makes the strategy trade on stale quotes.
Control:
policy quote-age guardrails, service-level `data_unavailable`
classification, and dry-run report anomaly surfacing.

4. Broker/account state goes stale or unavailable.
Control:
broker staleness thresholds, repeated-read failure detection, and
service-level `broker_unavailable` status.

5. Bot exceeds its intended daily trading budget.
Control:
week-1 policy snapshot with hard caps:
`3` new entries/day, `2` concurrent positions, `1` entry/symbol/day,
no same-session re-entry, `$500` per position, `30%` deployed-capital
limit.

6. Intraday losses keep compounding because the bot resumes too soon.
Control:
sticky `0.5%` session drawdown halt, marked against session-start
equity, with no same-session auto-resume.

7. Bot carries unintended overnight risk.
Control:
flat-by-close ladder with explicit T-15, T-10, T-5, T-2, and T-0
escalation stages in the policy snapshot.

8. Monday dry-run looks safe but hides operational blind spots.
Control:
post-close dry-run report, synthetic HALT/REJECT/RECOVERY drills,
Sunday rehearsal, and `GATES-0001` readiness evaluation.

9. Research or later changes mutate live behavior without governance.
Control:
week-1 runtime stays policy-snapshot driven, dry-run posture is locked
before `08:00 ET`, and the Tuesday go-live gate must remain `pass`
before any live submission path is enabled.

10. Operator confusion during an incident causes the wrong action.
Control:
explicit `/flatten` versus `/kill` semantics, Sunday rehearsal, and the
operator manual plus week-1 rehearsal runbook.

## Residual risk accepted for week 1

- Alpaca paper fills remain optimistic relative to live execution.
Containment:
dry-run first, marketable-limit price caps, and no overnight exposure.

- Telegram controls may slip while the core trading controls remain CLI
or file-trigger based.
Containment:
the rehearsal runbook defines CLI/OS fallback controls and those must be
tested before Monday.
