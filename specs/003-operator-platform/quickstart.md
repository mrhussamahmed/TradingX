---
id: QUICKSTART-0004
title: TradingX operator platform quickstart
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-014
---

# Quickstart: TradingX operator platform

## Run locally

```bash
npm --prefix webapp install
npm --prefix webapp run build
uv run tradingx web --env-file .env
```

Open `http://127.0.0.1:8765/`.

## Enable bounded controls

Set this in `.env` before starting the app:

```dotenv
TRADINGX_WEB_WRITE_MODE_ENABLED=true
```

## Recommended operator flow

1. Open `Command Center` to verify paper-only posture, service state,
   account state, and incidents.
2. Open `Research Studio` to review current candidate evidence and gate
   posture.
3. Use `Incident Center` to review and acknowledge operator-visible
   alerts.
4. Use `Trade Intelligence` and `Replay Lab` to inspect executions,
   blocks, and recoveries.
5. Use `Session Close` in write mode to generate a daily digest under
   `artifacts/operator_platform/daily_digests/`.
