## ADDED Requirements

### Requirement: Gate status is evidence-backed
Gate reports SHALL state whether requirements are satisfied using available
validation and paper evidence.

#### Scenario: Gate 3 evidence is insufficient
- **WHEN** the required duration or closed-trade count is not met
- **THEN** Gate 3 readiness reports block promotion or mark readiness
  insufficient

### Requirement: Gate 4 remains unavailable without durable approval evidence
Gate 4 live enablement SHALL remain blocked unless explicit operator
acknowledgements, schema-valid durable signed approval evidence, checklist
evidence references, and all prerequisite controls are satisfied.

#### Scenario: Gate 4 checks run during audit
- **WHEN** live-disable or live-enable status is inspected
- **THEN** the audit confirms live trading is disabled unless durable approval
  evidence is closed-world schema-valid, unexpired, signed, and checklist-backed

### Requirement: Decision reports distinguish wait from promote
Decision reports SHALL clearly distinguish advance, wait for evidence, and
reject/change recommendations.

#### Scenario: Validation artifacts are incomplete
- **WHEN** decision-report runs without all required evidence
- **THEN** it recommends waiting or not verified rather than promotion
