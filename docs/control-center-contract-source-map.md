# Control Center Contract Source Map

Date: 2026-04-29

This document is the implementation guardrail for the Control Center UI and
readmodel contracts. A displayed operational value must identify its source,
freshness timestamp, missing-data behavior, and whether it is authoritative or
derived. Missing numeric values must be represented as `null` plus an explicit
status, never as `"n/a"`, `""`, `$0`, or an equal-allocation placeholder.

## Status Vocabulary

- `fresh`: source-backed value with current source evidence.
- `stale`: source-backed value exists, but its source timestamp is older than
  the accepted freshness window.
- `unpriced`: position exists, but latest price or market value evidence is
  missing.
- `source_missing`: required source artifact or backend field is absent.
- `unknown`: backend cannot determine the value or source.
- `unavailable`: the feature/data path is not available for the selected scope.
- `partial`: enough data exists to render context, but not enough for a complete
  operational claim.

## Portfolio And Exposure

| Field | Source | Authority | Freshness | Missing Behavior |
| --- | --- | --- | --- | --- |
| `positions_panel.positions[].symbol` | Latest account/reconciliation portfolio state; legacy fallback may use service-cycle `open_position_symbols` | Source-backed when portfolio state contains full positions; symbol-only fallback is partial | Portfolio state `as_of_utc` or service cycle `completed_at_utc` | Omit row if no position symbol exists |
| `positions_panel.positions[].quantity` | `PortfolioState.positions[].quantity` | Source-backed | Portfolio state `as_of_utc` | `null` with `quantity_status="source_missing"` |
| `positions_panel.positions[].average_entry_price` | `PositionSnapshot.average_entry_price` | Source-backed | Portfolio state `as_of_utc` | `null` with `price_status="source_missing"` |
| `positions_panel.positions[].market_value` | `PositionSnapshot.market_value` | Source-backed broker/account mark | Portfolio state `as_of_utc` | `null` with `price_status="unpriced"` |
| `positions_panel.positions[].exposure_pct` | `abs(market_value) / equity * 100` | Derived from source-backed money values | Minimum of portfolio state/equity timestamps | `null` with `exposure_status="source_missing"` |
| `commandCenter.exposure_breakdown` | Deprecated compatibility field | Not authoritative unless backed by market values | Same as portfolio source | Empty only when no positions exist; when positions exist but values are missing, emit `value=null` plus `value_status="unpriced"` or `value_status="source_missing"` and a missing reason |
| Future risk allocation/exposure | Portfolio positions plus sleeve ledger/blueprint bindings | Derived | Minimum source timestamp used in calculation | Empty/card unavailable with explicit missing reason |

## Timeline And Replay

Existing endpoints remain compatibility contracts:

- `/api/platform/timeline`
- `/api/platform/replay`

New timeline work must use additive `/api/platform/session-timeline`.

| Field | Source | Authority | Freshness | Missing Behavior |
| --- | --- | --- | --- | --- |
| `OperatorTimelineEvent.occurred_at_utc` | Event artifact timestamp | Source-backed instant timestamp when artifact timestamp exists | Event timestamp | Event may be omitted if no defensible timestamp exists |
| `SessionTimelineEvent.shape="instant"` | Existing point event | Authoritative point event | Event timestamp | Default for legacy events |
| `SessionTimelineEvent.shape="span"` | Source artifact containing both start and end timestamps | Authoritative only when both endpoints are source-backed | Minimum endpoint/source timestamp | MUST NOT be emitted unless both endpoints are source-backed; otherwise emit `shape="instant"` or a partial event with null span endpoints. Any estimated range is presentation-only and must not enter the backend contract as a span |
| `SessionTimelineEvent.started_at_utc` | Source-specific start timestamp | Source-backed for spans | Source timestamp | `null` unless authoritative |
| `SessionTimelineEvent.ended_at_utc` | Source-specific end timestamp | Source-backed for spans | Source timestamp | `null` unless authoritative |
| Session open/close bounds | Persisted market-day schedule/session metadata | Source-backed for new records | Schedule/session record timestamp | `session.status="partial"` when historical records lack close time; do not infer close |
| `available_trading_days` | Real artifact/schedule dates | Derived list from source records | Latest source scan time | Empty list if no dated source records exist |

## Runtime Cadence

Cadence configuration is a separate runtime-control contract. UI must not imply a
running loop changed cadence unless the runtime confirms it.

| Field | Source | Meaning |
| --- | --- | --- |
| `configured_cadence_seconds` | Persisted operator override, falling back to env config | Nullable decimal/integer seconds for future starts/manual heartbeats |
| `configured_cadence_status` | Cadence settings read path | `fresh`, `source_missing`, `unknown`, or `unavailable` |
| `configured_cadence_source` | Cadence settings read path | `operator_override` or `env_config`; never `running_state` |
| `running_cadence_seconds` | Active service/runtime/scheduler state | Nullable decimal/integer seconds currently confirmed by a running loop |
| `running_cadence_status` | Runtime/scheduler state read path | `fresh` only when active runtime confirms the cadence; otherwise `unavailable`, `source_missing`, or `unknown` |
| `running_cadence_source` | Runtime/scheduler state read path | `runtime_state`, `scheduler_state`, or `service_state` |
| `applies_at` | Cadence reconciliation logic | `next_start`, `next_tick`, or `running_now`; `running_now` is allowed only when `running_cadence_status="fresh"` and the active runtime confirms the value |

## Strategy Attribution

| Field | Source | Authority | Freshness | Missing Behavior |
| --- | --- | --- | --- | --- |
| Active sleeve bindings | Active blueprint activation bindings | Source-backed | Blueprint approval/activation timestamp | Show single active binding, multiple bindings, or unavailable state |
| Attribution P&L/date | Sleeve daily attribution records | Source-backed when record exists | `recorded_at_utc` and `trading_day` | `null` plus unavailable/partial status; do not use UI render timestamp |
| Position count/exposure by sleeve | Sleeve position ledger snapshots or decomposition records | Source-backed/derived depending on source | Snapshot `recorded_at_utc` | `null` plus source status |

## Review Rules

1. Missing numeric values must be `null` plus status.
2. Formatted display strings are not primary data contracts.
3. Equal allocation values are allowed only when calculated from real market
   values that happen to be equal.
4. Fresh frontend render timestamps must not substitute for source evidence
   freshness.
5. Existing timeline/replay endpoints stay stable until their consumers migrate.
