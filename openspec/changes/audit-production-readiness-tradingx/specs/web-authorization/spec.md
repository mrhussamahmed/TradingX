## ADDED Requirements

### Requirement: Web write actions require local unlock and signing
The web backend SHALL reject write/control actions unless local write mode is
enabled and request signing is configured and valid.

#### Scenario: Write mode is disabled
- **WHEN** a client posts to a write endpoint without write mode enabled
- **THEN** the backend rejects the request without side effects

#### Scenario: Signing secret is missing
- **WHEN** write mode is enabled without a signing secret
- **THEN** the backend rejects write requests or refuses unsafe startup

### Requirement: Web write actions are idempotent
Write/control endpoints SHALL require idempotency or equivalent duplicate
prevention for state-changing actions.

#### Scenario: Duplicate request is sent
- **WHEN** the same signed write action is submitted twice
- **THEN** the backend returns a deterministic duplicate-safe result and avoids
  repeating the control action unsafely

### Requirement: Authorization failures are observable and safe
Authorization failures SHALL be visible to the operator without revealing
signing secrets or sensitive configuration.

#### Scenario: Invalid signature is supplied
- **WHEN** a write request has an invalid or expired signature
- **THEN** the response reports authorization failure and logs no secret values
