"""Shared test configuration."""

import pytest


@pytest.fixture
def anyio_backend():
    """Pin anyio tests to asyncio only (trio is not installed)."""
    return "asyncio"
