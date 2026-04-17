---
id: QUICKSTART-0003
title: TradingX local control web app quickstart
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-013
---

# Quickstart

## 1. Install backend and frontend dependencies

```bash
uv sync --all-groups
cd webapp && npm install
npm run build
```

## 2. Start the local website

```bash
uv run tradingx web --env-file .env
```

Expected behavior:

- The backend binds to `127.0.0.1` by default.
- The site serves a dashboard, evidence browser, gates view, config
  workspace, and project-record browser.
- Write actions stay disabled unless the dedicated web write-mode flag is
  enabled.

## 3. Run validation

```bash
./scripts/validate
```

This must cover backend tests, frontend tests, build verification, and
browser-level smoke coverage for the local website.
