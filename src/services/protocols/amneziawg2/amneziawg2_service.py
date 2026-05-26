import ipaddress
import re
from datetime import datetime
from typing import Any

from src.management.logger import configure_logger
from src.management.settings import get_settings
from src.services.management.base_protocol_service import BaseProtocolService
from src.services.protocols.amneziawg2.amneziawg2_config_generator import (
    AmneziaWG2ConfigGenerator,
)
from src.services.protocols.amneziawg2.amneziawg2_connection import AmneziaWG2Connection


logger = configure_logger("AmneziaWG2Service", "green")


class AmneziaWG2Service(BaseProtocolService):
    AMNEZIA_VPN_APP_TYPE = "amnezia_vpn"
    AMNEZIA_WG_APP_TYPE = "amnezia_wg"
    APP_TYPE_METADATA_KEY = "AppType"
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

    async def add_peer_to_config(self, public_key: str, allowed_ip: str) -> None:
        await self._add_peer_to_config(public_key, allowed_ip, self._default_app_type)

    async def remove_peer_from_config(self, public_key: str) -> bool:
        return await self.delete_peer(public_key)

    async def _add_peer_to_config(self, public_key: str, allowed_ip: str, app_type: str) -> None:
        wg_config = await self.connection.read_protocol_config()
        psk = await self.connection.read_preshared_key()
        peer_section = (
            f"\n[Peer]\n"
            f"# {self.APP_TYPE_METADATA_KEY} = {app_type}\n"
            f"PublicKey = {public_key}\n"
            f"PresharedKey = {psk}\n"
            f"AllowedIPs = {allowed_ip}\n"
        )
        await self.connection.write_protocol_config(wg_config + peer_section)

    def _remove_peer_from_raw_config(self, config: str, public_key: str) -> str:
        peer_section_pattern = re.compile(
            r"(?ms)^\s*\[Peer\]\s*$.*?(?=^\s*\[[^\]]+\]\s*$|\Z)"
        )

        result_parts: list[str] = []
        last_index = 0
        removed_any = False

        for match in peer_section_pattern.finditer(config):
            section = match.group(0)
            key_match = re.search(
                r"^\s*PublicKey\s*=\s*(\S+)\s*$",
                section,
                flags=re.MULTILINE,
            )
            if not key_match or key_match.group(1).strip() != public_key:
                continue

            result_parts.append(config[last_index:match.start()])
            last_index = match.end()
            removed_any = True

        if not removed_any:
            return config

        result_parts.append(config[last_index:])
        return "".join(result_parts)

    async def _allocate_ip_address(self) -> str:
        wg_config = await self.connection.read_protocol_config()
        subnet_match = re.search(r"Address\s*=\s*([\d\.]+/\d+)", wg_config)
        if not subnet_match:
            raise ValueError("Could not find subnet in protocol config")

        network = ipaddress.IPv4Network(subnet_match.group(1), strict=False)
        used_ips = set()

        dump_output = await self.connection.get_peers_dump()
        peers = self._parse_wg_dump(dump_output)
        for peer in peers.values():
            for allowed_ip in peer["allowed_ips"]:
                if "/" in allowed_ip:
                    used_ips.add(ipaddress.IPv4Address(allowed_ip.split("/", 1)[0]))

        for ip in network.hosts():
            if ip not in used_ips and ip != network.network_address + 1:
                return f"{ip}/32"

        raise ValueError("No available IP addresses in subnet")

    async def _get_server_port(self) -> int:
        wg_config = await self.connection.read_protocol_config()
        match = re.search(
            r"\[Interface\][\s\S]*?ListenPort\s*=\s*(\d+)",
            wg_config,
            re.IGNORECASE,
        )
        if not match:
            raise ValueError("ListenPort not found in protocol config")
        return int(match.group(1))

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

        subnet_match = re.search(r"Address\s*=\s*([\d\.]+)/\d+", wg_config)
        if subnet_match:
            subnet_base = subnet_match.group(1).rsplit(".", 1)[0]
            subnet_address = f"{subnet_base}.0"
        else:
            subnet_address = self.protocol_config.get("default_subnet_address", "10.8.1.0")

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
        params = self._awg_params_defaults.copy()
        param_mapping = {
            "H1": r"^[ \t]*#?[ \t]*H1[ \t]*=[ \t]*([^#\n]*)",
            "H2": r"^[ \t]*#?[ \t]*H2[ \t]*=[ \t]*([^#\n]*)",
            "H3": r"^[ \t]*#?[ \t]*H3[ \t]*=[ \t]*([^#\n]*)",
            "H4": r"^[ \t]*#?[ \t]*H4[ \t]*=[ \t]*([^#\n]*)",
            "I1": r"^[ \t]*#?[ \t]*I1[ \t]*=[ \t]*([^#\n]*)",
            "I2": r"^[ \t]*#?[ \t]*I2[ \t]*=[ \t]*([^#\n]*)",
            "I3": r"^[ \t]*#?[ \t]*I3[ \t]*=[ \t]*([^#\n]*)",
            "I4": r"^[ \t]*#?[ \t]*I4[ \t]*=[ \t]*([^#\n]*)",
            "I5": r"^[ \t]*#?[ \t]*I5[ \t]*=[ \t]*([^#\n]*)",
            "Jc": r"^[ \t]*#?[ \t]*Jc[ \t]*=[ \t]*([^#\n]*)",
            "Jmin": r"^[ \t]*#?[ \t]*Jmin[ \t]*=[ \t]*([^#\n]*)",
            "Jmax": r"^[ \t]*#?[ \t]*Jmax[ \t]*=[ \t]*([^#\n]*)",
            "S1": r"^[ \t]*#?[ \t]*S1[ \t]*=[ \t]*([^#\n]*)",
            "S2": r"^[ \t]*#?[ \t]*S2[ \t]*=[ \t]*([^#\n]*)",
            "S3": r"^[ \t]*#?[ \t]*S3[ \t]*=[ \t]*([^#\n]*)",
            "S4": r"^[ \t]*#?[ \t]*S4[ \t]*=[ \t]*([^#\n]*)",
        }

        for key, pattern in param_mapping.items():
            match = re.search(pattern, wg_config, flags=re.MULTILINE)
            if match:
                params[key] = match.group(1).strip()

        return params

    def _parse_wg_dump(self, dump_output: str) -> dict[str, dict[str, Any]]:
        peers: dict[str, dict[str, Any]] = {}
        lines = dump_output.strip().split("\n")
        if not lines:
            return peers

        for line in lines[1:]:
            parts = line.split("\t")
            if len(parts) < 8:
                continue

            public_key = parts[0]
            endpoint = parts[2] if parts[2] != "(none)" else None
            allowed_ips = [ip.strip() for ip in parts[3].split(",") if ip.strip()]
            last_handshake_ts = int(parts[4]) if parts[4] != "0" else None
            rx_bytes = int(parts[5])
            tx_bytes = int(parts[6])
            persistent_keepalive = int(parts[7]) if parts[7] != "off" else 0

            last_handshake = None
            if last_handshake_ts:
                last_handshake = datetime.fromtimestamp(last_handshake_ts)

            online = False
            if last_handshake:
                time_diff = (datetime.now() - last_handshake).total_seconds()
                online = time_diff < self.settings.peer_online_threshold_seconds

            peers[public_key] = {
                "endpoint": endpoint,
                "allowed_ips": allowed_ips,
                "last_handshake": last_handshake,
                "rx_bytes": rx_bytes,
                "tx_bytes": tx_bytes,
                "online": online,
                "persistent_keepalive": persistent_keepalive,
            }

        return peers

    def _normalize_app_type(self, app_type: str) -> str:
        value = getattr(app_type, "value", app_type)
        normalized = str(value).strip().lower()
        if normalized in {"amnezia_vpn", "vpn"}:
            return self.AMNEZIA_VPN_APP_TYPE
        if normalized in {"amnezia_wg", "wg", "amneziawg"}:
            return self.AMNEZIA_WG_APP_TYPE
        raise ValueError(f"Unsupported app_type: {app_type}")

    def _extract_peer_app_types(self, wg_config: str) -> dict[str, str]:
        peer_section_pattern = re.compile(
            r"(?ms)^\s*\[Peer\]\s*$.*?(?=^\s*\[[^\]]+\]\s*$|\Z)"
        )
        app_types_by_public_key: dict[str, str] = {}

        for match in peer_section_pattern.finditer(wg_config):
            section = match.group(0)
            public_key_match = re.search(
                r"^\s*PublicKey\s*=\s*(\S+)\s*$",
                section,
                flags=re.MULTILINE,
            )
            if not public_key_match:
                continue

            metadata_match = re.search(
                rf"^\s*#?\s*{self.APP_TYPE_METADATA_KEY}\s*=\s*(\S+)\s*$",
                section,
                flags=re.MULTILINE,
            )
            if metadata_match:
                raw_app_type = metadata_match.group(1).strip()
                try:
                    normalized_app_type = self._normalize_app_type(raw_app_type)
                except ValueError:
                    normalized_app_type = self._default_app_type
            else:
                normalized_app_type = self._default_app_type

            app_types_by_public_key[public_key_match.group(1).strip()] = normalized_app_type

        return app_types_by_public_key

    def _resolve_default_app_type(self) -> str:
        raw_default = self.protocol_config.get("default_app_type", self.AMNEZIA_WG_APP_TYPE)
        try:
            return self._normalize_app_type(str(raw_default))
        except ValueError:
            return self.AMNEZIA_WG_APP_TYPE
