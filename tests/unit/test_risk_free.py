from __future__ import annotations

import importlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest


def test_risk_free_module_shell_is_importable() -> None:
    module = importlib.import_module("tradingx.risk_free")

    assert module.__doc__
    assert hasattr(module, "__all__")


def test_needs_risk_free_refresh_returns_true_when_cache_is_missing(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.risk_free")

    assert (
        module.needs_risk_free_refresh(
            tmp_path / "risk_free_daily.csv",
            now_utc=datetime(2026, 4, 19, 16, 40, tzinfo=UTC),
        )
        is True
    )


def test_needs_risk_free_refresh_returns_false_for_fresh_cache(tmp_path: Path) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "risk_free_daily.csv"
    cache_path.write_text("date,annualized_rate,daily_rate\n", encoding="utf-8")

    fresh_time = datetime(2026, 4, 16, 12, 0, tzinfo=UTC).timestamp()
    cache_path.touch()
    cache_path.chmod(0o644)
    import os

    os.utime(cache_path, (fresh_time, fresh_time))

    assert (
        module.needs_risk_free_refresh(
            cache_path,
            now_utc=datetime(2026, 4, 19, 16, 40, tzinfo=UTC),
        )
        is False
    )


def test_refresh_risk_free_cache_writes_normalized_csv(tmp_path: Path) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "risk_free_daily.csv"

    def fake_fetcher(symbol: str, source: str, start: date, end: date) -> pd.DataFrame:
        assert symbol == "DGS3MO"
        assert source == "fred"
        assert start == date(2026, 4, 1)
        assert end == date(2026, 4, 3)
        return pd.DataFrame(
            {"DGS3MO": [4.50, 4.56, 4.62]},
            index=pd.to_datetime(["2026-04-01", "2026-04-02", "2026-04-03"]),
        )

    written_path = module.refresh_risk_free_cache(
        cache_path,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 3),
        now_utc=datetime(2026, 4, 19, 16, 40, tzinfo=UTC),
        fetcher=fake_fetcher,
    )

    assert written_path == cache_path
    frame = pd.read_csv(cache_path)
    assert list(frame.columns) == ["date", "annualized_rate", "daily_rate"]
    assert frame["date"].tolist() == ["2026-04-01", "2026-04-02", "2026-04-03"]
    assert frame["annualized_rate"].tolist() == pytest.approx([0.0450, 0.0456, 0.0462])
    assert frame["daily_rate"].tolist() == pytest.approx(
        [
            (1.0450 ** (1.0 / 252.0)) - 1.0,
            (1.0456 ** (1.0 / 252.0)) - 1.0,
            (1.0462 ** (1.0 / 252.0)) - 1.0,
        ]
    )


def test_daily_risk_free_rate_uses_latest_available_observation(tmp_path: Path) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "risk_free_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-01", "2026-04-03"],
            "annualized_rate": [0.0450, 0.0462],
            "daily_rate": [
                (1.0450 ** (1.0 / 252.0)) - 1.0,
                (1.0462 ** (1.0 / 252.0)) - 1.0,
            ],
        }
    ).to_csv(cache_path, index=False)

    rate = module.daily_risk_free_rate_for_date(cache_path, as_of_date=date(2026, 4, 5))

    assert rate == pytest.approx((1.0462 ** (1.0 / 252.0)) - 1.0)


def test_daily_risk_free_rate_raises_before_first_cached_observation(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "risk_free_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-03"],
            "annualized_rate": [0.0462],
            "daily_rate": [(1.0462 ** (1.0 / 252.0)) - 1.0],
        }
    ).to_csv(cache_path, index=False)

    with pytest.raises(ValueError, match="No cached risk-free rate is available"):
        module.daily_risk_free_rate_for_date(cache_path, as_of_date=date(2026, 4, 1))


def test_build_default_risk_free_series_uses_runtime_data_root(tmp_path: Path) -> None:
    module = importlib.import_module("tradingx.risk_free")
    config_module = importlib.import_module("tradingx.config")
    cache_path = tmp_path / "data" / "reference" / "risk_free_daily.csv"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "date": ["2026-04-03"],
            "annualized_rate": [0.0462],
            "daily_rate": [(1.0462 ** (1.0 / 252.0)) - 1.0],
        }
    ).to_csv(cache_path, index=False)

    config = config_module.TradingConfig(
        paper_credentials=config_module.PaperCredentials(
            api_key="paper-key",
            api_secret="paper-secret",
            account_id="paper-account",
        ),
        live_controls=config_module.LiveTradingControls(),
        alerting=config_module.AlertingConfig(),
        runtime=config_module.RuntimeConfig(data_root=tmp_path / "data"),
        web=config_module.WebAppConfig(),
    )

    series = module.build_default_risk_free_series(config)

    assert float(series.get_daily_rate(date(2026, 4, 5))) == pytest.approx(
        (1.0462 ** (1.0 / 252.0)) - 1.0
    )


