from functools import lru_cache

from src.services.host_service import HostService
from src.services.management.protocol_factory import (
    create_protocol_service,
    get_active_protocol_name,
    get_protocol_config,
)


class ServerNotRunningError(RuntimeError):
    """Raised when a restart is requested for a stopped server container."""


class ServerService:
    def __init__(self, host_service: HostService | None = None) -> None:
        self.host_service = host_service or HostService()

    async def get_status(self) -> dict:
        protocol_name = get_active_protocol_name()
        protocol_config = get_protocol_config(protocol_name)
        container_name = protocol_config["container_name"]
        interface = protocol_config["interface"]

        is_running = await self.host_service.is_container_running(container_name)
        if not is_running:
            return {
                "status": "stopped",
                "container_name": container_name,
                "port": None,
                "interface": interface,
                "protocol": protocol_name,
            }

        port = await self.host_service.get_container_port(container_name, "udp")
        return {
            "status": "running",
            "container_name": container_name,
            "port": port,
            "interface": interface,
            "protocol": protocol_name,
        }

    async def get_traffic(self) -> dict[str, int]:
        protocol_name = get_active_protocol_name()
        service = create_protocol_service(protocol_name)
        peers_data = await service.get_peers()

        return {
            "total_rx_bytes": sum(peer.get("rx_bytes", 0) for peer in peers_data),
            "total_tx_bytes": sum(peer.get("tx_bytes", 0) for peer in peers_data),
            "total_peers": len(peers_data),
            "online_peers": sum(1 for peer in peers_data if peer.get("online", False)),
        }

    async def restart(self) -> dict[str, str]:
        protocol_name = get_active_protocol_name()
        protocol_config = get_protocol_config(protocol_name)
        container_name = protocol_config["container_name"]

        is_running = await self.host_service.is_container_running(container_name)
        if not is_running:
            raise ServerNotRunningError(f"Container {container_name} is not running")

        await self.host_service.restart_container(container_name, timeout=10)
        return {
            "status": "restarted",
            "message": f"Server {container_name} has been restarted successfully",
        }


@lru_cache
def get_server_service() -> ServerService:
    return ServerService()
