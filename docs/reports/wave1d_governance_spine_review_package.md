# Wave 1D Review Package - Activation, Order Guard, Web Labeling, Drift

Roadmap slice: Wave 1D.

Files in scope:

- `src/tradingx/activation.py`
- `src/tradingx/execution.py`
- `src/tradingx/portfolio/live_construction.py`
- `src/tradingx/web/readmodels.py`
- `tests/integration/test_promotion_activation.py`
- `tests/unit/test_execution_authority.py`
- `tests/unit/test_portfolio_live_construction.py`
- `tests/unit/test_web_readmodels.py`
- `tests/unit/test_promotion.py`

Implemented evidence:

- `LocalActivationGateway` can refuse activation when a configured promotion decision is capped below the requested runtime state.
- Activation checks projection drift under `config/strategy/promotion/<strategy_id>.json` when a projection root is configured.
- Default local activation remains legacy-compatible when no V5 promotion policy is configured.
- `OrderRouteAuthorityGuard` denies order-capable routes below the required promotion state; direct paper gateways expose `v5_order_authorized == False` and fail `assert_v5_order_authority`.
- Portfolio cycle construction rejects negative sleeve targets before aggregation can drop or normalize the unsupported side.
- Local web read models label current document-derived authority as `legacy_non_authority`.

Validation evidence:

- `uv run pytest tests/integration/test_promotion_activation.py tests/unit/test_execution_authority.py tests/unit/test_portfolio_live_construction.py tests/unit/test_web_readmodels.py::test_local_web_read_model_builds_dashboard_from_artifacts_and_docs tests/unit/test_promotion.py`
- `uv run ruff check .`
- `uv run mypy src/tradingx`

