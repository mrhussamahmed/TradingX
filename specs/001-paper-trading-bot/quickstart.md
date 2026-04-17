---
id: QUICKSTART-0001
title: TradingX Stage 1 planning quickstart
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-011
---

# Quickstart

## 1. Prepare the environment

1. Use Python 3.11 in the repository root.
2. Keep live Alpaca credentials absent or blank; Stage 1 remains paper-
   only.
3. Fill `.env` with real `ALPACA_PAPER_API_KEY` and
   `ALPACA_PAPER_API_SECRET` only when you intend to run the smoke test.
4. Add `TRADINGX_TELEGRAM_*` and `TRADINGX_SMTP_*` settings only if you
   want real operator delivery; otherwise alerts still persist locally.

## 2. Install dependencies

```bash
uv sync --all-groups
```

## 3. Inspect the safe runtime status

```bash
uv run tradingx config-summary --env-file .env
uv run tradingx live-disable-status --env-file .env
```

Expected behavior:

- `config-summary` reports safe runtime settings without printing any
  secrets, including the configured service interval, symbol universe,
  and whether real alert transports are enabled.
- `live-disable-status` confirms paper-only mode and whether the manual
  kill switch is active.

## 4. Run the repo gate

```bash
./scripts/validate
```

This runs index validation, Ruff, Black, strict mypy, unit and
contract/integration tests, and the Alpaca paper smoke gate when real
paper credentials are present.

## 5. Review local evidence artifacts

```bash
uv run tradingx evidence-report --artifact-root artifacts/paper_loop
```

Expected behavior:

- The command prints category counts plus the most recent artifact name
  for each evidence bucket.
- The summary section reports blocked-trade totals, the latest open
  positions, the latest cash/equity snapshot, daily paper PnL, and
  evaluation recommendation counts.
- When gate reports exist, the summary also includes the latest status
  seen for each gate assessment.

## 6. Run the paper round trip directly

```bash
uv run pytest tests/smoke/test_alpaca_paper_roundtrip.py -rs
```

Expected behavior:

- With placeholder or missing paper credentials, the test skips with a
  clear message.
- With real paper credentials, the test executes a real Alpaca paper
  round trip and writes evidence under `artifacts/smoke/`.

## 7. Inspect the current implementation boundary

- `src/tradingx/controller.py` orchestrates the paper loop, recovery
  flow, evaluation pipeline, and gate-report generation.
- `src/tradingx/risk.py` enforces paper-only risk gates and auditable
  block decisions.
- `src/tradingx/strategy.py` contains the live paper-loop baseline and
  the mandatory evaluation candidate registry.
- `src/tradingx/evaluation.py`, `src/tradingx/validation.py`, and
  `src/tradingx/alerts.py` produce the offline evidence and operator-
  facing alert payloads.
- `docs/validation/acceptance_gates.md` defines the evidence needed for
  later phase advancement.

## 8. Operator paper-loop commands

```bash
uv run tradingx paper-loop --env-file .env --symbol SPY --quantity 1
uv run tradingx run-paper-service --env-file .env --symbols SPY,QQQ,IWM --quantity 1 --interval-seconds 300 --max-cycles 1
uv run tradingx paper-recover --env-file .env --symbol SPY
```

Expected behavior:

- `paper-loop` runs one regular-hours paper cycle and writes artifacts to
  `artifacts/paper_loop/`.
- `run-paper-service` repeats the paper loop on a cadence, scans the
  bounded symbol universe sequentially, and writes a service-cycle
  summary under `artifacts/paper_loop/service_cycles/`.
- Existing positions now exit deterministically when the baseline sees an
  approximately 1% take-profit or 1% stop-loss threshold.
- `paper-recover` resumes the latest persisted cycle for the symbol
  without creating a duplicate paper submission.

## 9. Generate Gate 1 or Gate 2 validation reports

Prepare a dividend-adjusted benchmark close-series artifact first:

```bash
uv run tradingx prepare-benchmark-closes --env-file .env --window-start 2023-01-01 --window-end 2026-04-17
```

By default this writes:

```text
artifacts/validation/benchmarks/spy-2023-01-01-2026-04-17-dividend.json
```

The prepared artifact includes the symbol, requested window, data feed,
adjustment mode, adjustment flag, and the close series. `gate-report`
will infer the dividend-adjusted status from that artifact and reject a
window mismatch. The legacy fallback format is still accepted as a JSON
array of close prices:

```json
["100", "101.25", "102.10"]
```

Then run a report command:

```bash
uv run tradingx gate-report --env-file .env --gate 1 --benchmark-closes-file artifacts/validation/benchmarks/spy-2023-01-01-2026-04-17-dividend.json --window-start 2023-01-01 --window-end 2026-04-17
uv run tradingx gate-report --env-file .env --gate 2 --benchmark-closes-file artifacts/validation/benchmarks/spy-2023-01-01-2026-04-17-dividend.json --window-start 2023-01-01 --window-end 2026-04-17
```

Expected behavior:

- The command writes candidate evaluation evidence, a validation report,
  and a gate assessment under `artifacts/validation/`.
- Gate 1 reports the benchmark edge, drawdown, Calmar, out-of-sample
  profile, and benchmark-adjustment criteria for each mandatory
  candidate.
- Gate 2 reports the 2x cost stress, parameter-perturbation, and
  rolling walk-forward criteria for each mandatory candidate.

## 10. Quickstart verification status

This quickstart was exercised on 2026-04-17 with:

- `uv run tradingx config-summary --env-file .env`
- `uv run tradingx live-disable-status --env-file .env`
- `uv run tradingx prepare-benchmark-closes --env-file .env --window-start 2023-01-01 --window-end 2026-04-17 --output-file <fixture>`
- `uv run tradingx gate-report --gate 1 --benchmark-closes-file <fixture> --window-start 2023-01-01 --window-end 2026-04-17`
- `uv run pytest`
- `./scripts/validate`

Those runs passed in this session. Because regular US market hours were
closed, the smoke gate skipped with an explicit closed-market message.
