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
