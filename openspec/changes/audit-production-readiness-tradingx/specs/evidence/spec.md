## ADDED Requirements

### Requirement: Evidence artifacts are trustworthy
TradingX SHALL generate evidence artifacts with enough metadata to support
later gate review and replay.

#### Scenario: Gate evidence is generated
- **WHEN** validation, replay, recovery, or Gate 3 reports are written
- **THEN** the artifacts include source paths, timestamps, inputs, and status
  indicators needed for review

### Requirement: Failed or skipped checks are explicit
Audit reports SHALL distinguish passed, failed, skipped, and not-verified
checks.

#### Scenario: Credentials are unavailable
- **WHEN** a broker, SMTP, Telegram, Postgres, or market-hours check cannot run
- **THEN** the report marks it `not verified` with the reason

### Requirement: Evidence paths are stable
TradingX SHALL write evidence under documented artifact roots and avoid silent
path drift.

#### Scenario: Operator reviews artifacts
- **WHEN** evidence-report or gate-report output references files
- **THEN** the files exist at the documented paths or the missing-path failure
  is explicit
