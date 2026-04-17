---
id: QUICKSTART-0001
title: TradingX Stage 1 planning quickstart
version: 1.0.0
status: active
created: 2026-04-17
last_amended: 2026-04-17
supersedes: null
superseded_by: null
author_session: SESS-2026-04-17-004
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

## 3. Run the repo gate

```bash
./scripts/validate
```

This runs index validation, Ruff, Black, strict mypy, unit and
integration tests, and the Alpaca paper smoke gate when real paper
credentials are present.

## 4. Run the paper round trip directly

```bash
uv run pytest tests/smoke/test_alpaca_paper_roundtrip.py -rs
```

Expected behavior:

- With placeholder or missing paper credentials, the test skips with a
  clear message.
- With real paper credentials, the test executes a real Alpaca paper
  round trip and writes evidence under `artifacts/smoke/`.

## 5. Inspect the current implementation boundary

- `src/tradingx/controller.py` orchestrates the round trip.
- `src/tradingx/risk.py` enforces paper-only risk gates.
- `src/tradingx/data.py`, `execution.py`, and `portfolio.py` wrap Alpaca.
- `docs/validation/acceptance_gates.md` defines the evidence needed for
  later phase advancement.

## 6. Next step after this plan

Generate implementation tasks from `PLAN-0001`, then execute them under
TDD while keeping `SPEC-0001`, `ADR-0009`, and `GATES-0001` as the
authoritative planning references.
