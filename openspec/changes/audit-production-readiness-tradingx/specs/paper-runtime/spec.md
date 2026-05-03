## ADDED Requirements

### Requirement: Paper cycles are bounded by default in audit
Paper runtime audit checks SHALL use explicit symbols, quantities, intervals,
and cycle limits.

#### Scenario: Manual cycle is audited
- **WHEN** a manual `SPY` cycle is exercised during the audit
- **THEN** the command is bounded, paper-only, and stops without requiring
  operator interruption

### Requirement: Duplicate paper submissions are prevented
TradingX SHALL prevent recovery, retries, restarts, or double-clicks from
creating duplicate paper submissions for the same intended action.

#### Scenario: Recovery reruns the latest cycle
- **WHEN** `paper-recover` is invoked for a previously persisted cycle
- **THEN** the system reconciles state and avoids duplicate paper submission

### Requirement: Paper automation is stoppable
Recurring paper automation SHALL expose a safe stop condition or operator stop
path.

#### Scenario: Recurring service is audited
- **WHEN** the service is run for `SPY,QQQ,IWM`
- **THEN** it uses a finite cycle limit or a verified stop path during audit
