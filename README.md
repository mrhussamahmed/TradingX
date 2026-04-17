# TradingX

TradingX is a paper-only US equities trading bot built with a strict
evidence-first workflow. The current branch contains a working Stage 1
implementation that can:

- run a deterministic paper trading loop with auditable risk decisions
- recover and reconcile without duplicate paper submissions
- evaluate the three mandatory baseline strategy families against SPY
- emit bounded operator alerts and evidence reports while live trading
  stays disabled

## Core commands

```bash
uv run tradingx config-summary --env-file .env
uv run tradingx live-disable-status --env-file .env
uv run tradingx evidence-report --artifact-root artifacts/paper_loop
uv run tradingx paper-loop --env-file .env --symbol SPY --quantity 1
uv run tradingx paper-recover --env-file .env --symbol SPY
```

`paper-loop` is intended for regular US market hours and paper mode
only. `paper-recover` resumes the latest persisted loop for a symbol
without creating a duplicate submission.

## Repo gate

```bash
./scripts/validate
```

This runs index validation, Ruff, Black, strict mypy, unit tests,
contract tests, integration tests with coverage, and the real Alpaca
paper smoke gate when `.env` contains real paper credentials.
