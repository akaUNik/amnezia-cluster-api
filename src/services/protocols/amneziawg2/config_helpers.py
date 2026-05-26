import ipaddress
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any


AMNEZIA_VPN_APP_TYPE = "amnezia_vpn"
AMNEZIA_WG_APP_TYPE = "amnezia_wg"
APP_TYPE_METADATA_KEY = "AppType"
AWG_PARAM_KEYS: tuple[str, ...] = (
    "H1",
    "H2",
    "H3",
    "H4",
    "I1",
    "I2",
    "I3",
    "I4",
    "I5",
    "Jc",
    "Jmax",
    "Jmin",
    "S1",
    "S2",
    "S3",
    "S4",
)

PEER_SECTION_PATTERN = re.compile(
    r"(?ms)^\s*\[Peer\]\s*$.*?(?=^\s*\[[^\]]+\]\s*$|\Z)"
)


def normalize_app_type(app_type: object) -> str:
    value = getattr(app_type, "value", app_type)
    normalized = str(value).strip().lower()
    if normalized in {"amnezia_vpn", "vpn"}:
        return AMNEZIA_VPN_APP_TYPE
    if normalized in {"amnezia_wg", "wg", "amneziawg"}:
        return AMNEZIA_WG_APP_TYPE
    raise ValueError(f"Unsupported app_type: {app_type}")


def extract_awg_params(wg_config: str, defaults: dict[str, Any]) -> dict[str, Any]:
    params = defaults.copy()
    for key in AWG_PARAM_KEYS:
        pattern = rf"^[ \t]*#?[ \t]*{key}[ \t]*=[ \t]*([^#\n]*)"
        match = re.search(pattern, wg_config, flags=re.MULTILINE)
        if match:
            params[key] = match.group(1).strip()
    return params


def remove_peer_from_raw_config(config: str, public_key: str) -> str:
    result_parts: list[str] = []
    last_index = 0
    removed_any = False

    for match in PEER_SECTION_PATTERN.finditer(config):
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


def build_peer_section(
    *,
    public_key: str,
    allowed_ip: str,
    preshared_key: str,
    app_type: str,
) -> str:
    return (
        "\n[Peer]\n"
        f"# {APP_TYPE_METADATA_KEY} = {app_type}\n"
        f"PublicKey = {public_key}\n"
        f"PresharedKey = {preshared_key}\n"
        f"AllowedIPs = {allowed_ip}\n"
    )


def extract_peer_app_types(
    wg_config: str,
    default_app_type: str,
    normalizer: Callable[[object], str] = normalize_app_type,
) -> dict[str, str]:
    app_types_by_public_key: dict[str, str] = {}

    for match in PEER_SECTION_PATTERN.finditer(wg_config):
        section = match.group(0)
        public_key_match = re.search(
            r"^\s*PublicKey\s*=\s*(\S+)\s*$",
            section,
            flags=re.MULTILINE,
        )
        if not public_key_match:
            continue

        metadata_match = re.search(
            rf"^\s*#?\s*{APP_TYPE_METADATA_KEY}\s*=\s*(\S+)\s*$",
            section,
            flags=re.MULTILINE,
        )
        if metadata_match:
            raw_app_type = metadata_match.group(1).strip()
            try:
                normalized_app_type = normalizer(raw_app_type)
            except ValueError:
                normalized_app_type = default_app_type
        else:
            normalized_app_type = default_app_type

        app_types_by_public_key[public_key_match.group(1).strip()] = normalized_app_type

    return app_types_by_public_key


def parse_wg_dump(
    dump_output: str,
    *,
    peer_online_threshold_seconds: int,
    now: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    peers: dict[str, dict[str, Any]] = {}
    lines = dump_output.strip().split("\n")
    if not lines:
        return peers

    current_time = now or datetime.now()
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
            time_diff = (current_time - last_handshake).total_seconds()
            online = time_diff < peer_online_threshold_seconds

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


def extract_interface_address(wg_config: str) -> str:
    subnet_match = re.search(r"Address\s*=\s*([\d\.]+/\d+)", wg_config)
    if not subnet_match:
        raise ValueError("Could not find subnet in protocol config")
    return subnet_match.group(1)


def extract_listen_port(wg_config: str) -> int:
    match = re.search(
        r"\[Interface\][\s\S]*?ListenPort\s*=\s*(\d+)",
        wg_config,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("ListenPort not found in protocol config")
    return int(match.group(1))


def default_subnet_address(wg_config: str, fallback: str) -> str:
    subnet_match = re.search(r"Address\s*=\s*([\d\.]+)/\d+", wg_config)
    if not subnet_match:
        return fallback
    subnet_base = subnet_match.group(1).rsplit(".", 1)[0]
    return f"{subnet_base}.0"


def allocate_ip_address(wg_config: str, dump_output: str) -> str:
    network = ipaddress.IPv4Network(extract_interface_address(wg_config), strict=False)
    used_ips = set()

    peers = parse_wg_dump(
        dump_output,
        peer_online_threshold_seconds=0,
    )
    for peer in peers.values():
        for allowed_ip in peer["allowed_ips"]:
            if "/" in allowed_ip:
                used_ips.add(ipaddress.IPv4Address(allowed_ip.split("/", 1)[0]))

    for ip in network.hosts():
        if ip not in used_ips and ip != network.network_address + 1:
            return f"{ip}/32"

    raise ValueError("No available IP addresses in subnet")
