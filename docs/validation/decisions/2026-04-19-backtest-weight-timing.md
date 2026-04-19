# Backtest Weight Timing Decision

## Question

Review item `H5` asked whether `run_daily_bar_backtest()` was correct to apply
`target_weights.iloc[t-1]` at day `t` open.

## Evidence

Two analytical toy paths were checked against the engine:

1. `open=[100,110,121]`, `close=[110,121,121]`,
   `target_weights=[0,1,1]`
   A trader who can act on day 2's open should earn the day-2 intraday
   return of `10%`.
2. The same bars with `target_weights=[1,1,1]`
   A fully-invested path should compound to `1.21`, or `21%`.

Under the stale-weight implementation both cases lagged by one bar and missed
the actionable open.

## Decision

`target_weights.iloc[t]` is the weight scheduled for day `t` open.

The backtest engine now:

- accrues overnight return on the prior holdings,
- rebalances into `target_weights.iloc[t]` at that day’s open, and
- accrues intraday return on the post-open holdings.

## Consequence

Backtest and gate evidence produced before this fix were computed under
stale-weight semantics and should not be compared directly with post-fix
results without noting the change.
