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

import pandas as pd  # type: ignore[import-untyped]

from tradingx.config import TradingConfig

DEFAULT_RISK_FREE_CACHE_PATH = Path("data/reference/risk_free_daily.csv")
# source: https://fred.stlouisfed.org/series/DGS3MO (retrieved 2026-04-19)
RISK_FREE_SERIES_CODE = "DGS3MO"
RISK_FREE_SOURCE = "fred"
TRADING_DAYS_PER_YEAR = 252
CACHE_REFRESH_INTERVAL = timedelta(days=7)

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
    "RISK_FREE_SERIES_CODE",
    "RISK_FREE_SOURCE",
    "TRADING_DAYS_PER_YEAR",
    "build_default_risk_free_series",
    "daily_risk_free_rate_for_date",
    "load_risk_free_cache",
    "needs_risk_free_refresh",
    "refresh_risk_free_cache",
)
