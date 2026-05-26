import hashlib

import pytest
from pydantic import ValidationError

from src.api.v1.management.middlewares.auth import FailedAuthLimiter
from src.management import security
from src.management.security import APIKeyStorage
from src.management.settings import Settings, get_settings


def test_api_key_verification_uses_fixed_length_digest_comparison(monkeypatch):
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("SERVER_PUBLIC_HOST", "vpn.example.test")
    get_settings.cache_clear()

    storage = APIKeyStorage()
    storage._api_key = "stored-secret"
    compared_lengths: list[tuple[int, int]] = []

    def fake_compare_digest(left: bytes, right: bytes) -> bool:
        compared_lengths.append((len(left), len(right)))
        return left == right

    monkeypatch.setattr(security.secrets, "compare_digest", fake_compare_digest)

    assert storage.verify_api_key("stored-secret") is True
    assert storage.verify_api_key("stored-secret-with-extra-data") is False
    assert compared_lengths == [
        (hashlib.sha256().digest_size, hashlib.sha256().digest_size),
        (hashlib.sha256().digest_size, hashlib.sha256().digest_size),
    ]

    get_settings.cache_clear()


def test_settings_require_api_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            development=True,
            server_public_host="vpn.example.test",
        )


def test_settings_reject_blank_api_key():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            development=True,
            server_public_host="vpn.example.test",
            api_key="   ",
        )


def test_failed_auth_limiter_blocks_after_configured_failures():
    current_time = 100.0

    def clock() -> float:
        return current_time

    limiter = FailedAuthLimiter(
        limit=2,
        window_seconds=60,
        block_seconds=30,
        clock=clock,
    )
    identifier = "203.0.113.10"

    assert limiter.is_blocked(identifier) is False

    limiter.record_failure(identifier)
    assert limiter.is_blocked(identifier) is False

    limiter.record_failure(identifier)
    assert limiter.is_blocked(identifier) is True


def test_failed_auth_limiter_clears_failures_after_success():
    limiter = FailedAuthLimiter(
        limit=2,
        window_seconds=60,
        block_seconds=30,
        clock=lambda: 100.0,
    )
    identifier = "203.0.113.10"

    limiter.record_failure(identifier)
    limiter.record_success(identifier)
    limiter.record_failure(identifier)

    assert limiter.is_blocked(identifier) is False
