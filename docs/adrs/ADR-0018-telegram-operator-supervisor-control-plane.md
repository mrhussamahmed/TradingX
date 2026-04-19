---
id: ADR-0018
title: Use a local supervisor with a single-chat Telegram operator command plane
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Context

`ADR-0017` hardened week-1 safety, but the repo still lacks two
operator-facing controls called out in the week-1 contract:

- `TEL-001`: a minimal Telegram command surface
- `SUP-001`: an independent local supervisor for unattended operation

Week 1 remains local-only, single-operator, dry-run first, and
paper-only. The control plane must not bypass the SQLite journal,
policy snapshots, or the runtime lock.

# Decision

Adopt a local supervisor process as the week-1 control parent and give
it a single-authorized-chat Telegram command plane.

The supervisor:

- owns the long-running market-day scheduler child process
- owns persistent halt, clearance, and kill control files
- writes a durable supervisor state artifact
- optionally polls Telegram with one authorized `chat_id`
- performs broker-side `/flatten` actions independently of the child

The child trading workload remains isolated in a separate local process.
Telegram commands never talk to the child directly; they mutate
supervisor-owned control state or trigger supervisor-owned actions.

# Consequences

## Positive

- week-1 operator control no longer depends on the website being open
- supervisor can stop or restart the child without modifying the trading
  loop entrypoints
- Telegram remains narrow and auditable instead of becoming a general
  admin API
- the existing runtime lock remains the single-writer guard for the data
  root

## Negative

- there is one more long-running local process to supervise
- the control plane must maintain persistent state and Telegram offsets
- operator commands now add additional test surface around authorization,
  flatten behavior, and child lifecycle

# Guardrails

- Only one configured Telegram `chat_id` is authorized.
- Telegram polling is optional and disabled unless the bot token and chat
  id are configured.
- `dry_run` posture and week-1 policy remain authoritative; supervisor
  commands cannot enable live trading.
- `/kill` stops decisioning without flattening.
- `/flatten` is independent of halt state and broker-submits exits even
  if the trading child is stopped.
