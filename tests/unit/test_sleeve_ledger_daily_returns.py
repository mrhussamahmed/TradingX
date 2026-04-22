from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from tradingx.drift.sleeve_ledger import compute_modified_dietz_return
from tradingx.persistence import FilesystemArtifactStore
from tradingx.types import SleeveDailyAttributionRecord


def test_legacy_sleeve_daily_attribution_payload_deserializes_with_new_defaults(
    tmp_path,
) -> None:
    store = FilesystemArtifactStore(tmp_path)
    category_dir = tmp_path / "sleeve_daily_attribution"
    category_dir.mkdir(parents=True)
    payload = {
        "attribution_id": "attr-1",
        "sleeve_id": "trend-following-v1",
        "trading_day": "2026-04-21",
        "recorded_at_utc": datetime(2026, 4, 21, 20, 0, tzinfo=UTC).isoformat(),
        "starting_equity": "100000",
        "ending_equity": "100500",
        "daily_return": "0.005",
        "per_symbol_open_weight": [["SPY", "0.4"]],
        "per_symbol_close_weight": [["SPY", "0.42"]],
    }
    (category_dir / "trend-following-v1__2026-04-21.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    record = store.list_sleeve_daily_attribution_records(
        sleeve_id="trend-following-v1"
    )[0]

    assert record == SleeveDailyAttributionRecord(
        attribution_id="attr-1",
        sleeve_id="trend-following-v1",
        trading_day="2026-04-21",
        recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100500"),
        daily_return=Decimal("0.005"),
        per_symbol_open_weight=(("SPY", Decimal("0.4")),),
        per_symbol_close_weight=(("SPY", Decimal("0.42")),),
        realized_pnl=None,
        unrealized_pnl=None,
        cash_balance=None,
        calculation_mode=None,
        bootstrap_confidence=None,
        ledger_genesis_id=None,
    )


def test_extended_sleeve_daily_attribution_record_accepts_ledger_fields() -> None:
    record = SleeveDailyAttributionRecord(
        attribution_id="attr-1",
        sleeve_id="trend-following-v1",
        trading_day="2026-04-21",
        recorded_at_utc=datetime(2026, 4, 21, 20, 0, tzinfo=UTC),
        starting_equity=Decimal("100000"),
        ending_equity=Decimal("100500"),
        daily_return=Decimal("0.005"),
        per_symbol_open_weight=(("SPY", Decimal("0.4")),),
        per_symbol_close_weight=(("SPY", Decimal("0.42")),),
        realized_pnl=Decimal("250"),
        unrealized_pnl=Decimal("250"),
        cash_balance=Decimal("1000"),
        calculation_mode="sleeve_ledger_mark_to_market",
        bootstrap_confidence="high",
        ledger_genesis_id="genesis-1",
    )

    assert record.realized_pnl == Decimal("250")
    assert record.unrealized_pnl == Decimal("250")
    assert record.cash_balance == Decimal("1000")
    assert record.calculation_mode == "sleeve_ledger_mark_to_market"
    assert record.bootstrap_confidence == "high"
    assert record.ledger_genesis_id == "genesis-1"


def test_modified_dietz_weights_signed_flows_individually() -> None:
    opened = datetime(2026, 4, 22, 13, 30, tzinfo=UTC)
    midday = datetime(2026, 4, 22, 15, 30, tzinfo=UTC)
    late = datetime(2026, 4, 22, 18, 30, tzinfo=UTC)
    closed = datetime(2026, 4, 22, 20, 0, tzinfo=UTC)

    weighted = compute_modified_dietz_return(
        opening_equity=Decimal("100"),
        closing_equity=Decimal("108"),
        cash_flows=((midday, Decimal("10")), (late, Decimal("-8"))),
        session_open_utc=opened,
        session_close_utc=closed,
    )
    netted = compute_modified_dietz_return(
        opening_equity=Decimal("100"),
        closing_equity=Decimal("108"),
        cash_flows=((midday, Decimal("2")),),
        session_open_utc=opened,
        session_close_utc=closed,
    )

    assert weighted != netted
