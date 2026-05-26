from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.management.container_connection import ContainerConnection


class BaseProtocolService(ABC):
    def __init__(self, protocol_name: str) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def protocol_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def connection(self) -> "ContainerConnection":
        raise NotImplementedError

    @abstractmethod
    async def get_peers(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    async def create_peer(
        self,
        app_type: str,
        allocated_ip: str | None = None,
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def delete_peer(self, public_key: str) -> bool:
        raise NotImplementedError