def _fake_treasury_fetcher(
    symbol: str,
    source: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    assert source == "fred"
    dates = pd.date_range(start, end, freq="B", tz="UTC")
    values = {"DGS2": 4.50, "DGS10": 4.25}.get(symbol, 4.00)
    return pd.DataFrame({symbol: [values] * len(dates)}, index=dates)


def test_refresh_treasury_yield_cache_writes_single_csv_with_both_series(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "treasury_yields.csv"

    module.refresh_treasury_yield_cache(
        cache_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 10),
        now_utc=datetime(2025, 1, 10, tzinfo=UTC),
        fetcher=_fake_treasury_fetcher,
    )

    assert cache_path.exists()
    frame = module.load_treasury_yield_cache(cache_path)
    assert set(frame.columns) == {"date", "dgs2", "dgs10", "spread_2s10s_bps"}
    assert all(abs(frame["spread_2s10s_bps"] - (-25.0)) < 1e-6)


def test_yield_curve_spread_for_date_returns_decimal_bps(tmp_path: Path) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "treasury_yields.csv"

    module.refresh_treasury_yield_cache(
        cache_path,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 10),
        now_utc=datetime(2025, 1, 10, tzinfo=UTC),
        fetcher=_fake_treasury_fetcher,
    )

    spread = module.yield_curve_spread_for_date(
        cache_path,
        as_of_date=date(2025, 1, 8),
    )

    assert isinstance(spread, Decimal)
    assert abs(float(spread) - (-25.0)) < 1e-6


def test_treasury_series_codes_exposed() -> None:
    module = importlib.import_module("tradingx.risk_free")

    assert module.TREASURY_SERIES_CODES == ("DGS2", "DGS10")


def test_refresh_vix_cache_writes_normalized_vixcls_csv(tmp_path: Path) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "vix_daily.csv"

    def fake_fetcher(symbol: str, source: str, start: date, end: date) -> pd.DataFrame:
        assert symbol == "VIXCLS"
        assert source == "fred"
        assert start == date(2026, 4, 20)
        assert end == date(2026, 4, 22)
        return pd.DataFrame(
            {"VIXCLS": [24.5, 26.0, 35.2]},
            index=pd.to_datetime(["2026-04-20", "2026-04-21", "2026-04-22"]),
        )

    module.refresh_vix_cache(
        cache_path,
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 22),
        now_utc=datetime(2026, 4, 23, tzinfo=UTC),
        fetcher=fake_fetcher,
    )

    frame = module.load_vix_cache(cache_path)

    assert list(frame.columns) == ["date", "vix_close"]
    assert frame["date"].dt.date.tolist() == [
        date(2026, 4, 20),
        date(2026, 4, 21),
        date(2026, 4, 22),
    ]
    assert frame["vix_close"].tolist() == pytest.approx([24.5, 26.0, 35.2])


def test_vix_pit_lookup_uses_one_business_day_lag_without_release_time(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "vix_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-20", "2026-04-21"],
            "vix_close": [24.5, 28.0],
        }
    ).to_csv(cache_path, index=False)

    same_day = module.vix_close_for_date(cache_path, as_of_date=date(2026, 4, 20))
    next_session = module.vix_close_for_date(cache_path, as_of_date=date(2026, 4, 21))

    assert same_day is None
    assert next_session == Decimal("24.5")


def test_vix_pit_lookup_does_not_leak_same_day_after_close_release_timestamp(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "vix_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-20"],
            "vix_close": [36.25],
            "release_timestamp_utc": ["2026-04-20T21:30:00+00:00"],
        }
    ).to_csv(cache_path, index=False)

    value = module.vix_close_for_date(cache_path, as_of_date=date(2026, 4, 20))

    assert value is None


def test_vix_pit_lookup_allows_release_timestamp_before_decision_time(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.risk_free")
    cache_path = tmp_path / "vix_daily.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-20"],
            "vix_close": [36.25],
            "release_timestamp_utc": ["2026-04-20T13:00:00+00:00"],
        }
    ).to_csv(cache_path, index=False)

    value = module.vix_close_for_date(
        cache_path,
        as_of_date=date(2026, 4, 20),
        as_of_utc=datetime(2026, 4, 20, 14, 0, tzinfo=UTC),
    )

    assert value == Decimal("36.25")


def test_macro_pit_lookup_treats_values_older_than_five_nyse_sessions_as_missing(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("tradingx.risk_free")
    vix_path = tmp_path / "vix_daily.csv"
    treasury_path = tmp_path / "treasury_yields.csv"
    pd.DataFrame(
        {
            "date": ["2026-04-20"],
            "vix_close": [22.0],
        }
    ).to_csv(vix_path, index=False)
    pd.DataFrame(
        {
            "date": ["2026-04-20"],
            "dgs2": [4.5],
            "dgs10": [4.0],
            "spread_2s10s_bps": [-50.0],
        }
    ).to_csv(treasury_path, index=False)

    assert module.vix_close_for_date(vix_path, as_of_date=date(2026, 4, 28)) is None
    assert (
        module.yield_curve_spread_for_date_pit(
            treasury_path,
            as_of_date=date(2026, 4, 28),
        )
        is None
    )
