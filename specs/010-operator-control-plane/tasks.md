---
id: TASKS-0010
title: TradingX operator control plane task list
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Tasks: TradingX operator control plane

**Input**: Design and spec documents from
`/specs/010-operator-control-plane/`

- [ ] T001 Add file-backed operator control state with halt, clearance,
      kill, and status helpers
- [ ] T002 Add Telegram command parsing, authorization, and polling
      transport
- [ ] T003 Add supervisor child lifecycle management and bounded restart
      policy
- [ ] T004 Add flatten and positions/status/today reporting helpers
- [ ] T005 Add CLI entrypoints and fallback operator controls
- [ ] T006 Update operator docs, architecture map, state, and handoff
- [ ] T007 Run `./scripts/validate`, `python3 scripts/check_index.py`,
      and promote the branch
