import hashlib
import re
import secrets
from pathlib import Path
from functools import lru_cache

from src.management.logger import configure_logger
from src.management.settings import get_settings


logger = configure_logger("APIKeyStorage", "yellow")


class APIKeyStorage:
    def __init__(self, env_file_path: str = ".env"):
        self.env_file_path = self._resolve_env_file_path(Path(env_file_path))
        self.settings = get_settings()
        self._api_key: str | None = None

    def get_api_key(self) -> str:
        if self._api_key:
            return self._api_key

        if self.settings.api_key:
            self._api_key = self.settings.api_key
            return self._api_key

        env_key = self._read_from_env_file()
        if env_key:
            self._api_key = env_key
            return self._api_key

        api_key = self._generate_api_key()
        self._write_to_env_file(api_key)
        self._api_key = api_key
        return api_key

    def _generate_api_key(self) -> str:
        return secrets.token_urlsafe(32)

    def _read_from_env_file(self) -> str | None:
        if not self.env_file_path.exists():
            return None

        try:
            with open(self.env_file_path, "r") as file_handle:
                for line in file_handle:
                    line = line.strip()
                    if line.startswith("API_KEY="):
                        match = re.match(r'API_KEY=["\']?([^"\']*)["\']?', line)
                        if match:
                            value = match.group(1).strip()
                            if value:
                                return value
        except Exception as exc:
            logger.warning(f"Failed to read API_KEY from .env: {exc}")

        return None

    def _write_to_env_file(self, api_key: str) -> None:
        try:
            self.env_file_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.env_file_path.exists():
                with open(self.env_file_path, "w") as file_handle:
                    file_handle.write(f"API_KEY={api_key}\n")
                return

            with open(self.env_file_path, "r") as file_handle:
                lines = file_handle.readlines()

            replaced = False
            updated_lines: list[str] = []
            for line in lines:
                if line.strip().startswith("API_KEY="):
                    updated_lines.append(f"API_KEY={api_key}\n")
                    replaced = True
                else:
                    updated_lines.append(line)

            if not replaced:
                if updated_lines and not updated_lines[-1].endswith("\n"):
                    updated_lines[-1] = updated_lines[-1] + "\n"
                updated_lines.append(f"API_KEY={api_key}\n")

            with open(self.env_file_path, "w") as file_handle:
                file_handle.writelines(updated_lines)
        except Exception as exc:
            logger.warning(f"Failed to write API_KEY to .env: {exc}")

    def verify_api_key(self, provided_key: str) -> bool:
        stored_key = self.get_api_key()
        provided_digest = hashlib.sha256(provided_key.encode("utf-8")).digest()
        stored_digest = hashlib.sha256(stored_key.encode("utf-8")).digest()
        return secrets.compare_digest(provided_digest, stored_digest)

    def _resolve_env_file_path(self, env_file_path: Path) -> Path:
        if env_file_path.is_absolute():
            return env_file_path

        cwd_candidate = Path.cwd() / env_file_path
        module_candidate = Path(__file__).resolve().parents[2] / env_file_path

        if cwd_candidate.exists():
            return cwd_candidate
        if module_candidate.exists():
            return module_candidate
        return module_candidate
    
@lru_cache
def get_api_key_storage() -> APIKeyStorage:
    return APIKeyStorage()
