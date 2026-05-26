import hashlib
import secrets
from functools import lru_cache

from src.management.settings import get_settings


class APIKeyStorage:
    def __init__(self) -> None:
        self._api_key: str | None = None

    def get_api_key(self) -> str:
        if self._api_key:
            return self._api_key

        api_key = get_settings().api_key.strip()
        if not api_key:
            raise RuntimeError("API_KEY must be configured")
        self._api_key = api_key
        return api_key

    def verify_api_key(self, provided_key: str) -> bool:
        stored_key = self.get_api_key()
        provided_digest = hashlib.sha256(provided_key.encode("utf-8")).digest()
        stored_digest = hashlib.sha256(stored_key.encode("utf-8")).digest()
        return secrets.compare_digest(provided_digest, stored_digest)


@lru_cache
def get_api_key_storage() -> APIKeyStorage:
    return APIKeyStorage()
