## ADDED Requirements

### Requirement: Control Center is local-first
The Control Center SHALL bind to local interfaces by default and expose safe
read-only behavior unless write controls are explicitly enabled.

#### Scenario: Default web startup
- **WHEN** the web backend starts with default configuration
- **THEN** read views are available locally and write actions remain disabled

### Requirement: Frontend cannot bypass backend safety
The Control Center frontend SHALL treat backend authorization and safety checks
as authoritative for every control action.

#### Scenario: A write button is forced client-side
- **WHEN** a user manipulates the frontend to call a write endpoint directly
- **THEN** the backend still rejects the request unless local write mode,
  signing, idempotency, and action-specific validation pass

### Requirement: Runtime host controls expose stop state
The Control Center SHALL make runtime start, stop, loading, error, and stopped
states observable to the operator.

#### Scenario: Runtime stop is requested
- **WHEN** the operator stops the supervised paper runtime from the UI
- **THEN** the UI reflects the stop request and the backend transitions the
  runtime toward a non-running state
