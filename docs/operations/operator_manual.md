---
id: RUNBOOK-0003
title: TradingX operator manual
version: 1.4.0
status: active
created: 2026-04-18
last_amended: 2026-04-19
supersedes: RUNBOOK-0003@1.3.0
superseded_by: null
author_session: SESS-2026-04-19-026
---

# TradingX Operator Manual

## Purpose

This document is the single operator-facing instruction manual for
starting, using, monitoring, and maintaining TradingX.

Use it as the first place to look when you need to:

- set up the bot on a machine
- start the bot through the CLI or website
- run manual or unattended paper-trading workflows
- generate validation and Gate 3 evidence
- recover from interruptions
- understand what each dashboard/control does

## Maintenance rule

This manual MUST be updated in any future session that changes any of:

- startup steps
- required environment variables
- CLI commands
- local website controls or dashboards
- scheduler or automation workflows
- validation or evidence workflows
- recovery, drill, or troubleshooting steps

If a future implementation changes operator behavior and this file is
not updated in the same session, that session is incomplete.

## Safety boundaries

TradingX is currently operated under these boundaries:

- paper trading only
- live trading stays disabled
- local-only website and controls
- write actions are disabled by default in the website
- regular-hours enforcement remains active in the trading workflow

Do not add live credentials or attempt live trading from this manual.

## Week 1 controls

For the current week-1 dry-run posture, use these supporting runbooks:

- [week1_premortem.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/operations/week1_premortem.md:1)
- [week1_rehearsal_and_gates.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/operations/week1_rehearsal_and_gates.md:1)

Week-1 defaults are intentionally conservative:

- `SPY` only
- Monday dry-run only
- Tuesday earliest possible submit date
- flat by close
- zero overnight exposure
- sticky `0.5%` drawdown halt

Before Monday dry-run, generate the week-1 rehearsal artifacts:

```bash
uv run tradingx week1-rehearsal --env-file .env --output-dir artifacts/ops
```

This writes:

- `artifacts/ops/operator_control_verification.json`
- `artifacts/ops/premortem_review.json`
- `artifacts/ops/sunday_rehearsal.json`
- `artifacts/ops/reconciliation_review.json`
- `artifacts/ops/paper_account_starting_state.json`

## Core files and locations

- Main environment file: [`.env`](</Users/ahmedabd/Desktop/AI Projects/TradingX/.env:1>)
- Example environment file: [`.env.example`](</Users/ahmedabd/Desktop/AI Projects/TradingX/.env.example:1>)
- Main repo guide: [README.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/README.md:1)
- Project state: [STATE.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/handover/STATE.md:1)
- Acceptance gates: [acceptance_gates.md](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/validation/acceptance_gates.md:1)
- Week-1 SQLite journal: `data/journal.db`
- Week-1 content-addressed decision snapshots: `data/snapshots/`
- Week-1 policy snapshots: `data/policy/`

## Prerequisites

Before running TradingX, make sure you have:

- the repository checked out locally
- `uv` available
- `node` and `npm` available for the website
- valid Alpaca paper credentials in `.env`

## First-time setup

### 1. Install backend dependencies

```bash
uv sync --all-groups
```

### 2. Install frontend dependencies

```bash
npm --prefix webapp install
```

### 3. Populate `.env`

Start from [`.env.example`](</Users/ahmedabd/Desktop/AI Projects/TradingX/.env.example:1>) and make sure these paper settings are present:

```dotenv
ALPACA_PAPER_API_KEY=your-paper-key
ALPACA_PAPER_API_SECRET=your-paper-secret
ALPACA_PAPER_ACCOUNT_ID=your-paper-account-id
```

Common optional settings:

- `TRADINGX_SYMBOL_UNIVERSE`
- `TRADINGX_SERVICE_INTERVAL_SECONDS`
- `TRADINGX_SCHEDULER_POLL_SECONDS`
- `TRADINGX_WEB_WRITE_MODE_ENABLED`
- `TRADINGX_TELEGRAM_*`
- `TRADINGX_SMTP_*`

### 4. Build the website bundle

```bash
npm --prefix webapp run build
```

### 5. Verify the config loads safely

```bash
uv run tradingx config-summary --env-file .env
uv run tradingx live-disable-status --env-file .env
```

What to confirm:

- paper credentials are detected
- live trading is still disabled
- symbol universe and intervals look correct

## Main ways to operate TradingX

There are six primary operating modes:

1. Week-1 operator supervisor
2. Local trading appliance from the website
3. Single manual cycle
4. Recurring paper service
5. One bounded market day
6. Recurring market-day scheduler

Use the smallest mode that fits what you need.

## Mode 1: Run the week-1 operator supervisor

This is the preferred week-1 control surface when you want one local
parent process plus Telegram or CLI fallback controls.

