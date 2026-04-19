# Runtime Log Rotation Audit

## Finding

Review item `M6` questioned whether log rotation has a rotate-then-write race
if multiple writers share one JSONL file.

## Audit

- Runtime logs are partitioned by explicit component names:
  `service`, `controller`, `supervisor`, and `telegram`.
- `build_default_runtime_logger()` writes each component to its own file under
  `data/logs/<component>.jsonl`.
- Current production code does not configure two processes to write the same
  component log file concurrently.

## Decision

No code change in this wave. There is no verified shared-file writer in the
current process topology, so adding file locking around rotation would be
preventive hardening, not a response to an active defect.

## Follow-up

Re-open this item if a future process model introduces shared component names
across multiple writers.
