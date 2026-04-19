from __future__ import annotations

from decimal import Decimal

from tradingx.quant import decimal_stddev


def test_decimal_stddev_matches_sample_standard_deviation() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]

    result = decimal_stddev(values)

    assert result == Decimal("1.5811388300841898")
