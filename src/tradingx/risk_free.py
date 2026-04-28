"""Risk-free rate cache helpers backed by FRED's DGS3MO daily series.

source: https://fred.stlouisfed.org/series/DGS3MO
    (retrieved 2026-04-19)
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen

import exchange_calendars as xcals  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from tradingx.config import TradingConfig

DEFAULT_RISK_FREE_CACHE_PATH = Path("data/reference/risk_free_daily.csv")
DEFAULT_TREASURY_YIELD_CACHE_PATH = Path("data/reference/treasury_yields_daily.csv")
DEFAULT_VIX_CACHE_PATH = Path("data/reference/vix_daily.csv")
# source: https://fred.stlouisfed.org/series/DGS3MO (retrieved 2026-04-19)
RISK_FREE_SERIES_CODE = "DGS3MO"
TREASURY_SERIES_CODES = ("DGS2", "DGS10")
VIX_SERIES_CODE = "VIXCLS"
RISK_FREE_SOURCE = "fred"
TRADING_DAYS_PER_YEAR = 252
CACHE_REFRESH_INTERVAL = timedelta(days=7)
MACRO_MAX_STALENESS_SESSIONS = 5

RiskFreeFetcher = Callable[[str, str, date, date], pd.DataFrame]


@dataclass(frozen=True)
class CachedRiskFreeSeries:
    cache_path: Path

    def get_daily_rate(self, session_date: date) -> Decimal:
        return Decimal(
            str(daily_risk_free_rate_for_date(self.cache_path, as_of_date=session_date))
        )


def needs_risk_free_refresh(
    cache_path: Path,
    *,
    now_utc: datetime,
    max_age: timedelta = CACHE_REFRESH_INTERVAL,
) -> bool:
    if not cache_path.exists():
        return True
    modified_at = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=UTC)
    return modified_at < now_utc - max_age


def refresh_risk_free_cache(
    cache_path: Path,
    *,
    start_date: date,
    end_date: date,
    now_utc: datetime,
    fetcher: RiskFreeFetcher | None = None,
) -> Path:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")
    active_fetcher = fetcher or _default_fred_fetcher
    raw_frame = active_fetcher(
        RISK_FREE_SERIES_CODE,
        RISK_FREE_SOURCE,
        start_date,
        end_date,
    )
    normalized = _normalize_risk_free_frame(raw_frame)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(cache_path, index=False)
    timestamp = now_utc.astimezone(UTC).timestamp()
    os.utime(cache_path, (timestamp, timestamp))
    return cache_path


def load_risk_free_cache(cache_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(cache_path)
    expected_columns = {"date", "annualized_rate", "daily_rate"}
    if set(frame.columns) != expected_columns:
        raise ValueError(
            "Risk-free cache must contain exactly date, annualized_rate, and "
            "daily_rate columns."
        )
    loaded = frame.copy()
    loaded["date"] = pd.to_datetime(loaded["date"], utc=True).dt.normalize()
    return loaded.sort_values("date", kind="stable").reset_index(drop=True)


def daily_risk_free_rate_for_date(cache_path: Path, *, as_of_date: date) -> float:
    frame = load_risk_free_cache(cache_path)
    keyed = frame.set_index("date")["daily_rate"]
    target = pd.Timestamp(as_of_date).tz_localize(UTC)
    available = keyed.loc[keyed.index <= target]
    if available.empty:
        raise ValueError(
            "No cached risk-free rate is available on or before "
            f"{as_of_date.isoformat()}."
        )
    return float(available.iloc[-1])


def build_default_risk_free_series(
    config: TradingConfig,
    *,
    cache_path: Path | None = None,
) -> CachedRiskFreeSeries:
    resolved_cache_path = cache_path or (
        config.runtime.data_root / "reference" / DEFAULT_RISK_FREE_CACHE_PATH.name
    )
    return CachedRiskFreeSeries(resolved_cache_path)


def _normalize_risk_free_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if RISK_FREE_SERIES_CODE not in frame.columns:
        raise ValueError(
            f"Fetched risk-free frame must contain {RISK_FREE_SERIES_CODE}."
        )
    normalized = frame[[RISK_FREE_SERIES_CODE]].copy()
    normalized = normalized.dropna()
    if normalized.empty:
        raise ValueError("Fetched risk-free frame did not contain any observations.")
    normalized.index = pd.to_datetime(normalized.index, utc=True).normalize()
    normalized = normalized.sort_index(kind="stable")
    annualized_rate = normalized[RISK_FREE_SERIES_CODE].astype(float) / 100.0
    daily_rate = ((1.0 + annualized_rate) ** (1.0 / float(TRADING_DAYS_PER_YEAR))) - 1.0
    return pd.DataFrame(
        {
            "date": normalized.index.strftime("%Y-%m-%d"),
            "annualized_rate": annualized_rate.values,
            "daily_rate": daily_rate.values,
        }
    ).reset_index(drop=True)


def _normalize_treasury_frame(frame_by_code: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if set(frame_by_code.keys()) != set(TREASURY_SERIES_CODES):
        missing = set(TREASURY_SERIES_CODES) - set(frame_by_code.keys())
        raise ValueError(
            f"Missing Treasury series in fetch response: {sorted(missing)}"
        )
    aligned = pd.concat(
        [
            frame.rename(columns={code: code.lower()})
            for code, frame in frame_by_code.items()
        ],
        axis=1,
    ).dropna()
    aligned.index = pd.to_datetime(aligned.index, utc=True).normalize()
    aligned = aligned.sort_index(kind="stable")
    aligned["spread_2s10s_bps"] = (aligned["dgs10"] - aligned["dgs2"]) * 100.0
    return pd.DataFrame(
        {
            "date": aligned.index.strftime("%Y-%m-%d"),
            "dgs2": aligned["dgs2"].astype(float).values,
            "dgs10": aligned["dgs10"].astype(float).values,
            "spread_2s10s_bps": aligned["spread_2s10s_bps"].astype(float).values,
        }
    ).reset_index(drop=True)


def _normalize_vix_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if VIX_SERIES_CODE not in frame.columns:
        raise ValueError(f"Fetched VIX frame must contain {VIX_SERIES_CODE}.")
    normalized = frame[[VIX_SERIES_CODE]].copy()
    normalized = normalized.dropna()
    if normalized.empty:
        raise ValueError("Fetched VIX frame did not contain any observations.")
    normalized.index = pd.to_datetime(normalized.index, utc=True).normalize()
    normalized = normalized.sort_index(kind="stable")
    return pd.DataFrame(
        {
            "date": normalized.index.strftime("%Y-%m-%d"),
            "vix_close": normalized[VIX_SERIES_CODE].astype(float).values,
        }
    ).reset_index(drop=True)


def refresh_treasury_yield_cache(
    cache_path: Path,
    *,
    start_date: date,
    end_date: date,
    now_utc: datetime,
    fetcher: RiskFreeFetcher | None = None,
) -> Path:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")
    active_fetcher = fetcher or _default_fred_fetcher
    frame_by_code = {
        code: active_fetcher(code, RISK_FREE_SOURCE, start_date, end_date)
        for code in TREASURY_SERIES_CODES
    }
    normalized = _normalize_treasury_frame(frame_by_code)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(cache_path, index=False)
    timestamp = now_utc.astimezone(UTC).timestamp()
    os.utime(cache_path, (timestamp, timestamp))
    return cache_path


def refresh_vix_cache(
    cache_path: Path,
    *,
    start_date: date,
    end_date: date,
    now_utc: datetime,
    fetcher: RiskFreeFetcher | None = None,
) -> Path:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date.")
    active_fetcher = fetcher or _default_fred_fetcher
    raw_frame = active_fetcher(
        VIX_SERIES_CODE,
        RISK_FREE_SOURCE,
        start_date,
        end_date,
    )
    normalized = _normalize_vix_frame(raw_frame)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(cache_path, index=False)
    timestamp = now_utc.astimezone(UTC).timestamp()
    os.utime(cache_path, (timestamp, timestamp))
    return cache_path


def load_treasury_yield_cache(cache_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(cache_path)
    expected_columns = {"date", "dgs2", "dgs10", "spread_2s10s_bps"}
    if set(frame.columns) != expected_columns:
        raise ValueError(
            "Treasury yield cache must contain exactly date, dgs2, dgs10, and "
            "spread_2s10s_bps columns."
        )
    loaded = frame.copy()
    loaded["date"] = pd.to_datetime(loaded["date"], utc=True).dt.normalize()
    return loaded.sort_values("date", kind="stable").reset_index(drop=True)


def load_vix_cache(cache_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(cache_path)
    expected_columns = {"date", "vix_close"}
    timestamp_columns = {"date", "vix_close", "release_timestamp_utc"}
    column_set = set(frame.columns)
    if column_set != expected_columns and column_set != timestamp_columns:
        raise ValueError(
            "VIX cache must contain date and vix_close, with optional "
            "release_timestamp_utc."
        )
    loaded = frame.copy()
    loaded["date"] = pd.to_datetime(loaded["date"], utc=True).dt.normalize()
    if "release_timestamp_utc" in loaded.columns:
        loaded["release_timestamp_utc"] = pd.to_datetime(
            loaded["release_timestamp_utc"],
            utc=True,
        )
    return loaded.sort_values("date", kind="stable").reset_index(drop=True)


def yield_curve_spread_for_date(cache_path: Path, *, as_of_date: date) -> Decimal:
    frame = load_treasury_yield_cache(cache_path)
    keyed = frame.set_index("date")["spread_2s10s_bps"]
    target = pd.Timestamp(as_of_date).tz_localize(UTC)
    available = keyed.loc[keyed.index <= target]
    if available.empty:
        raise ValueError(
            "No cached Treasury spread is available on or before "
            f"{as_of_date.isoformat()}."
        )
    return Decimal(str(float(available.iloc[-1])))


def vix_close_for_date(
    cache_path: Path,
    *,
    as_of_date: date,
    as_of_utc: datetime | None = None,
) -> Decimal | None:
    frame = load_vix_cache(cache_path)
    return _pit_macro_value_for_date(
        frame,
        value_column="vix_close",
        as_of_date=as_of_date,
        as_of_utc=as_of_utc,
    )


def yield_curve_spread_for_date_pit(
    cache_path: Path,
    *,
    as_of_date: date,
    as_of_utc: datetime | None = None,
) -> Decimal | None:
    frame = load_treasury_yield_cache(cache_path)
    return _pit_macro_value_for_date(
        frame,
        value_column="spread_2s10s_bps",
        as_of_date=as_of_date,
        as_of_utc=as_of_utc,
    )


def _pit_macro_value_for_date(
    frame: pd.DataFrame,
    *,
    value_column: str,
    as_of_date: date,
    as_of_utc: datetime | None = None,
) -> Decimal | None:
    if frame.empty:
        return None
    target_session = pd.Timestamp(as_of_date).tz_localize(UTC).normalize()
    target_instant = (
        pd.Timestamp(as_of_utc).tz_convert(UTC)
        if as_of_utc is not None
        else target_session
    )
    loaded = frame.copy()
    loaded["_available_date"] = loaded.apply(_macro_available_date, axis=1)
    available = loaded.loc[loaded["_available_date"] <= target_instant]
    if available.empty:
        return None
    latest = available.iloc[-1]
    observation_date = cast(pd.Timestamp, latest["date"])
    if (
        _trading_sessions_after(observation_date, target_session)
        > MACRO_MAX_STALENESS_SESSIONS
    ):
        return None
    return Decimal(str(float(latest[value_column])))


def _macro_available_date(row: pd.Series) -> pd.Timestamp:
    release_timestamp = row.get("release_timestamp_utc")
    if pd.notna(release_timestamp):
        release = pd.Timestamp(release_timestamp)
        if release.tzinfo is None:
            release = release.tz_localize(UTC)
        return release.tz_convert(UTC)
    observation_date = cast(pd.Timestamp, row["date"])
    return _next_nyse_session(observation_date)


def _next_nyse_session(session_date: pd.Timestamp) -> pd.Timestamp:
    calendar = xcals.get_calendar("XNYS")
    normalized = session_date.tz_convert(None).normalize()
    if calendar.is_session(normalized):
        return calendar.next_session(normalized).tz_localize(UTC)
    sessions = calendar.sessions_in_range(normalized, normalized + pd.Timedelta(days=7))
    if sessions.empty:
        raise ValueError(f"No NYSE session found after {normalized.date()}.")
    return sessions[0].tz_localize(UTC)


def _trading_sessions_after(
    observation_date: pd.Timestamp,
    as_of_timestamp: pd.Timestamp,
) -> int:
    calendar = xcals.get_calendar("XNYS")
    start = observation_date.tz_convert(None).normalize()
    end = as_of_timestamp.tz_convert(None).normalize()
    if end <= start:
        return 0
    sessions = calendar.sessions_in_range(start, end)
    return int(sum(session > start for session in sessions))


def _default_fred_fetcher(
    symbol: str,
    source: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    if source != RISK_FREE_SOURCE:
        raise ValueError(f"Unsupported risk-free data source: {source}.")
    try:
        from pandas_datareader.data import DataReader  # type: ignore[import-untyped]

        return DataReader(symbol, source, start, end)
    except ModuleNotFoundError:
        return _fetch_fred_csv(symbol, start, end)


def _fetch_fred_csv(symbol: str, start: date, end: date) -> pd.DataFrame:
    # source: https://fred.stlouisfed.org/data/DGS3MO (retrieved 2026-04-19)
    url = f"https://fred.stlouisfed.org/data/{symbol}"
    html = _download_text(url)

    tables = pd.read_html(
        StringIO(html),
        attrs={"id": "data-table-observations"},
    )
    if not tables:
        raise ValueError(
            f"FRED table response for {symbol} did not contain observations."
        )
    visible = tables[0].copy()
    if "DATE" not in visible.columns or "VALUE" not in visible.columns:
        raise ValueError(
            f"FRED table response for {symbol} did not match expectations."
        )
    visible = visible.rename(columns={"VALUE": symbol})

    hidden_rows = re.findall(r"#(\d{4}-\d{2}-\d{2})\|\s*([0-9.]+|\.)", html)
    hidden = pd.DataFrame(hidden_rows, columns=["DATE", symbol])

    frame = pd.concat((visible, hidden), ignore_index=True)
    frame = frame.drop_duplicates(subset=["DATE"], keep="first")
    frame[symbol] = frame[symbol].replace(".", pd.NA)
    frame = frame.dropna(subset=[symbol])
    frame["DATE"] = pd.to_datetime(frame["DATE"], utc=True)
    frame[symbol] = frame[symbol].astype(float)
    mask = (frame["DATE"].dt.date >= start) & (frame["DATE"].dt.date <= end)
    return frame.loc[mask, ["DATE", symbol]].set_index("DATE")


def _download_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "TradingX/0.1"})
    try:
        with urlopen(request) as response:
            body = cast(bytes, response.read())
            return body.decode("utf-8")
    except Exception:
        result = subprocess.run(
            ("curl", "-fsSL", "--compressed", url),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout


__all__ = (
    "CACHE_REFRESH_INTERVAL",
    "CachedRiskFreeSeries",
    "DEFAULT_RISK_FREE_CACHE_PATH",
    "DEFAULT_TREASURY_YIELD_CACHE_PATH",
    "DEFAULT_VIX_CACHE_PATH",
    "MACRO_MAX_STALENESS_SESSIONS",
    "RISK_FREE_SERIES_CODE",
    "RISK_FREE_SOURCE",
    "TREASURY_SERIES_CODES",
    "TRADING_DAYS_PER_YEAR",
    "VIX_SERIES_CODE",
    "build_default_risk_free_series",
    "daily_risk_free_rate_for_date",
    "load_risk_free_cache",
    "load_treasury_yield_cache",
    "load_vix_cache",
    "needs_risk_free_refresh",
    "refresh_risk_free_cache",
    "refresh_treasury_yield_cache",
    "refresh_vix_cache",
    "vix_close_for_date",
    "yield_curve_spread_for_date",
    "yield_curve_spread_for_date_pit",
)
