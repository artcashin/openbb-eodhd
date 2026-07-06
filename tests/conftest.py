"""Shared fixtures for openbb-eodhd tests."""

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest


# ============================================================
# Mock helpers
# ============================================================

def _make_mock_pykx():
    """Return a mock pykx module for modules that import it."""
    mock_kx = MagicMock()
    mock_kx.q = MagicMock()
    return mock_kx


# ============================================================
# Async helpers
# ============================================================

def run_async(async_fn, *args, **kwargs):
    """Run an async function synchronously via asyncio.run."""
    return asyncio.run(async_fn(*args, **kwargs))


# ============================================================
# Sample EODHD bar data
# ============================================================

@pytest.fixture
def eod_bar_data() -> list[dict]:
    return [
        {"date": "2024-01-02", "open": 150.0, "high": 153.0, "low": 149.0,
         "close": 152.0, "volume": 1000000, "adjusted_close": 151.5},
        {"date": "2024-01-03", "open": 152.0, "high": 155.0, "low": 151.0,
         "close": 154.0, "volume": 1200000, "adjusted_close": 153.5},
    ]


@pytest.fixture
def intraday_bar_data() -> list[dict]:
    return [
        {"timestamp": 1704150000, "open": 150.0, "high": 151.0, "low": 149.5,
         "close": 150.5, "volume": 50000},
        {"timestamp": 1704153600, "open": 150.5, "high": 152.0, "low": 150.0,
         "close": 151.0, "volume": 45000},
    ]


@pytest.fixture
def null_close_bar_data() -> list[dict]:
    return [
        {"date": "2024-01-02", "open": 150.0, "high": 153.0, "low": 149.0,
         "close": 152.0, "volume": 1000000},
        {"date": "2024-01-03", "open": None, "high": None, "low": None,
         "close": None, "volume": 0},
    ]


@pytest.fixture
def multi_symbol_bar_data() -> list[dict]:
    return [
        {"_symbol": "AAPL", "date": "2024-01-02", "open": 150.0,
         "high": 153.0, "low": 149.0, "close": 152.0, "volume": 1000000},
        {"_symbol": "MSFT", "date": "2024-01-02", "open": 300.0,
         "high": 305.0, "low": 299.0, "close": 302.0, "volume": 2000000},
    ]


@pytest.fixture
def eodhd_credentials() -> dict[str, str]:
    return {"eodhd_api_key": "test_key_123"}


# ============================================================
# Mock amake_request
# ============================================================

@pytest.fixture
def mock_amake_request():
    """Return a factory that creates mock async amake_request functions."""

    def _make(response: Any):
        async def mock_request(url, method="GET", **kwargs):
            return response
        return mock_request

    return _make
