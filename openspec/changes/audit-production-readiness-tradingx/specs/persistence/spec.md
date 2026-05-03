## ADDED Requirements

### Requirement: Legacy local mode remains default
TradingX SHALL continue operating with local artifact and data directories when
Postgres is not configured.

#### Scenario: Postgres DSN is absent
- **WHEN** the app starts without Postgres configuration
- **THEN** local persistence paths remain usable and no Postgres connection is
  required

### Requirement: Optional Postgres checks are gated
Postgres integration checks SHALL run only against explicitly configured test
databases.

#### Scenario: Test DSN is absent
- **WHEN** Postgres integration tests require `TRADINGX_TEST_POSTGRES_DSN`
- **THEN** they are skipped or marked not verified rather than connecting to an
  unintended database

### Requirement: Persistence protects evidence ordering
Persistence layers SHALL preserve enough ordering, identifiers, and checksums to
detect sequence gaps or stale/corrupt evidence where required by gate review.

#### Scenario: Evidence ledger has a gap
- **WHEN** validation reads a ledger with missing or stale records
- **THEN** it rejects or flags the evidence rather than treating it as complete
