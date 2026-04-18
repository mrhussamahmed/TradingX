---
id: DATAMODEL-0005
title: TradingX replay-slippage evidence data model
version: 1.0.0
status: active
created: 2026-04-18
last_amended: 2026-04-18
supersedes: null
superseded_by: null
author_session: SESS-2026-04-18-017
---

# Data Model: TradingX replay-slippage evidence

## Execution lifecycle additions

Existing execution-lifecycle records gain these fields:

- `bid_price`
- `ask_price`
- `average_daily_volume_30d`

These fields are required for newly written execution artifacts. Older
artifacts may omit them and will not support replay generation.

## Replay Slippage Record

- `replay_id`
- `execution_id`
- `intent_id`
- `symbol`
- `side`
- `filled_qty`
- `reference_price`
- `paper_fill_price`
- `paper_slippage_bps`
- `simulated_fill_price`
- `simulated_slippage_bps`
- `divergence_ratio`
- `quoted_spread_bps`
- `participation_rate`
- `generated_at_utc`

## Replay Slippage Summary

- `summary_id`
- `matched_execution_count`
- `paper_mean_absolute_slippage_bps`
- `replay_mean_absolute_slippage_bps`
- `divergence_ratio`
- `status`
- `details`
- `generated_at_utc`

## Replay Generation Result

- `status`
- `matched_execution_count`
- `record_paths`
- `summary_path`
- `summary`
