## ADDED Requirements

### Requirement: Safety controls have regression tests
Critical safety boundaries SHALL have automated tests that fail if live trading
opens accidentally, write authorization weakens, or duplicate paper submission
risk increases.

#### Scenario: Live boundary test suite runs
- **WHEN** safety-related unit, contract, or integration tests run
- **THEN** they verify live trading remains disabled unless Gate 4 controls are
  explicitly satisfied

### Requirement: Verification commands are reproducible
Audit verification SHALL use documented repo commands and record exact results.

#### Scenario: Validation command fails
- **WHEN** a documented validation command fails
- **THEN** the failure is recorded with scope, likely cause, and follow-up test
  recommendations

### Requirement: UI tests cover authorization states
Frontend tests SHALL cover disabled write mode, missing signing secret, invalid
signature, loading, error, and duplicate-action states where relevant.

#### Scenario: Write controls render disabled
- **WHEN** API status reports write actions unavailable
- **THEN** frontend tests verify unsafe controls cannot be activated from the UI
