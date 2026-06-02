from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services.protocols.amneziawg2.amneziawg2_service import AmneziaWG2Service


@pytest.fixture
def service():
    instance = object.__new__(AmneziaWG2Service)
    instance.settings = SimpleNamespace(peer_online_threshold_seconds=180)
    instance._awg_params_defaults = {"Jc": "5", "Jmin": "10"}
    instance._default_app_type = AmneziaWG2Service.AMNEZIA_WG_APP_TYPE
    return instance


@pytest.mark.parametrize(
    ("raw_app_type", "expected"),
    [
        ("amnezia_vpn", "amnezia_vpn"),
        (" vpn ", "amnezia_vpn"),
        ("amnezia_wg", "amnezia_wg"),
        ("WG", "amnezia_wg"),
        ("amneziawg", "amnezia_wg"),
    ],
)
def test_normalize_app_type_aliases(service, raw_app_type, expected):
    assert service._normalize_app_type(raw_app_type) == expected


def test_normalize_app_type_rejects_unknown_value(service):
    with pytest.raises(ValueError, match="Unsupported app_type"):
        service._normalize_app_type("wireguard")


def test_extract_peer_app_types_reads_metadata_and_defaults_invalid_values(service):
    config = """
[Interface]
Address = 10.8.1.1/24

[Peer]
# AppType = amnezia_vpn
PublicKey = first-key
AllowedIPs = 10.8.1.2/32

[Peer]
# AppType = invalid
PublicKey = second-key
AllowedIPs = 10.8.1.3/32

[Peer]
PublicKey = third-key
AllowedIPs = 10.8.1.4/32
"""

    assert service._extract_peer_app_types(config) == {
        "first-key": "amnezia_vpn",
        "second-key": "amnezia_wg",
        "third-key": "amnezia_wg",
    }


def test_remove_peer_from_raw_config_removes_only_matching_peer_section(service):
    config = """
[Interface]
Address = 10.8.1.1/24

[Peer]
PublicKey = keep-key
AllowedIPs = 10.8.1.2/32

[Peer]
# AppType = amnezia_vpn
PublicKey = remove-key
AllowedIPs = 10.8.1.3/32

[Peer]
PublicKey = also-keep-key
AllowedIPs = 10.8.1.4/32
"""

    updated = service._remove_peer_from_raw_config(config, "remove-key")

    assert "remove-key" not in updated
    assert "keep-key" in updated
    assert "also-keep-key" in updated
    assert service._remove_peer_from_raw_config(config, "missing-key") == config


def test_parse_wg_dump_maps_peer_fields_and_online_status(service):
    recent_ts = int((datetime.now() - timedelta(seconds=30)).timestamp())
    old_ts = int((datetime.now() - timedelta(seconds=300)).timestamp())
    dump_output = (
        "private\tpublic\tlisten-port\tfwmark\n"
        f"online-key\tpsk\t203.0.113.10:12345\t10.8.1.2/32\t{recent_ts}\t100\t200\t25\n"
        f"offline-key\tpsk\t(none)\t10.8.1.3/32,fd00::3/128\t{old_ts}\t300\t400\toff\n"
        "invalid\tline\n"
    )

    peers = service._parse_wg_dump(dump_output)

    assert peers["online-key"]["endpoint"] == "203.0.113.10:12345"
    assert peers["online-key"]["allowed_ips"] == ["10.8.1.2/32"]
    assert peers["online-key"]["rx_bytes"] == 100
    assert peers["online-key"]["tx_bytes"] == 200
    assert peers["online-key"]["persistent_keepalive"] == 25
    assert peers["online-key"]["online"] is True
    assert peers["offline-key"]["endpoint"] is None
    assert peers["offline-key"]["allowed_ips"] == ["10.8.1.3/32", "fd00::3/128"]
    assert peers["offline-key"]["persistent_keepalive"] == 0
    assert peers["offline-key"]["online"] is False


class FakePeersConnection:
    async def get_peers_dump(self) -> str:
        recent_ts = int((datetime.now() - timedelta(seconds=30)).timestamp())
        return (
            "private\tpublic\tlisten-port\tfwmark\n"
            f"named-key\tpsk\t203.0.113.10:12345\t10.8.1.2/32\t{recent_ts}\t100\t200\t25\n"
            f"unnamed-key\tpsk\t(none)\t10.8.1.3/32\t0\t0\t0\toff\n"
        )

    async def read_protocol_config(self) -> str:
        return """
[Peer]
# AppType = amnezia_vpn
PublicKey = named-key
AllowedIPs = 10.8.1.2/32
"""

    async def read_clients_table(self) -> str:
        return """
[
    {
        "clientId": "named-key",
        "userData": {
            "clientName": "dmitry-iphone"
        }
    }
]
"""


@pytest.mark.anyio
async def test_get_peers_includes_client_name_from_clients_table():
    instance = object.__new__(AmneziaWG2Service)
    instance.settings = SimpleNamespace(peer_online_threshold_seconds=180)
    instance._connection = FakePeersConnection()
    instance._protocol_name = "amneziawg2"
    instance._default_app_type = AmneziaWG2Service.AMNEZIA_WG_APP_TYPE

    peers = await instance.get_peers()

    assert peers[0]["public_key"] == "named-key"
    assert peers[0]["client_name"] == "dmitry-iphone"
    assert peers[0]["app_type"] == "amnezia_vpn"
    assert peers[1]["public_key"] == "unnamed-key"
    assert peers[1]["client_name"] is None
    assert peers[1]["app_type"] == "amnezia_wg"


class FakeConnection:
    async def read_server_public_key(self) -> str:
        return "server-public-key"

    async def read_preshared_key(self) -> str:
        return "preshared-key"

    async def read_protocol_config(self) -> str:
        return """
[Interface]
Address = 10.8.1.1/24
Jc = 7
Jmin = 11
Jmax = 51
"""


@pytest.mark.anyio
async def test_generate_text_config_matches_current_template():
    instance = object.__new__(AmneziaWG2Service)
    instance.settings = SimpleNamespace(
        server_public_host="vpn.example.test",
        persistent_keepalive_seconds=25,
    )
    instance._connection = FakeConnection()
    instance.protocol_config = {
        "primary_dns": "1.1.1.1",
        "secondary_dns": "1.0.0.1",
    }
    instance._awg_params_defaults = {
        "Jc": "5",
        "Jmin": "10",
        "Jmax": "50",
        "S1": "",
        "S2": "",
        "S3": "",
        "S4": "",
        "H1": "",
        "H2": "",
        "H3": "",
        "H4": "",
        "I1": "",
        "I2": "",
        "I3": "",
        "I4": "",
        "I5": "",
    }

    assert await instance._generate_text_config(
        private_key="client-private-key",
        allowed_ip="10.8.1.2/32",
        server_port=51820,
    ) == (
        "[Interface]\n"
        "Address = 10.8.1.2/32\n"
        "DNS = 1.1.1.1, 1.0.0.1\n"
        "PrivateKey = client-private-key\n"
        "Jc = 7\n"
        "Jmin = 11\n"
        "Jmax = 51\n"
        "S1 = \n"
        "S2 = \n"
        "S3 = \n"
        "S4 = \n"
        "H1 = \n"
        "H2 = \n"
        "H3 = \n"
        "H4 = \n"
        "I1 = \n"
        "I2 = \n"
        "I3 = \n"
        "I4 = \n"
        "I5 = \n"
        "\n"
        "[Peer]\n"
        "PublicKey = server-public-key\n"
        "PresharedKey = preshared-key\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        "Endpoint = vpn.example.test:51820\n"
        "PersistentKeepalive = 25\n"
    )
