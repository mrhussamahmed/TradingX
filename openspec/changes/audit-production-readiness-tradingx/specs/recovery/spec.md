## ADDED Requirements

### Requirement: Recovery reconciles before action
Recovery flows SHALL inspect persisted paper state before taking any new
broker-facing paper action.

#### Scenario: Recovery follows interrupted cycle
- **WHEN** an interrupted paper cycle is recovered
- **THEN** TradingX reconciles state before deciding whether a new paper action
  is needed

### Requirement: Drills produce reviewable artifacts
Recovery and alert drills SHALL persist artifacts with a stable schema that
documents the drill id, command inputs, start and completion timestamps, status,
outcome, sanitized failure reason, evidence references, and retention path.

#### Scenario: Drill command runs
- **WHEN** `recovery-drill` or `alert-drill` runs safely
- **THEN** it writes a reviewable retained artifact without exposing secrets

#### Scenario: Drill dependency is unavailable
- **WHEN** a drill cannot complete because broker, SMTP, Telegram, or evidence
  dependencies are unavailable
- **THEN** the artifact records `pending`, `not_configured`, or `failed` with a
  sanitized reason and does not mark the drill as passing

### Requirement: Hard stops fail closed
Kill, halt, and stop controls SHALL transition the runtime to a state that
prevents new paper submissions and preserves enough state for later recovery.

#### Scenario: Kill request is observed
- **WHEN** an operator kill request is issued
- **THEN** new submissions stop and persistent state records the request
