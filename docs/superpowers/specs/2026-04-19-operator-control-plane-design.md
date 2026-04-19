---
id: DESIGN-0008
title: TradingX operator control plane design
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# TradingX operator control plane design

## Goal

Add a minimal production-grade operator control plane for week 1 so the
bot can be started, supervised, halted, resumed, flattened, and killed
from Telegram while the actual trading child process remains isolated.

## Scope

This phase adds two tightly coupled pieces:

- `TEL-001`: a single-authorized-chat Telegram command surface with
  `/status`, `/positions`, `/today`, `/halt`, `/resume`, `/flatten`,
  and `/kill`
- `SUP-001`: a local supervisor that owns the long-running market-day
  scheduler child process, restart policy, pid/state files, and the
  independent stop path

This phase intentionally does not add multi-user auth, webhooks,
multiple bots, or cloud services.

## Core runtime model

- The supervisor is the only long-running parent process for week-1
  unattended operation.
- The trading child is still the bounded existing scheduler/runtime
  path, launched as a subprocess.
- Telegram commands never talk to the trading child directly.
- Operator commands mutate file-backed control state or request
  supervisor-owned actions.
- New entries are blocked through a file-backed halt request.
- `kill` stops decisioning without flattening.
- `flatten` is independent of the child loop and talks to Alpaca paper
  directly.

## Command semantics

- `/status`: return supervisor state, child liveness, halt/kill flags,
  and latest known runtime posture
- `/positions`: return current Alpaca paper positions and open-order
  count
- `/today`: summarize today’s service cycles, snapshots, journal events,
  blocked intents, and anomalies
- `/halt`: create the persistent halt request and prevent new entries
- `/resume`: clear the halt request, clear the kill flag, and record a
  clearance request
- `/flatten`: cancel open orders and flatten all paper positions
  independently of the child
- `/kill`: set the persistent kill flag and stop the child process
  without flattening

## Safety rules

- Only one configured Telegram `chat_id` is authorized.
- Unknown chats receive no privileged response.
- The supervisor never auto-enables live trading.
- Restart policy is bounded and opt-in.
- Control files live under `data/control/`.
- Supervisor state lives under `artifacts/operator_platform/supervisor/`.
- `/status`, `/positions`, and `/today` are read-only and must not start
  the child as a side effect.

## Testing and readiness

This phase requires:

- command parsing and authorization tests
- halt/resume/kill/flatten supervisor tests
- child restart policy tests
- CLI command tests
- full repo validation after promotion
