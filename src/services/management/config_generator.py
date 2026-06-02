from abc import ABC, abstractmethod
from typing import Any


class ConfigGenerator(ABC):
    @abstractmethod
    def generate_vpn_config(self, **kwargs: Any) -> str:
        raise NotImplementedError

    @abstractmethod
    def decode_vpn_link(self, vpn_link: str) -> dict:
        raise NotImplementedError
