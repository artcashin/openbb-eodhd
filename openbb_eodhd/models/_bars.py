"""Shared EODHD price-bar helpers (used by equity, crypto, and forex historical).

EODHD serves every asset class through the same two endpoints — `/api/eod`
(daily/weekly/monthly) and `/api/intraday` (1m/5m/1h) — differing only by the
symbol suffix (`.US`, `.CC`, `.FOREX`). This module holds the request/parse
logic once; each asset-class fetcher supplies its own symbol qualification.
"""

from datetime import datetime, time, timezone
from typing import Any

from openbb_core.app.model.abstract.error import OpenBBError
from openbb_core.provider.utils.errors import EmptyDataError, UnauthorizedError

# OpenBB interval -> EODHD. Intraday -> /api/intraday; daily+ -> /api/eod.
INTRADAY_MAP = {"1m": "1m", "5m": "5m", "1h": "1h"}
EOD_PERIOD_MAP = {"1d": "d", "1W": "w", "1M": "m"}
INTERVAL_CHOICES = list(INTRADAY_MAP) + list(EOD_PERIOD_MAP)
BASE_URL = "https://eodhd.com/api"


def to_unix(day: Any, *, end_of_day: bool) -> int:
    """Convert a date to a UTC unix timestamp (start or end of that day)."""
    clock = time.max if end_of_day else time.min
    return int(datetime.combine(day, clock, tzinfo=timezone.utc).timestamp())


async def fetch_bars(
    interval: str,
    symbols: list[str],
    start_date: Any,
    end_date: Any,
    credentials: dict[str, str] | None,
) -> list[dict]:
    """Fetch raw bars for already-qualified symbols (e.g. AAPL.US, BTC-USD.CC)."""
    # pylint: disable=import-outside-toplevel
    from openbb_core.provider.utils.helpers import amake_request

    api_key = (credentials or {}).get("eodhd_api_key")
    if not api_key:
        raise UnauthorizedError("Missing EODHD credential. Set EODHD_API_KEY.")

    intraday = interval in INTRADAY_MAP
    multiple = len(symbols) > 1
    results: list[dict] = []
    for sym in symbols:
        if intraday:
            url = f"{BASE_URL}/intraday/{sym}"
            params: dict[str, Any] = {
                "api_token": api_key,
                "fmt": "json",
                "interval": INTRADAY_MAP[interval],
                "from": to_unix(start_date, end_of_day=False),
                "to": to_unix(end_date, end_of_day=True),
            }
        else:
            url = f"{BASE_URL}/eod/{sym}"
            params = {
                "api_token": api_key,
                "fmt": "json",
                "period": EOD_PERIOD_MAP[interval],
                "from": str(start_date),
                "to": str(end_date),
                "order": "a",
            }
        try:
            response = await amake_request(
                url, method="GET", params=params, timeout=30
            )
        except Exception as exc:
            # The request itself failed (timeout, connection, non-JSON body).
            # Don't assume it's auth — but a 401/403 also lands here (EODHD
            # returns HTML), so keep the API-key hint.
            raise OpenBBError(
                f"EODHD request for '{sym}' failed: {exc}. If this is a 401/403,"
                " verify EODHD_API_KEY is valid and the token has access to this"
                " symbol/exchange."
            ) from exc
        if isinstance(response, dict):
            msg = response.get("errors") or response.get("message") or response
            raise UnauthorizedError(f"EODHD ({sym}): {msg}")
        for bar in response or []:
            if multiple:
                bar["_symbol"] = sym
            results.append(bar)

    if not results:
        raise EmptyDataError("The request was returned empty.")
    return results


def rows_from_bars(interval: str, multiple: bool, data: list[dict]) -> list[dict]:
    """Turn raw EODHD bars into standard-model row dicts."""
    # pylint: disable=import-outside-toplevel
    from pandas import isna, to_datetime

    intraday = interval in INTRADAY_MAP
    rows: list[dict] = []
    for bar in data:
        # EODHD emits null-OHLC rows for no-trade buckets; drop them.
        if bar.get("close") is None:
            continue
        if intraday:
            # `timestamp` is a UTC unix epoch; keep bars tz-aware in UTC.
            bar_date: Any = to_datetime(bar.get("timestamp"), unit="s", utc=True, errors="coerce")
        else:
            bar_date = to_datetime(bar.get("date"), errors="coerce")
        # Skip bars whose date is missing/unparseable — never emit a NaT row.
        if isna(bar_date):
            continue
        if not intraday:
            bar_date = bar_date.date()
        row = {
            "date": bar_date,
            "open": bar.get("open"),
            "high": bar.get("high"),
            "low": bar.get("low"),
            "close": bar.get("close"),
            "volume": bar.get("volume"),
            "adjusted_close": bar.get("adjusted_close"),
        }
        if multiple:
            row["symbol"] = bar.get("_symbol")
        rows.append(row)
    # Chronological, then by symbol when multiple. Every row has a real date
    # (NaT rows were skipped above), so the sort key is safe.
    rows.sort(key=lambda r: (str(r.get("symbol", "")), r["date"]))
    return rows
