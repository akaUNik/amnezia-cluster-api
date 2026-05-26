import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("SERVER_PUBLIC_HOST", "vpn.example.test")

    from src.management.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"
