# 2026-04-19 Audit Remediation Wave 2

## Purpose

Capture the agreed follow-up work from the 2026-04-19 main-branch audit so
the repo has one reviewable plan tying each code change back to a specific
finding.

## Implemented task list

- `C5` — make `TradingConfig.from_env_file()` merge dotenv values with
  `os.environ`, with shell environment values winning.
- `C2` + `C3` — harden `MultiprocessingChildHandle` so terminate escalates to
  kill and both paths raise if the child survives.
- `C4` — move supervisor flatten execution off the command loop and return an
  accepted status immediately.
- `H1` — serialize `Decimal` journal payload values before durable writes.
- `H2` + `H3` — convert JSON artifact and decision-snapshot writes to
  temp-file plus `fsync` plus `os.replace`.
- `H4` — log alert transport failures and fail closed for undelivered
  critical alerts.
- `H6` — switch `decimal_stddev()` to sample standard deviation so warmup
  volatility matches the rest of the repo.
- `M4` — persist sticky drawdown halts to disk and reload them across policy
  engine instances.
- `M7` — make web read-model datetime parsing tolerant of malformed ISO
  strings.
- `L1`, `L2`, `L3`, `L4` — tighten low-severity correctness:
  required STARTTLS, SPA fallback no longer echoes the requested path,
  timezone-aware weight timestamps are enforced, and risk-free daily rates
  use compounding instead of simple `/252`.

## Verify-then-decide items

- `M3` — scheduler single-instance enforcement
- `M6` — runtime log rotation concurrency
- `M8` — journal single-writer / timeout discipline

The conclusions for those items live in `docs/operations/audits/`.

## Spec-dependent items

- `H5` — backtest target-weight timing semantics
- `L5` — whether insufficient data should report `pending` or `fail`

The decisions for those items live in `docs/validation/decisions/`.
