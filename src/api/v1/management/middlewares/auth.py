from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from threading import Lock
from time import monotonic

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from src.api.v1.management.exceptions.auth import (
    ApiKeyRateLimitException,
    InvalidApiKeyException,
)
from src.management.security import get_api_key_storage
from src.management.settings import get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class FailedAuthRecord:
    attempts: deque[float] = field(default_factory=deque)
    blocked_until: float = 0.0


class FailedAuthLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int,
        block_seconds: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self.block_seconds = max(1, block_seconds)
        self.clock = clock
        self._records: defaultdict[str, FailedAuthRecord] = defaultdict(FailedAuthRecord)
        self._lock = Lock()

    def is_blocked(self, identifier: str) -> bool:
        now = self.clock()
        with self._lock:
            record = self._records[identifier]
            if record.blocked_until <= now:
                record.blocked_until = 0.0
                return False
            return True

    def record_failure(self, identifier: str) -> None:
        now = self.clock()
        window_start = now - self.window_seconds
        with self._lock:
            record = self._records[identifier]
            while record.attempts and record.attempts[0] <= window_start:
                record.attempts.popleft()

            record.attempts.append(now)
            if len(record.attempts) >= self.limit:
                record.blocked_until = now + self.block_seconds
                record.attempts.clear()

    def record_success(self, identifier: str) -> None:
        with self._lock:
            self._records.pop(identifier, None)


@lru_cache
def get_failed_auth_limiter() -> FailedAuthLimiter:
    settings = get_settings()
    return FailedAuthLimiter(
        limit=settings.api_key_failed_auth_limit,
        window_seconds=settings.api_key_failed_auth_window_seconds,
        block_seconds=settings.api_key_failed_auth_block_seconds,
    )


def get_auth_rate_limit_identifier(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host


async def get_current_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_header),
) -> str:
    identifier = get_auth_rate_limit_identifier(request)
    limiter = get_failed_auth_limiter()

    if limiter.is_blocked(identifier):
        raise ApiKeyRateLimitException()

    if not api_key:
        limiter.record_failure(identifier)
        raise InvalidApiKeyException()

    if not get_api_key_storage().verify_api_key(api_key):
        limiter.record_failure(identifier)
        raise InvalidApiKeyException()

    limiter.record_success(identifier)
    return api_key
