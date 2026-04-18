# TradingX

TradingX is a paper-only US equities trading bot built with a strict
evidence-first workflow. The current branch contains a working Stage 1
implementation that can:

- run a deterministic paper trading loop with auditable risk decisions
- run a recurring paper trading service across a bounded symbol universe
- recover and reconcile without duplicate paper submissions
- exit existing paper positions with deterministic take-profit and
  stop-loss rules
- evaluate the three mandatory baseline strategy families against SPY
- generate Gate 1 and Gate 2 validation reports from benchmark close
  series without waiting for market hours
- emit persisted operator alerts locally or through optional Telegram and
  SMTP transports while live trading stays disabled
- report richer paper-service evidence, including blocked-trade counts,
  latest portfolio state, evaluation recommendation summaries, and gate
  assessment status
- persist Gate 3 execution-lifecycle, closed-trade, recovery-drill,
  alert-drill, and market-session evidence
- generate Gate 3 readiness reports and promotion packages from the
  persisted paper evidence trail
- generate replay-slippage cross-check evidence from persisted paper
  execution context
- run a bounded market-day automation workflow that performs pre-open,
  heartbeat, closeout, and automatic Gate 3 evidence refresh
- run a recurring market-day scheduler that launches the bounded
  market-day workflow automatically on trading days and records one
  durable schedule artifact per launched day
- serve a local control website with a React dashboard over the existing
  paper-trading and evidence pipeline

For the full step-by-step startup and operating guide, use the
[TradingX Operator Manual](/Users/ahmedabd/Desktop/AI%20Projects/TradingX/docs/operations/operator_manual.md:1).

## Core commands

```bash
uv run tradingx config-summary --env-file .env
uv run tradingx live-disable-status --env-file .env
uv run tradingx paper-loop --env-file .env --symbol SPY --quantity 1
uv run tradingx run-paper-service --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --max-cycles 1
uv run tradingx run-market-day --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --max-heartbeats 3
uv run tradingx run-market-scheduler --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --poll-interval-seconds 60 --max-scheduled-days 1
uv run tradingx paper-recover --env-file .env --symbol SPY
uv run tradingx evidence-report --artifact-root artifacts/paper_loop
uv run tradingx prepare-benchmark-closes --env-file .env --window-start 2023-01-01 --window-end 2026-04-17
uv run tradingx gate-report --env-file .env --gate 1 --benchmark-closes-file artifacts/validation/benchmarks/spy-2023-01-01-2026-04-17-dividend.json --window-start 2023-01-01 --window-end 2026-04-17
uv run tradingx decision-report --gate 1
uv run tradingx recovery-drill --env-file .env --symbol SPY
uv run tradingx alert-drill --env-file .env --channel smtp
uv run tradingx replay-slippage-report --paper-artifact-root artifacts/paper_loop --validation-artifact-root artifacts/validation
uv run tradingx gate3-report --env-file .env
uv run tradingx gate3-package --env-file .env
uv run tradingx web --env-file .env
```

`paper-loop` is intended for regular US market hours and paper mode
only. `run-paper-service` repeats the loop across a bounded universe and
persists a service-cycle summary on every pass; omit `--max-cycles` to
leave it running. `paper-recover` resumes the latest persisted loop for
a symbol without creating a duplicate submission.

`run-market-day` performs one bounded automation workflow: it writes a
pre-open checkpoint, runs repeated bounded heartbeats, refreshes
replay-slippage evidence and Gate 3 readiness, then writes the closeout
checkpoint and promotion package. Omit `--max-heartbeats` only when you
want it to keep running until the market closes.

`run-market-scheduler` sits above `run-market-day`: it polls the
regular-hours market calendar, launches at most one market-day workflow
per trading day, persists one schedule artifact under
`artifacts/operator_platform/market_day_schedules/`, and exposes the
next scheduled run time to the CLI and local website. Omit
`--max-scheduled-days` to leave it running indefinitely, or use
`TRADINGX_SCHEDULER_POLL_SECONDS` to control the default waiting
cadence.

If `TRADINGX_TELEGRAM_BOT_TOKEN` / `TRADINGX_TELEGRAM_CHAT_ID` or the
`TRADINGX_SMTP_*` settings are present in `.env`, operator alerts are
delivered through those transports in addition to being persisted under
`artifacts/paper_loop/operator_alerts/`.

`prepare-benchmark-closes` fetches daily closes from Alpaca market data
and writes a metadata-rich artifact under `artifacts/validation/benchmarks/`
by default. `gate-report` writes validation artifacts under
`artifacts/validation/`. The benchmark closes input may still be a JSON
array like `["100","101.5"]` or a simple comma/newline-delimited list,
but when you use the prepared artifact the command can infer whether the
series is dividend-adjusted and will reject window mismatches.

`decision-report` reads the latest validation artifacts together with the
paper-loop evidence summary and prints one operator-ready brief plus a
gate-decision alert preview. It is meant to answer the practical next
question after a gate run: should the operator advance, wait for more
evidence, or send the strategy back for changes?

`recovery-drill` and `alert-drill` persist explicit operational-drill
artifacts for Gate 3. `gate3-report` writes a readiness report from the
current paper evidence, and `gate3-package` writes the matching
promotion package. `replay-slippage-report` writes replay cross-check
records and a replay-slippage summary under `artifacts/validation/`.

## Local website

```bash
npm --prefix webapp install
npm --prefix webapp run build
uv run tradingx web --env-file .env
```

By default the site binds to `127.0.0.1:8765`, serves a local-only
dashboard, and keeps all write actions disabled. Set
`TRADINGX_WEB_WRITE_MODE_ENABLED=true` in `.env` if you explicitly want
the local controls enabled. The website exposes:

- an operations deck for bounded paper actions and service control
- an evidence browser for alerts, service cycles, and validation reports
- a gate cockpit for current gate states and recommendation counts
- a Gate 3 operations surface for readiness status, drill history,
  market-session checkpoints, replay-slippage divergence, automation
  history, recurring scheduler state, and promotion workflow actions
- a project-intelligence panel for state and handover context
- a proposal studio that writes safe config proposals under
  `config/proposals/`

## Repo gate

```bash
./scripts/validate
```

This runs index validation, Ruff, Black, strict mypy, unit tests,
contract tests, integration tests with coverage, frontend tests,
frontend build verification, and the real Alpaca paper smoke gate when
`.env` contains real paper credentials.
