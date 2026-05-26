from typing import Any

from src.management.logger import configure_logger
from src.management.settings import get_settings
from src.services.management.base_protocol_service import BaseProtocolService
from src.services.protocols.amneziawg2.amneziawg2_config_generator import (
    AmneziaWG2ConfigGenerator,
)
from src.services.protocols.amneziawg2.amneziawg2_connection import AmneziaWG2Connection
from src.services.protocols.amneziawg2.config_helpers import (
    AMNEZIA_VPN_APP_TYPE as DEFAULT_AMNEZIA_VPN_APP_TYPE,
    AMNEZIA_WG_APP_TYPE as DEFAULT_AMNEZIA_WG_APP_TYPE,
    APP_TYPE_METADATA_KEY as DEFAULT_APP_TYPE_METADATA_KEY,
    allocate_ip_address,
    build_peer_section,
    default_subnet_address,
    extract_awg_params,
    extract_listen_port,
    extract_peer_app_types,
    normalize_app_type,
    parse_wg_dump,
    remove_peer_from_raw_config,
)


logger = configure_logger("AmneziaWG2Service", "green")


class AmneziaWG2Service(BaseProtocolService):
    AMNEZIA_VPN_APP_TYPE = DEFAULT_AMNEZIA_VPN_APP_TYPE
    AMNEZIA_WG_APP_TYPE = DEFAULT_AMNEZIA_WG_APP_TYPE
    APP_TYPE_METADATA_KEY = DEFAULT_APP_TYPE_METADATA_KEY
    AMNEZIAWG_CLIENT_TEMPLATE = (
        "[Interface]\n"
        "Address = {CLIENT_ADDRESS}/32\n"
        "DNS = {PRIMARY_DNS}, {SECONDARY_DNS}\n"
        "PrivateKey = {CLIENT_PRIVATE_KEY}\n"
        "Jc = {JC}\n"
        "Jmin = {JMIN}\n"
        "Jmax = {JMAX}\n"
        "S1 = {S1}\n"
        "S2 = {S2}\n"
        "S3 = {S3}\n"
        "S4 = {S4}\n"
        "H1 = {H1}\n"
        "H2 = {H2}\n"
        "H3 = {H3}\n"
        "H4 = {H4}\n"
        "I1 = {I1}\n"
        "I2 = {I2}\n"
        "I3 = {I3}\n"
        "I4 = {I4}\n"
        "I5 = {I5}\n\n"
        "[Peer]\n"
        "PublicKey = {SERVER_PUBLIC_KEY}\n"
        "PresharedKey = {PRESHARED_KEY}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "{ENDPOINT_LINE}"
        "PersistentKeepalive = {KEEPALIVE}\n"
    )

    def __init__(self, protocol_name: str = "amneziawg2"):
        self.settings = get_settings()
        self._protocol_name = protocol_name
        self._connection = AmneziaWG2Connection(protocol_name=protocol_name)
        self.protocol_config = self._connection.protocol_config
        self.config_generator = AmneziaWG2ConfigGenerator()
        self._awg_params_defaults = dict(self.protocol_config.get("awg_junk_params", {}))
        self._default_app_type = self._resolve_default_app_type()

    @property
    def protocol_name(self) -> str:
        return self._protocol_name

    @property
    def connection(self) -> AmneziaWG2Connection:
        return self._connection

    async def get_peers(self) -> list[dict]:
        dump_output = await self.connection.get_peers_dump()
        peers_data = self._parse_wg_dump(dump_output)
        wg_config = await self.connection.read_protocol_config()
        app_types_by_public_key = self._extract_peer_app_types(wg_config)

        peers = []
        for public_key, data in peers_data.items():
            peers.append(
                {
                    "public_key": public_key,
                    "app_type": app_types_by_public_key.get(public_key, self._default_app_type),
                    "endpoint": data["endpoint"],
                    "allowed_ips": data["allowed_ips"],
                    "last_handshake": (
                        data["last_handshake"].isoformat()
                        if data["last_handshake"]
                        else None
                    ),
                    "rx_bytes": data["rx_bytes"],
                    "tx_bytes": data["tx_bytes"],
                    "online": data["online"],
                    "persistent_keepalive": data["persistent_keepalive"],
                }
            )

        return peers

    async def create_peer(
        self,
        app_type: str,
        allocated_ip: str | None = None,
    ) -> dict:
        normalized_app_type = self._normalize_app_type(app_type)
        private_key = await self.connection.generate_private_key()
        public_key = await self.connection.generate_public_key(private_key)

        if not allocated_ip:
            allocated_ip = await self._allocate_ip_address()
        if "/" not in allocated_ip:
            allocated_ip = f"{allocated_ip}/32"

        server_port = await self._get_server_port()
        endpoint = f"{self.settings.server_public_host}:{server_port}"

        await self._add_peer_to_config(public_key, allocated_ip, normalized_app_type)
        await self.connection.sync_config()

        config_payload = await self._generate_config_payload(
            app_type=normalized_app_type,
            private_key=private_key,
            public_key=public_key,
            allowed_ip=allocated_ip,
            server_port=server_port,
        )

        logger.info(f"Peer created for protocol {self.protocol_name} with IP {allocated_ip}")

        return {
            "protocol": self.protocol_name,
            "app_type": normalized_app_type,
            "config": config_payload["config"],
            "public_key": public_key,
            "private_key": private_key,
            "allocated_ip": allocated_ip,
            "endpoint": endpoint,
        }

    async def delete_peer(self, public_key: str) -> bool:
        wg_config = await self.connection.read_protocol_config()
        updated_config = self._remove_peer_from_raw_config(wg_config, public_key)

        if updated_config == wg_config:
            return False

        await self.connection.write_protocol_config(updated_config)
        await self.connection.sync_config()
        logger.info(f"Peer {public_key} deleted from protocol {self.protocol_name}")
        return True

    async def _add_peer_to_config(self, public_key: str, allowed_ip: str, app_type: str) -> None:
        wg_config = await self.connection.read_protocol_config()
        psk = await self.connection.read_preshared_key()
        peer_section = build_peer_section(
            public_key=public_key,
            allowed_ip=allowed_ip,
            preshared_key=psk,
            app_type=app_type,
        )
        await self.connection.write_protocol_config(wg_config + peer_section)

    def _remove_peer_from_raw_config(self, config: str, public_key: str) -> str:
        return remove_peer_from_raw_config(config, public_key)

    async def _allocate_ip_address(self) -> str:
        wg_config = await self.connection.read_protocol_config()
        dump_output = await self.connection.get_peers_dump()
        return allocate_ip_address(wg_config, dump_output)

    async def _get_server_port(self) -> int:
        wg_config = await self.connection.read_protocol_config()
        return extract_listen_port(wg_config)

    async def _generate_config_uri(
        self,
        private_key: str,
        public_key: str,
        allowed_ip: str,
        server_port: int,
    ) -> str:
        server_public_key = await self.connection.read_server_public_key()
        psk = await self.connection.read_preshared_key()
        wg_config = await self.connection.read_protocol_config()
        awg_params = self._extract_awg_params(wg_config)

        subnet_address = default_subnet_address(
            wg_config,
            self.protocol_config.get("default_subnet_address", "10.8.1.0"),
        )

        client_ip = allowed_ip if allowed_ip.endswith("/32") else f"{allowed_ip}/32"

        config_uri = self.config_generator.generate_vpn_config(
            client_private_key=private_key,
            client_public_key=public_key,
            server_public_key=server_public_key,
            psk=psk,
            client_ip=client_ip,
            awg_params=awg_params,
            server_endpoint=self.settings.server_public_host,
            server_port=server_port,
            primary_dns=self.protocol_config.get("primary_dns", "1.1.1.1"),
            secondary_dns=self.protocol_config.get("secondary_dns", "1.0.0.1"),
            container_name=self.protocol_config.get("container_name", self.protocol_name),
            description=self.settings.server_display_name,
            subnet_address=subnet_address,
            persistent_keepalive=self.settings.persistent_keepalive_seconds,
        )

        self.config_generator.decode_vpn_link(config_uri)
        return config_uri

    async def _generate_text_config(
        self,
        private_key: str,
        allowed_ip: str,
        server_port: int,
    ) -> str:
        server_public_key = await self.connection.read_server_public_key()
        psk = await self.connection.read_preshared_key()
        wg_config = await self.connection.read_protocol_config()
        awg_params = self._extract_awg_params(wg_config)
        endpoint_line = f"Endpoint = {self.settings.server_public_host}:{server_port}\n"

        return self.AMNEZIAWG_CLIENT_TEMPLATE.format(
            CLIENT_ADDRESS=allowed_ip.split("/")[0],
            PRIMARY_DNS=self.protocol_config.get("primary_dns", "1.1.1.1"),
            SECONDARY_DNS=self.protocol_config.get("secondary_dns", "1.0.0.1"),
            CLIENT_PRIVATE_KEY=private_key,
            JC=awg_params.get("Jc", ""),
            JMIN=awg_params.get("Jmin", ""),
            JMAX=awg_params.get("Jmax", ""),
            S1=awg_params.get("S1", ""),
            S2=awg_params.get("S2", ""),
            S3=awg_params.get("S3", ""),
            S4=awg_params.get("S4", ""),
            H1=awg_params.get("H1", ""),
            H2=awg_params.get("H2", ""),
            H3=awg_params.get("H3", ""),
            H4=awg_params.get("H4", ""),
            I1=awg_params.get("I1", ""),
            I2=awg_params.get("I2", ""),
            I3=awg_params.get("I3", ""),
            I4=awg_params.get("I4", ""),
            I5=awg_params.get("I5", ""),
            SERVER_PUBLIC_KEY=server_public_key,
            PRESHARED_KEY=psk,
            ENDPOINT_LINE=endpoint_line,
            KEEPALIVE=str(self.settings.persistent_keepalive_seconds),
        )

    async def _generate_config_payload(
        self,
        app_type: str,
        private_key: str,
        public_key: str,
        allowed_ip: str,
        server_port: int,
    ) -> dict:
        if app_type == self.AMNEZIA_VPN_APP_TYPE:
            return {
                "type": self.AMNEZIA_VPN_APP_TYPE,
                "config": await self._generate_config_uri(
                    private_key=private_key,
                    public_key=public_key,
                    allowed_ip=allowed_ip,
                    server_port=server_port,
                ),
            }

        if app_type == self.AMNEZIA_WG_APP_TYPE:
            return {
                "type": self.AMNEZIA_WG_APP_TYPE,
                "config": await self._generate_text_config(
                    private_key=private_key,
                    allowed_ip=allowed_ip,
                    server_port=server_port,
                ),
            }

        raise ValueError(f"Unsupported app_type: {app_type}")

    def _extract_awg_params(self, wg_config: str) -> dict:
        return extract_awg_params(wg_config, self._awg_params_defaults)

    def _parse_wg_dump(self, dump_output: str) -> dict[str, dict[str, Any]]:
        return parse_wg_dump(
            dump_output,
            peer_online_threshold_seconds=self.settings.peer_online_threshold_seconds,
        )

    def _normalize_app_type(self, app_type: object) -> str:
        return normalize_app_type(app_type)

    def _extract_peer_app_types(self, wg_config: str) -> dict[str, str]:
        return extract_peer_app_types(
            wg_config,
            self._default_app_type,
            self._normalize_app_type,
        )

    def _resolve_default_app_type(self) -> str:
        raw_default = self.protocol_config.get("default_app_type", self.AMNEZIA_WG_APP_TYPE)
        try:
            return self._normalize_app_type(str(raw_default))
        except ValueError:
            return self.AMNEZIA_WG_APP_TYPE
