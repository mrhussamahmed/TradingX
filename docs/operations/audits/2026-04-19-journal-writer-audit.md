# Journal Writer Invariant Audit

## Finding

Review item `M8` questioned whether the SQLite journal should use a longer
timeout and a long-lived connection because multiple components might write to
`journal.db`.

## Audit

- `SqliteOmsJournal` already enables WAL mode on initialization.
- Controller code is the only production writer calling `append_event()`.
- Other journal consumers in the current repo use read paths such as
  `list_events()` or `build_today_summary()`.
- The runtime lock prevents multiple supported trading processes from owning
  the same data root concurrently.

## Decision

No timeout or connection-lifetime change in this wave. Under the current
single-writer invariant, the default connection pattern is acceptable and a
larger refactor would not address a proven production issue.

## Follow-up

If the repo later introduces concurrent journal writers, raise the SQLite
timeout and hold one connection per journal instance before that topology
ships.
