---
id: RESEARCH-0004
title: TradingX Gate 3 operations and evidence research
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-016
---

# Research: TradingX Gate 3 operations and evidence

## Existing repo capabilities

- The paper bot already persists trade intents, orders,
  reconciliations, operator alerts, service cycles, evaluation
  evidence, validation reports, and gate assessments.
- The operator platform already supports read models, incident handling,
  replay, explorer queries, and bounded day-operations actions.
- The CLI already supports paper-loop, paper-service, recovery,
  benchmark prep, gate-report, and decision-report flows.

## Confirmed gap

The current artifact set is not enough to answer Gate 3 questions
truthfully. It lacks durable records for:

- per-fill slippage
- closed-trade outcomes
- explicit recovery exercises
- explicit emergency alert drills
- a criterion-by-criterion Gate 3 readiness report

## Design conclusion

The safest implementation is to extend the existing artifact model
rather than infer Gate 3 from service-cycle summaries alone. This keeps
the website and CLI backed by the same evidence and avoids browser-only
state.

## Open evidence limitations handled in design

- If no reference expectation exists for hit rate or Sharpe, Gate 3
  readiness must remain `pending`.
- If alerting is not configured, an alert drill must persist a failed or
  pending drill record rather than silently succeeding.
- If there are no closed trades yet, trade-count progress can still be
  shown while expectation-based criteria remain pending.
