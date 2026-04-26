# Wave 1B Review Package - Ledger, Signatures, Trust Roots

Roadmap slice: Wave 1B.

Files in scope:

- `src/tradingx/authority.py`
- `schemas/quant/trust_root.schema.json`
- `tests/unit/test_authority.py`
- `tests/fixtures/promotion/sequence_gap/`
- `tests/fixtures/promotion/unsigned_approval/`

Implemented evidence:

- `AuthorityLedger` appends JSONL authority records outside the OMS journal.
- Ledger append takes an exclusive file lock, rereads the tail under lock, verifies sequence, previous hash, payload hash, artifact refs, approval refs, replay refs, and fsyncs committed records and directory state.
- Ledger reader fails closed on corrupt records, sequence gaps, previous-hash mismatches, payload-hash mismatches, and missing refs.
- `TrustRoot` carries key scopes, revoked keys, validity bounds, and fixture-root status.
- `verify_approval_signature` rejects placeholder, malformed, revoked, unknown-key, wrong-scope, expired, wrong-digest, and fixture signatures under non-fixture trust roots.

Validation evidence:

- `uv run pytest tests/unit/test_authority.py`
- `uv run ruff check .`
- `uv run mypy src/tradingx`

