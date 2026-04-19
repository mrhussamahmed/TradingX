---
id: DESIGN-0009
title: TradingX control center launcher design
version: 1.0.0
status: active
created: 2026-04-19
last_amended: 2026-04-19
supersedes: null
superseded_by: null
author_session: SESS-2026-04-19-028
---

# TradingX control center launcher design

## Goal

Give the operator a no-terminal startup path for TradingX that:

- launches the local control center with a double-clickable macOS app
- starts the local web control plane in the background if it is not
  already running
- opens the browser directly to the existing dashboard
- keeps actual bot start and stop actions inside the current website
  `Runtime Host` panel

This phase also applies the approved local operator defaults for the
current week-1 posture:

- `TRADINGX_SYMBOL_UNIVERSE=SPY`
- `TRADINGX_WEB_WRITE_MODE_ENABLED=true`

## Scope

This phase adds three tightly coupled pieces:

- `LCH-001`: a Python launcher flow that can detect or start the local
  TradingX web control plane
- `LCH-002`: a double-clickable macOS `TradingX Control Center.app`
  wrapper that invokes the launcher without showing the user a terminal
- `LCH-003`: local operator-default updates in `.env` for SPY-only week-1
  operation and enabled website write actions

This phase intentionally does not add:

- a new native desktop UI
- automatic bot start at login
- automatic order submission on app launch
- cloud hosting, remote access, or public exposure

## Operator flow

The approved operator experience is:

1. The operator double-clicks `TradingX Control Center.app`.
2. The launcher checks whether the TradingX control plane is already
   healthy on the configured local host and port.
3. If the control plane is already healthy, the launcher only opens the
   browser to the dashboard.
4. If the control plane is not healthy, the launcher starts the existing
   `tradingx web` server in the background, waits for readiness, then
   opens the browser.
5. The operator reviews the website and explicitly starts the bot from
   the `Runtime Host` panel.

The launcher never bypasses the website and never starts trading on its
own.

## Runtime contract

The launcher is a thin local bootstrapper around the existing web app.
It does not replace the FastAPI server, the React dashboard, or the
runtime-host control path.

The launcher owns only these decisions:

- how to decide whether the control plane is already running
- how to start the web server in the background when needed
- how long to wait for readiness before failing
- how to open the browser to the configured local URL

The existing website remains the only operator surface for:

- bot start and stop
- scheduler start and stop
- evidence review
- incident triage
- runtime-host readiness review

## Health and startup behavior

The launcher must:

- load the same `.env` file used by normal CLI operation
- resolve the effective web host and port from config
- probe `GET /api/config/summary` on the existing control plane
- treat a successful response as proof that the dashboard is already up
- start the control plane in a detached background subprocess when the
  endpoint is not healthy
- poll until the control plane becomes reachable or the timeout expires
- open the default browser to the local dashboard URL only after the
  endpoint is healthy

The default readiness timeout for this phase is `30` seconds.

The launcher must fail clearly when:

- the control plane never becomes healthy within the timeout
- the configured port cannot be bound and no healthy instance appears
- the underlying `uv run tradingx web --env-file .env` startup command
  exits immediately

## Packaging shape

The implementation should keep logic in Python and make the macOS app a
thin wrapper only.

The Python side should provide an explicit launcher entry point that can
be tested directly. The macOS app should do nothing more than:

- change into the repository root
- invoke the launcher entry point with the repo `.env`
- show a local error dialog if startup fails
- exit after the dashboard is opened or an error is surfaced

This keeps the real behavior versioned and testable in the repository,
while the app bundle remains a local convenience wrapper instead of a
second application surface.

## Safety rules

- The launcher is local-only and must use the configured local bind
  address.
- The launcher must not enable live trading.
- The launcher must not auto-start the bot, scheduler, or paper service.
- The launcher must not mutate strategy config, policy files, or
  evidence artifacts outside the normal web server startup path.
- The launcher should prefer reusing an existing healthy control plane
  instead of spawning duplicates.
- The website remains read/write only because local config explicitly
  opted in via `.env`.

## Configuration changes

The approved local changes for this machine are:

- set `TRADINGX_SYMBOL_UNIVERSE=SPY`
- set `TRADINGX_WEB_WRITE_MODE_ENABLED=true`

These are operator-local defaults for the current week-1 workflow, not a
general project-wide policy change.

## Testing shape

This phase requires:

- unit tests for launcher health-check success
- unit tests for launcher background-start behavior
- unit tests for launcher timeout and startup-failure behavior
- unit tests proving the launcher opens the browser only after readiness
- integration or CLI-level coverage for the new launcher entry point
- regression coverage showing the existing web app still serves the
  dashboard normally

The macOS wrapper itself may remain thin and largely untested, but the
Python launcher it invokes must be fully covered.

## Documentation updates

Implementation of this phase must update the operator-facing docs to
cover:

- how to use the double-click launcher
- where the launcher lives in the repo or local workspace
- what it does and does not start automatically
- the continued role of the `Runtime Host` panel for actual bot start
  and stop
