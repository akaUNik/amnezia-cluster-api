import yaml
import importlib
from pathlib import Path
from typing import Any, Type

from src.management.logger import configure_logger
from src.management.settings import get_settings
from src.services.management.base_protocol_service import BaseProtocolService


logger = configure_logger("ProtocolFactory", "cyan")

ProtocolConfig = dict[str, Any]

_protocol_config: dict[str, ProtocolConfig] = {}


def clear_protocol_config() -> None:
    _protocol_config.clear()


def _ensure_protocol_config_loaded() -> None:
    if not _protocol_config:
        load_protocol_config()


def _normalize_protocol_name(protocol_name: str) -> str:
    return protocol_name.lower()


def _get_protocol_or_raise(protocol_name: str) -> ProtocolConfig:
    _ensure_protocol_config_loaded()

    normalized_name = _normalize_protocol_name(protocol_name)
    if normalized_name not in _protocol_config:
        available = get_available_protocols()
        raise ValueError(
            f"Unsupported protocol: {protocol_name}. Available protocols: {available}"
        )

    return _protocol_config[normalized_name]


def load_protocol_config(config_path: str | None = None) -> None:
    settings = get_settings()
    if config_path is None:
        config_path = settings.protocol_config_path

    config_file = Path(config_path)
    clear_protocol_config()
    if not config_file.exists():
        raise FileNotFoundError(f"Protocol config file not found: {config_file.resolve()}")

    try:
        with open(config_file, "r") as file_handle:
            config = yaml.safe_load(file_handle) or {}
            protocols = config.get("protocols", {})
            if not protocols:
                raise ValueError(
                    f"Protocol config {config_file.resolve()} does not define any protocols"
                )

            normalized_protocols = {
                str(name).lower(): value for name, value in protocols.items()
            }
            for protocol_name, protocol_cfg in normalized_protocols.items():
                if not isinstance(protocol_cfg, dict):
                    raise ValueError(
                        f"Protocol {protocol_name} config must be a mapping"
                    )
                if not protocol_cfg.get("service_class"):
                    raise ValueError(
                        f"Protocol {protocol_name} is missing required field: service_class"
                    )

            _protocol_config.update(normalized_protocols)
            logger.info(f"Loaded {len(_protocol_config)} protocol(s) from {config_path}")
    except Exception as exc:
        logger.error(f"Failed to load protocol config from {config_path}: {exc}")
        raise


def reload_protocol_config(config_path: str | None = None) -> None:
    load_protocol_config(config_path=config_path)


def get_available_protocols() -> list[str]:
    _ensure_protocol_config_loaded()

    return [
        name
        for name, config in _protocol_config.items()
        if config.get("enabled", True)
    ]


def get_active_protocol_name() -> str:
    available = get_available_protocols()
    if not available:
        raise ValueError("No enabled protocols configured")
    return available[0]


def get_protocol_config(protocol_name: str) -> dict:
    return _get_protocol_or_raise(protocol_name)


def create_protocol_service(protocol_name: str) -> BaseProtocolService:
    normalized_name = _normalize_protocol_name(protocol_name)
    config = _get_protocol_or_raise(protocol_name)
    if not config.get("enabled", True):
        raise ValueError(f"Protocol {protocol_name} is disabled")

    try:
        service_class_path = config["service_class"]
        module_path, class_name = service_class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        service_class: Type[BaseProtocolService] = getattr(module, class_name)

        instance = service_class(protocol_name=normalized_name)
        logger.debug(f"Created service instance for protocol: {normalized_name}")
        return instance
    except ImportError as exc:
        logger.error(f"Failed to import service class for {protocol_name}: {exc}")
        raise ValueError(f"Failed to load protocol service for {protocol_name}: {exc}")
    except AttributeError as exc:
        logger.error(f"Service class not found for {protocol_name}: {exc}")
        raise ValueError(f"Service class not found for {protocol_name}: {exc}")
    except Exception as exc:
        logger.error(f"Failed to create service instance for {protocol_name}: {exc}")
        raise ValueError(f"Failed to create protocol service for {protocol_name}: {exc}")
