## ADDED Requirements

### Requirement: Live trading remains fail-closed
TradingX SHALL keep live trading disabled unless every documented Gate 4
control is explicitly satisfied and locally authorized.

#### Scenario: Live controls are absent
- **WHEN** the operator runs safety-status commands without Gate 4 sign-off
- **THEN** the system reports live trading disabled and blocks live broker
  submission paths

#### Scenario: Live mode is requested accidentally
- **WHEN** configuration requests live broker mode without the full live
  enablement chain
- **THEN** startup or order routing fails closed before any live submission can
  occur

### Requirement: Paper mode is the only audit execution target
TradingX SHALL limit audit-run execution to paper, dry-run, mocked, bounded, or
read-only paths.

#### Scenario: Audit reaches an order path
- **WHEN** a reviewed flow can reach broker submission
- **THEN** the flow is verified as paper-only, dry-run, mocked, or blocked

### Requirement: Secrets are redacted from evidence
TradingX SHALL avoid printing credential values in logs, reports, screenshots,
test output, and OpenSpec artifacts.

#### Scenario: Config evidence is generated
- **WHEN** config summaries, runtime logs, reports, or failures mention
  credential fields
- **THEN** only presence, absence, or redacted values are visible
