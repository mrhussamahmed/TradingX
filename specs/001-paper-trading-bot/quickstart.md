---
id: QUICKSTART-0001
title: TradingX Stage 1 planning quickstart
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-006
---

# Quickstart

## 1. Prepare the environment

1. Use Python 3.11 in the repository root.
2. Keep live Alpaca credentials absent or blank; Stage 1 remains paper-
   only.
3. Fill `.env` with real `ALPACA_PAPER_API_KEY` and
   `ALPACA_PAPER_API_SECRET` only when you intend to run the smoke test.

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
  secrets.
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
  flow, and evaluation pipeline.
- `src/tradingx/risk.py` enforces paper-only risk gates and auditable
  block decisions.
- `src/tradingx/strategy.py` contains the live paper-loop baseline and
  the mandatory evaluation candidate registry.
- `src/tradingx/evaluation.py` and `src/tradingx/alerts.py` produce the
  offline evidence and operator-facing alert payloads.
- `docs/validation/acceptance_gates.md` defines the evidence needed for
  later phase advancement.

## 8. Operator paper-loop commands

```bash
uv run tradingx paper-loop --env-file .env --symbol SPY --quantity 1
uv run tradingx paper-recover --env-file .env --symbol SPY
```

Expected behavior:

- `paper-loop` runs one regular-hours paper cycle and writes artifacts to
  `artifacts/paper_loop/`.
- `paper-recover` resumes the latest persisted cycle for the symbol
  without creating a duplicate paper submission.

## 9. Quickstart verification status

This quickstart was exercised on 2026-04-17 with:

- `uv run tradingx config-summary --env-file .env`
- `uv run tradingx live-disable-status --env-file .env`
- `./scripts/validate`

Those runs passed in this session, including the real Alpaca paper smoke
gate.
