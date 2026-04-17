# TradingX Development Guidelines

Auto-generated from active feature plans. Last updated: 2026-04-17

## Active Technologies

- Python 3.11
- Core trading libraries: `alpaca-py`, `python-dotenv`, `nautilus_trader`
- Quality tooling: `pytest`, `ruff`, `black`, `mypy`
- Operator and monitoring adapters: `python-telegram-bot`,
  `prometheus-client`

## Project Structure

```text
src/tradingx/
tests/
specs/001-paper-trading-bot/
docs/
```

## Commands

- `uv sync --all-groups`
- `./scripts/validate`
- `python3 scripts/check_index.py`
- `uv run pytest tests/smoke/test_alpaca_paper_roundtrip.py -rs`

## Code Style

- Use UTC datetimes for all internal timestamps.
- Use `Decimal` for money, prices, and quantities that touch orders.
- Keep live trading disabled unless explicit Gate 4 enablement work says
  otherwise.
- Follow TDD and strict typing for production code under `src/`.

## Recent Changes

- `001-paper-trading-bot`: promoted `SPEC-0001`, added `PLAN-0001`,
  `RESEARCH-0001`, `DATAMODEL-0001`, `QUICKSTART-0001`,
  `CONTRACT-0001`, `CONTRACT-0002`, `ADR-0009`, and `GATES-0001`.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
