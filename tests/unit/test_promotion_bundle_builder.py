from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from tradingx.promotion import PromotionState, load_promotion_decision
from tradingx.promotion_bundle_builder import write_paper_trading_promotion_bundle


def test_promotion_bundle_builder_parameterizes_strategy_and_exact_cap(
    tmp_path: Path,
) -> None:
    template = Path("config/strategy/promotion/baseline-long-only-v1")
    root = tmp_path / "promotion"

    for strategy_id, cap in {
        "baseline-long-only-v1": Decimal("0.40"),
        "mean-reversion-v1": Decimal("0.20"),
        "trend-following-v1": Decimal("0.20"),
        "vol-target-v1": Decimal("0.20"),
    }.items():
        write_paper_trading_promotion_bundle(
            root / strategy_id,
            strategy_id=strategy_id,
            max_strategy_allocation=cap,
            template_bundle_root=template,
            target_weights={"SPY": cap},
        )

        decision = load_promotion_decision(root, strategy_id=strategy_id)

        assert decision.max_state == PromotionState.PAPER_TRADING
        assert decision.blocker_codes == ()
        assert len(decision.strategy_allocation_limits) == 1
        assert decision.strategy_allocation_limits[0]["strategy_id"] == strategy_id
        assert (
            Decimal(decision.strategy_allocation_limits[0]["max_strategy_allocation"])
            == cap
        )
        ledger_lines = [
            line
            for line in (root / strategy_id / "ledger" / "records.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        ledger_payload = json.loads(ledger_lines[-1])["payload"]
        assert all(
            Decimal(str(weight)) <= cap
            for weight in ledger_payload["target_weights"].values()
        )


def test_promotion_bundle_builder_test_reads_last_jsonl_record(tmp_path: Path) -> None:
    template = Path("config/strategy/promotion/baseline-long-only-v1")
    root = tmp_path / "promotion"
    strategy_id = "baseline-long-only-v1"

    write_paper_trading_promotion_bundle(
        root / strategy_id,
        strategy_id=strategy_id,
        max_strategy_allocation=Decimal("0.20"),
        template_bundle_root=template,
        target_weights={"SPY": Decimal("0.20")},
    )
    write_paper_trading_promotion_bundle(
        root / strategy_id,
        strategy_id=strategy_id,
        max_strategy_allocation=Decimal("0.40"),
        template_bundle_root=template,
        target_weights={"SPY": Decimal("0.40")},
    )

    ledger_lines = [
        line
        for line in (root / strategy_id / "ledger" / "records.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    ledger_payload = json.loads(ledger_lines[-1])["payload"]

    assert len(ledger_lines) == 2
    assert Decimal(ledger_payload["target_weights"]["SPY"]) == Decimal("0.40")
