from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlsplit

import httpx

from src.management.logger import configure_logger
from src.management.settings import get_settings
from src.services.host_service import HostService
from src.services.management.protocol_factory import (
    create_protocol_service,
    get_active_protocol_name,
    get_available_protocols,
    get_protocol_config,
)


logger = configure_logger("PeersService", "cyan")


class PeersService:
    def __init__(self):
        self.settings = get_settings()
        try:
            self.host_service = HostService()
        except Exception as exc:
            logger.warning(f"HostService is unavailable: {exc}")
            self.host_service = None

    def _get_service(self, protocol: str):
        try:
            return create_protocol_service(protocol)
        except ValueError as exc:
            logger.error(str(exc))
            raise

    async def create_active_peer(self, app_type: str) -> dict:
        protocol = get_active_protocol_name()
        return await self.create_peer(protocol=protocol, app_type=app_type)

    async def list_active_peers(
        self,
        app_type: str | None = None,
        online_only: bool = False,
    ) -> tuple[str, list[dict]]:
        if app_type and app_type not in {"amnezia_vpn", "amnezia_wg"}:
            raise ValueError(f"Invalid app_type: {app_type}")

        protocol = get_active_protocol_name()
        peers = await self.get_peers(protocol)
        filtered_peers = []
        for peer in peers:
            if app_type and peer.get("app_type") != app_type:
                continue
            if online_only and not peer.get("online"):
                continue
            filtered_peers.append(peer)
        return protocol, filtered_peers

    async def update_active_peer(self, public_key: str, app_type: str) -> dict:
        protocol = get_active_protocol_name()
        service = self._get_service(protocol)
        peers_data = await service.get_peers()

        old_peer = None
        for peer in peers_data:
            if peer["public_key"] == public_key:
                old_peer = peer
                break

        if not old_peer:
            raise LookupError(f"Peer {public_key[:16]}... not found")

        old_allocated_ip = (
            old_peer["allowed_ips"][0]
            if old_peer.get("allowed_ips")
            else None
        )

        await service.delete_peer(public_key)
        result = await service.create_peer(
            app_type=app_type,
            allocated_ip=old_allocated_ip,
        )

        return {
            "old_public_key": public_key,
            "new_public_key": result["public_key"],
            "allocated_ip": result["allocated_ip"],
            "app_type": result["app_type"],
            "protocol": result["protocol"],
            "config": result["config"],
        }

    async def delete_active_peer(self, public_key: str) -> bool:
        protocol = get_active_protocol_name()
        return await self.delete_peer(protocol=protocol, public_key=public_key)

    async def create_peer(
        self,
        protocol: str,
        app_type: str,
        allocated_ip: str | None = None,
    ) -> dict:
        service = self._get_service(protocol)
        return await service.create_peer(app_type=app_type, allocated_ip=allocated_ip)

    async def delete_peer(self, protocol: str, public_key: str) -> bool:
        service = self._get_service(protocol)
        return await service.delete_peer(public_key=public_key)

    async def get_peers(self, protocol: str) -> list[dict]:
        service = self._get_service(protocol)
        return await service.get_peers()

    async def get_peer_status(self, protocol: str, public_key: str) -> dict:
        peer = await self._get_peer(protocol, public_key)
        return {
            "public_key": peer["public_key"],
            "endpoint": peer.get("endpoint"),
            "last_handshake": peer.get("last_handshake"),
            "online": peer.get("online", False),
        }

    async def get_peers_status(
        self,
        protocol: str,
        online_only: bool | None = None,
    ) -> list[dict]:
        peers = await self.get_peers(protocol)
        if online_only is True:
            peers = [peer for peer in peers if peer.get("online", False)]
        if online_only is False:
            peers = [peer for peer in peers if not peer.get("online", False)]
        return [
            {
                "public_key": peer["public_key"],
                "endpoint": peer.get("endpoint"),
                "last_handshake": peer.get("last_handshake"),
                "online": peer.get("online", False),
            }
            for peer in peers
        ]

    async def get_peer_traffic(self, protocol: str, public_key: str) -> dict:
        peer = await self._get_peer(protocol, public_key)
        return self._to_peer_traffic(peer)

    async def get_all_peers_traffic(self, protocol: str) -> dict[str, dict]:
        peers = await self.get_peers(protocol)
        return {
            peer["public_key"]: self._to_peer_traffic(peer)
            for peer in peers
        }

    async def get_total_traffic(self, protocol: str) -> dict[str, int]:
        peers = await self.get_peers(protocol)
        return self._build_total_traffic(peers)

    async def get_status_snapshot(self, protocol: str) -> dict:
        peers = await self.get_peers(protocol)
        container_name, container_status = await self._get_container_state(protocol)
        return {
            "protocol": protocol,
            "container_name": container_name,
            "container_status": container_status,
            "peers": peers,
            "server_traffic": self._build_total_traffic(peers),
        }

    async def sync_peers_status(
        self,
        central_api_url: str | None = None,
        central_api_key: str | None = None,
        protocols: list[str] | None = None,
    ) -> int:
        sync_url = (central_api_url or self.settings.central_api_url or "").strip()
        sync_api_key = (central_api_key or self.settings.central_api_key or "").strip()

        if not sync_url or not sync_api_key:
            logger.debug(
                "Sync skipped: CENTRAL_API_URL or CENTRAL_API_KEY is not configured"
            )
            return 0

        # Validate the sync destination before attaching the central API key.
        sync_base_url = self._validate_sync_url(sync_url)
        target_protocols = protocols or get_available_protocols()
        payloads = []

        for protocol in target_protocols:
            snapshot = await self.get_status_snapshot(protocol)
            snapshot["sync_timestamp"] = datetime.now(timezone.utc).isoformat()
            payloads.append(snapshot)

        if not payloads:
            logger.debug("No protocols to sync")
            return 0

        headers = {"X-API-Key": sync_api_key}

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            for payload in payloads:
                response = await client.post(
                    f"{sync_base_url}/clusters/sync",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()

        logger.debug(f"Synced peer status for {len(payloads)} protocol(s)")
        return len(payloads)

    def _validate_sync_url(self, sync_url: str) -> str:
        try:
            parsed = urlsplit(sync_url)
        except ValueError as exc:
            raise ValueError("CENTRAL_API_URL is not a valid URL") from exc

        if parsed.scheme not in {"http", "https"}:
            raise ValueError("CENTRAL_API_URL must use http or https")
        if not parsed.hostname:
            raise ValueError("CENTRAL_API_URL must include a host")
        if parsed.username or parsed.password:
            raise ValueError("CENTRAL_API_URL must not include credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("CENTRAL_API_URL must not include query or fragment parts")
        if not self.settings.development and parsed.scheme != "https":
            raise ValueError("CENTRAL_API_URL must use https outside development")

        host = self._normalize_hostname(parsed.hostname)
        allowed_hosts = self._get_central_api_allowed_hosts()
        if not allowed_hosts:
            raise ValueError(
                "CENTRAL_API_ALLOWED_HOSTS must include the central API host "
                "when sync is enabled"
            )
        if not any(
            self._host_matches_allowed_pattern(host, allowed)
            for allowed in allowed_hosts
        ):
            raise ValueError("CENTRAL_API_URL host is not allowed for central sync")

        return sync_url.rstrip("/")

    def _get_central_api_allowed_hosts(self) -> set[str]:
        configured_hosts = self.settings.central_api_allowed_hosts or ""
        return {
            self._normalize_hostname(host)
            for host in configured_hosts.split(",")
            if host.strip()
        }

    @staticmethod
    def _normalize_hostname(host: str) -> str:
        return host.strip().rstrip(".").lower()

    @staticmethod
    def _host_matches_allowed_pattern(host: str, allowed_host: str) -> bool:
        if allowed_host.startswith("*."):
            suffix = allowed_host[1:]
            return host.endswith(suffix) and host != allowed_host[2:]
        return host == allowed_host

    async def _get_peer(self, protocol: str, public_key: str) -> dict:
        peers = await self.get_peers(protocol)
        for peer in peers:
            if peer.get("public_key") == public_key:
                return peer
        raise ValueError(f"Peer {public_key} not found for protocol {protocol}")

    def _to_peer_traffic(self, peer: dict) -> dict:
        return {
            "public_key": peer["public_key"],
            "endpoint": peer.get("endpoint"),
            "allowed_ips": peer.get("allowed_ips", []),
            "last_handshake": peer.get("last_handshake"),
            "rx_bytes": int(peer.get("rx_bytes", 0)),
            "tx_bytes": int(peer.get("tx_bytes", 0)),
            "online": bool(peer.get("online", False)),
            "persistent_keepalive": int(peer.get("persistent_keepalive", 0)),
        }

    def _build_total_traffic(self, peers: list[dict]) -> dict[str, int]:
        total_rx = sum(int(peer.get("rx_bytes", 0)) for peer in peers)
        total_tx = sum(int(peer.get("tx_bytes", 0)) for peer in peers)
        return {
            "total_rx_bytes": total_rx,
            "total_tx_bytes": total_tx,
            "total_peers": len(peers),
            "online_peers": sum(1 for peer in peers if peer.get("online", False)),
        }

    async def _get_container_state(self, protocol: str) -> tuple[str | None, str]:
        protocol_config = get_protocol_config(protocol)
        container_name = protocol_config.get("container_name")
        if not container_name:
            return None, "unknown"
        if self.host_service is None:
            return container_name, "unknown"
        is_running = await self.host_service.is_container_running(container_name)
        return container_name, "running" if is_running else "stopped"

@lru_cache
def get_peers_service() -> PeersService:
    return PeersService()
