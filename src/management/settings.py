from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    development: bool

    server_public_host: str
    server_display_name: str = "AmneziaWG Server"

    api_key: str | None = None
    api_key_failed_auth_limit: int = 10
    api_key_failed_auth_window_seconds: int = 60
    api_key_failed_auth_block_seconds: int = 60

    central_api_url: str | None = None
    central_api_key: str | None = None
    central_api_allowed_hosts: str | None = None
    sync_interval_seconds: int = 60
    protocol_config_path: str = "src/management/protocols.yaml"
    persistent_keepalive_seconds: int = 25
    peer_online_threshold_seconds: int = 180
    
    model_config = SettingsConfigDict(
        env_file = ".env",
        extra="ignore"
    )

@lru_cache
def get_settings():
    return Settings()
