"""EODHD corporate actions: historical dividends and splits."""

from typing import Any

from openbb_core.provider.abstract.fetcher import Fetcher
from openbb_core.provider.standard_models.historical_dividends import (
    HistoricalDividendsData,
    HistoricalDividendsQueryParams,
)
from openbb_core.provider.standard_models.historical_splits import (
    HistoricalSplitsData,
    HistoricalSplitsQueryParams,
)
from openbb_core.app.model.abstract.error import OpenBBError
from openbb_core.provider.utils.errors import EmptyDataError, UnauthorizedError
from pydantic import Field

BASE_URL = "https://eodhd.com/api"


def _qualify(symbol: str, exchange: str) -> str:
    """Qualify a single bare symbol with an exchange code (AAPL -> AAPL.US)."""
    s = symbol.strip().upper()
    return s if "." in s else f"{s}.{exchange.upper()}"


async def _fetch_list(
    kind: str, sym: str, credentials: dict[str, str] | None, extra: dict | None = None
) -> list[dict]:
    """GET /api/{div|splits}/{sym} and return the raw JSON list."""
    # pylint: disable=import-outside-toplevel
    from openbb_core.provider.utils.helpers import amake_request

    api_key = (credentials or {}).get("eodhd_api_key")
    if not api_key:
        raise UnauthorizedError("Missing EODHD credential. Set EODHD_API_KEY.")

    params = {"api_token": api_key, "fmt": "json", **(extra or {})}
    try:
        response = await amake_request(
            f"{BASE_URL}/{kind}/{sym}", method="GET", params=params, timeout=30
        )
    except Exception as exc:
        # The request itself failed; a 401/403 also lands here (HTML body), so
        # keep the API-key hint without asserting the failure is auth-related.
        raise OpenBBError(
            f"EODHD {kind} for '{sym}' failed: {exc}. If this is a 401/403, verify"
            " EODHD_API_KEY is valid and the token has access to this symbol."
        ) from exc
    if isinstance(response, dict):
        msg = response.get("errors") or response.get("message") or response
        raise UnauthorizedError(f"EODHD ({sym}): {msg}")
    if not response:
        raise EmptyDataError(f"EODHD returned no {kind} for '{sym}'.")
    return response


# --- Dividends -----------------------------------------------------------------
class EODHDHistoricalDividendsQueryParams(HistoricalDividendsQueryParams):
    """EODHD Historical Dividends Query."""

    exchange: str = Field(
        default="US", description="EODHD exchange code for bare symbols (e.g. 'US')."
    )


class EODHDHistoricalDividendsData(HistoricalDividendsData):
    """EODHD Historical Dividends Data."""

    declaration_date: Any = Field(default=None, description="Dividend declaration date.")
    record_date: Any = Field(default=None, description="Dividend record date.")
    payment_date: Any = Field(default=None, description="Dividend payment date.")
    frequency: str | None = Field(default=None, description="Dividend period/frequency.")
    unadjusted_amount: float | None = Field(
        default=None, description="Unadjusted dividend amount."
    )
    currency: str | None = Field(default=None, description="Dividend currency.")


class EODHDHistoricalDividendsFetcher(
    Fetcher[EODHDHistoricalDividendsQueryParams, list[EODHDHistoricalDividendsData]]
):
    """EODHD historical dividends (/api/div)."""

    @staticmethod
    def transform_query(params: dict[str, Any]) -> EODHDHistoricalDividendsQueryParams:
        # pylint: disable=unused-argument
        return EODHDHistoricalDividendsQueryParams(**params)

    @staticmethod
    async def aextract_data(query, credentials, **kwargs) -> list[dict]:  # pylint: disable=unused-argument
        extra: dict[str, Any] = {}
        if query.start_date:
            extra["from"] = str(query.start_date)
        if query.end_date:
            extra["to"] = str(query.end_date)
        sym = _qualify(query.symbol, query.exchange)
        return await _fetch_list("div", sym, credentials, extra)

    @staticmethod
    def transform_data(query, data: list[dict], **kwargs) -> list[EODHDHistoricalDividendsData]:  # pylint: disable=unused-argument
        # pylint: disable=import-outside-toplevel
        from pandas import isna, to_datetime

        def _d(v):
            if not v:
                return None
            ts = to_datetime(v, errors="coerce")
            return None if isna(ts) else ts.date()

        rows = []
        for item in data:
            ex_date = _d(item.get("date"))
            # ex_dividend_date is the primary field and the sort key; skip rows
            # that lack a usable one rather than carry a null/NaT date.
            if ex_date is None:
                continue
            rows.append(
                EODHDHistoricalDividendsData.model_validate(
                    {
                        "ex_dividend_date": ex_date,
                        "amount": item.get("value"),
                        "declaration_date": _d(item.get("declarationDate")),
                        "record_date": _d(item.get("recordDate")),
                        "payment_date": _d(item.get("paymentDate")),
                        "frequency": item.get("period"),
                        "unadjusted_amount": item.get("unadjustedValue"),
                        "currency": item.get("currency"),
                    }
                )
            )
        rows.sort(key=lambda r: r.ex_dividend_date)
        return rows


# --- Splits --------------------------------------------------------------------
class EODHDHistoricalSplitsQueryParams(HistoricalSplitsQueryParams):
    """EODHD Historical Splits Query."""

    exchange: str = Field(
        default="US", description="EODHD exchange code for bare symbols (e.g. 'US')."
    )


class EODHDHistoricalSplitsData(HistoricalSplitsData):
    """EODHD Historical Splits Data."""


class EODHDHistoricalSplitsFetcher(
    Fetcher[EODHDHistoricalSplitsQueryParams, list[EODHDHistoricalSplitsData]]
):
    """EODHD historical splits (/api/splits)."""

    @staticmethod
    def transform_query(params: dict[str, Any]) -> EODHDHistoricalSplitsQueryParams:
        # pylint: disable=unused-argument
        return EODHDHistoricalSplitsQueryParams(**params)

    @staticmethod
    async def aextract_data(query, credentials, **kwargs) -> list[dict]:  # pylint: disable=unused-argument
        sym = _qualify(query.symbol, query.exchange)
        return await _fetch_list("splits", sym, credentials)

    @staticmethod
    def transform_data(query, data: list[dict], **kwargs) -> list[EODHDHistoricalSplitsData]:  # pylint: disable=unused-argument
        # pylint: disable=import-outside-toplevel
        from pandas import to_datetime

        rows = []
        for item in data:
            # EODHD "split" is a "num/den" string, e.g. "4.000000/1.000000".
            raw = str(item.get("split", "")).split("/")
            try:
                num = float(raw[0])
                den = float(raw[1]) if len(raw) > 1 and float(raw[1]) else 1.0
            except (ValueError, IndexError):
                continue
            raw_date = item.get("date")
            if not raw_date:
                continue
            try:
                parsed = to_datetime(raw_date).date()
            except (ValueError, TypeError):
                continue
            rows.append(
                EODHDHistoricalSplitsData.model_validate(
                    {
                        "date": parsed,
                        "numerator": num,
                        "denominator": den,
                        # standard field is a string, e.g. "4:1".
                        "split_ratio": f"{num:g}:{den:g}",
                    }
                )
            )
        rows.sort(key=lambda r: r.date)
        return rows
