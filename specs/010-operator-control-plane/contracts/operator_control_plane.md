---
id: CONTRACT-0011
title: Operator control plane contract
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-026
---

# Operator control plane contract

## Telegram commands

- `/status`: read-only status summary
- `/positions`: read-only positions and open-order count summary
- `/today`: read-only daily summary
- `/halt`: set persistent halt request
- `/resume`: clear halt and kill requests, then record clearance request
- `/flatten`: cancel working orders and flatten positions
- `/kill`: set persistent kill request and request a clean child stop at
  the next cycle boundary

## Authorization

- Exactly one configured Telegram `chat_id` is privileged.
- Unauthorized chats receive a denied result and no state mutation.

## Supervisor rules

- The supervisor owns the child process lifecycle.
- The child trading workload is isolated in a separate local process.
- The supervisor writes a durable state artifact.
- `restart_policy_enabled` defaults to `false`.
