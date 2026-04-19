---
id: TASKS-0010
title: TradingX operator control plane task list
version: 1.0.1
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: TASKS-0010@1.0.0
superseded_by: null
author_session: SESS-2026-04-19-027
---

# Tasks: TradingX operator control plane

**Input**: Design and spec documents from
`/specs/010-operator-control-plane/`

- [x] T001 Add file-backed operator control state with halt, clearance,
      kill, and status helpers
- [x] T002 Add Telegram command parsing, authorization, and polling
      transport
- [x] T003 Add supervisor child lifecycle management and bounded restart
      policy
- [x] T004 Add flatten and positions/status/today reporting helpers
- [x] T005 Add CLI entrypoints and fallback operator controls
- [x] T006 Update operator docs, architecture map, state, and handoff
- [x] T007 Run `./scripts/validate`, `python3 scripts/check_index.py`,
      and promote the branch