```bash
uv run tradingx run-operator-supervisor --env-file .env --symbols SPY --quantity 1 --interval-seconds 300
```

What it does:

- holds the week-1 runtime lock for the entire session
- supervises the long-running trading child process
- persists state under `artifacts/operator_platform/supervisor/`
- reads control files under `data/control/`
- optionally polls Telegram if the bot token and chat id are configured

Telegram commands when enabled:

- `/status`
- `/positions`
- `/today`
- `/halt`
- `/resume`
- `/flatten`
- `/kill`

Important semantics:

- `/kill` stops decisioning without flattening
- `/flatten` cancels working orders and attempts to flatten positions
  independently of the child
- `/resume` clears halt/kill requests and records a clearance request
- if Telegram is not configured, the CLI/file-based fallback controls
  from `week1_rehearsal_and_gates.md` remain valid

## Mode 2: Start the local trading appliance

This is now the preferred operator workflow.

1. Start the local website:

```bash
uv run tradingx web --env-file .env
```

2. Open [http://127.0.0.1:8765](http://127.0.0.1:8765)
3. Enable `TRADINGX_WEB_WRITE_MODE_ENABLED=true` in `.env` if you want
   action buttons live.
4. Use the `Runtime Host` panel in the `Command Center` view:
   - `Start Bot`
   - `Refresh Learning Proposal`
   - `Stop Bot`

What the runtime host does before it starts the bot:

- loads or creates the active strategy activation record
- loads or creates the approved model-weight snapshot
- builds historical warmup for the configured universe
- synchronizes broker/account state
- ranks the current universe and records the latest opportunity
  selection
- fails closed if warmup or activation prerequisites are not ready

Operator outputs created by this mode:

- runtime state under `artifacts/operator_platform/runtime_host/`
- warmup artifacts under `artifacts/operator_platform/historical_warmups/`
- opportunity selection artifacts under
  `artifacts/operator_platform/opportunity_selections/`
- model-weight proposals under
  `artifacts/operator_platform/model_weight_proposals/`

CLI equivalent for bounded diagnostics:

```bash
uv run tradingx runtime-start --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --max-cycles 1
```

## Mode 3: Run one manual paper cycle

Use this when you want one bounded pass for a single symbol.

```bash
uv run tradingx paper-loop --env-file .env --symbol SPY --quantity 1
```

Typical use:

- quick verification
- one-off manual operation
- checking that paper execution still works

If the loop is interrupted and you need to resume safely:

```bash
uv run tradingx paper-recover --env-file .env --symbol SPY
```

All week-1 trading entry points now enforce a single-writer runtime
lock on `data/runtime.pid`. If a second process attempts to start
against the same data root, TradingX refuses to run and returns a
blocked error instead of risking duplicate paper orders.

## Mode 4: Run the recurring paper service

Use this when you want repeated bounded cycles across a symbol universe.

```bash
uv run tradingx run-paper-service --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300
```

Helpful option:

- `--max-cycles 1`
  Use this for a bounded verification run.

What it does:

- scans the configured symbols
- runs the paper loop repeatedly
- writes service-cycle artifacts under `artifacts/paper_loop/`

## Mode 5: Run one bounded market day

Use this when you want one full automation workflow for a trading day.

```bash
uv run tradingx run-market-day --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --max-heartbeats 3
```

What it does:

- writes a pre-open checkpoint
- runs repeated bounded heartbeats
- performs closeout
- refreshes replay-slippage and Gate 3 evidence

Helpful option:

- `--max-heartbeats 3`
  Good for bounded local verification

## Mode 6: Run the recurring market-day scheduler

Use this when you want unattended recurring operation across future
trading days.

```bash
uv run tradingx run-market-scheduler --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300
```

Helpful options:

- `--poll-interval-seconds 60`
- `--max-scheduled-days 1`

What it does:

- polls the market calendar
- waits for the current or next eligible session
- launches at most one `run-market-day` workflow per trading day
- writes schedule artifacts under
  `artifacts/operator_platform/market_day_schedules/`

Important limitation:

- the scheduler still needs a running local process
- if the machine or process stops, future days will not launch until the
  scheduler is started again

## Start the local website

```bash
uv run tradingx web --env-file .env
```

Then open:

- [http://127.0.0.1:8765](http://127.0.0.1:8765)

By default:

- the site is local-only
- the site is read-only

To enable action buttons, set this in `.env`:

```dotenv
TRADINGX_WEB_WRITE_MODE_ENABLED=true
```

## How to use the website

### Operations deck

Use this for:

- running a single cycle
- starting or stopping the paper service
- triggering recoveries

### Runtime Host

Use this for the supervised bot workflow:

- start the bot from one control surface
- inspect runtime readiness and fail-closed reasons
- inspect the active strategy activation record
- inspect the active model-weight snapshot
- inspect the latest ranked opportunity and selected symbol
- trigger a bounded learning proposal refresh

### Gate cockpit

Use this to inspect:

- current gate state
- recommendation summaries
- validation posture

### Evidence views

Use these to review:

- service-cycle outputs
- operator alerts
- validation artifacts
- drill outputs

### Gate 3 Ops

Use this for:

- readiness status
- replay-slippage status
- market-session checkpoints
- automation history
- scheduler controls and scheduler status

### Project intelligence and records

Use these to inspect:

- project state
- handover/session records
- repo-side operational context

### Proposal studio

Use this for:

- safe config proposals written under `config/proposals/`

## Step-by-step daily operation guide

### Option A: Manual market-hours session

1. Verify config and safety state.
```bash
uv run tradingx config-summary --env-file .env
uv run tradingx live-disable-status --env-file .env
```
2. Start the website.
```bash
uv run tradingx web --env-file .env
```
3. Open the `Command Center` and use `Start Bot` in the `Runtime Host`
   panel if you want the supervised appliance workflow.
4. If you want lower-level control instead, run `paper-loop`,
   `run-paper-service`, or `run-market-day`.
5. Review evidence in the website and under `artifacts/`.
6. If needed, run `paper-recover`.

### Option B: Unattended recurring operation

1. Verify `.env` and intervals.
2. Start the website if desired.
3. Start the operator supervisor if you want Telegram or fallback control
   over the unattended session.
```bash
uv run tradingx run-operator-supervisor --env-file .env --symbols SPY --quantity 1 --interval-seconds 300
```
4. Or start the recurring scheduler directly if you only need the
   scheduler loop.
```bash
uv run tradingx run-market-scheduler --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300
```
5. Keep that process alive.
6. Monitor scheduler state in the website `Gate 3 Ops` panel or via
   Telegram `/status`.
7. Review the latest schedule and automation artifacts after each run.

## Validation and evidence workflows

### Prepare benchmark closes

```bash
uv run tradingx prepare-benchmark-closes --env-file .env --window-start 2023-01-01 --window-end 2026-04-17
```

### Generate Gate 1 or Gate 2 reports

```bash
uv run tradingx gate-report --env-file .env --gate 1 --benchmark-closes-file artifacts/validation/benchmarks/spy-2023-01-01-2026-04-17-dividend.json --window-start 2023-01-01 --window-end 2026-04-17
```

### Generate a decision brief

```bash
uv run tradingx decision-report --gate 1
```

### Refresh replay-slippage evidence

```bash
uv run tradingx replay-slippage-report --paper-artifact-root artifacts/paper_loop --validation-artifact-root artifacts/validation
```

### Generate Gate 3 readiness and package artifacts

```bash
uv run tradingx gate3-report --env-file .env
uv run tradingx gate3-package --env-file .env
```

## Recovery and drills

### Recover a symbol safely

```bash
uv run tradingx paper-recover --env-file .env --symbol SPY
```

### Run the recovery drill

```bash
uv run tradingx recovery-drill --env-file .env --symbol SPY
```

### Run the alert drill

```bash
uv run tradingx alert-drill --env-file .env --channel smtp
```

## Where to look for outputs

- Paper-loop and service artifacts:
  `artifacts/paper_loop/`
- Validation artifacts:
  `artifacts/validation/`
- Operator-platform artifacts:
  `artifacts/operator_platform/`

High-value subdirectories:

- `artifacts/paper_loop/service_cycles/`
- `artifacts/paper_loop/operator_alerts/`
- `artifacts/validation/benchmarks/`
- `artifacts/validation/gate3_reports/`
- `artifacts/validation/gate3_packages/`
- `artifacts/operator_platform/market_automation_runs/`
- `artifacts/operator_platform/market_day_schedules/`

## Troubleshooting

### The smoke test skips

Expected when:

- regular market hours are closed
- `.env` does not contain real paper credentials

### The website shows controls but they do not run

Check:

- `TRADINGX_WEB_WRITE_MODE_ENABLED=true`
- the website was restarted after changing `.env`

### The scheduler never starts a market day

Check:

- the process is still running
- the poll interval is reasonable
- the market is in or approaching an eligible session
- a schedule artifact does not already exist for the current trading
  day

### The website is stale

Check:

- the backend process is still running
- the frontend bundle was built with
  `npm --prefix webapp run build`

### You want a safe repo-wide verification pass

Run:

```bash
./scripts/validate
```

## Operator checklist

Before running:

- confirm `.env` is correct
- confirm live trading is still disabled
- confirm website write mode is only enabled when intentionally needed

While running:

- watch alerts, service state, and Gate 3 Ops
- review evidence and schedule artifacts

After running:

- review outputs under `artifacts/`
- refresh validation or Gate 3 reports if needed
- update this manual in the same session if operator behavior changed
