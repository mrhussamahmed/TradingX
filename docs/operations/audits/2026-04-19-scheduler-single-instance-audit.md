# Scheduler Single-Instance Audit

## Finding

Review item `M3` questioned whether `MarketDayScheduler` could double-launch
because its durable schedule record is a check-then-act filesystem write.

## Audit

- The CLI entrypoint `run-market-scheduler` already runs inside
  `runtime_process_lock()` in `/Users/ahmedabd/Desktop/AI Projects/TradingX/src/tradingx/__main__.py`.
- The supervised child scheduler is spawned only from the operator
  supervisor, which already owns the same runtime lock.
- No second production path launches a scheduler outside that lock in the
  current repo topology.

## Decision

No code change in this wave. The single-instance invariant currently holds in
the supported execution paths, so adding a second lock at the scheduler layer
would be redundant hardening rather than a correctness fix.

## Follow-up

If a future direct scheduler entrypoint is added outside the locked CLI /
supervisor paths, the scheduler should acquire its own per-day or runtime
lock before launch.
