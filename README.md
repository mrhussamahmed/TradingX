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

## Core commands

```bash
uv run tradingx config-summary --env-file .env
uv run tradingx live-disable-status --env-file .env
uv run tradingx paper-loop --env-file .env --symbol SPY --quantity 1
uv run tradingx run-paper-service --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --max-cycles 1
uv run tradingx paper-recover --env-file .env --symbol SPY
uv run tradingx evidence-report --artifact-root artifacts/paper_loop
uv run tradingx gate-report --env-file .env --gate 1 --benchmark-closes-file benchmark-closes.json --window-start 2023-01-01 --window-end 2026-04-17 --benchmark-adjusted
```

`paper-loop` is intended for regular US market hours and paper mode
only. `run-paper-service` repeats the loop across a bounded universe and
persists a service-cycle summary on every pass; omit `--max-cycles` to
leave it running. `paper-recover` resumes the latest persisted loop for
a symbol without creating a duplicate submission.

If `TRADINGX_TELEGRAM_BOT_TOKEN` / `TRADINGX_TELEGRAM_CHAT_ID` or the
`TRADINGX_SMTP_*` settings are present in `.env`, operator alerts are
delivered through those transports in addition to being persisted under
`artifacts/paper_loop/operator_alerts/`.

`gate-report` writes validation artifacts under `artifacts/validation/`.
The benchmark closes file may be a JSON array like `["100","101.5"]`
or a simple comma/newline-delimited list of close prices. Pass
`--benchmark-adjusted` only when the input series is already
dividend-adjusted.

## Repo gate

```bash
./scripts/validate
```

This runs index validation, Ruff, Black, strict mypy, unit tests,
contract tests, integration tests with coverage, and the real Alpaca
paper smoke gate when `.env` contains real paper credentials.
