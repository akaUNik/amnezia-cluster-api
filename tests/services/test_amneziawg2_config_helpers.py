from datetime import datetime, timedelta

import pytest

from src.services.protocols.amneziawg2.config_helpers import (
    allocate_ip_address,
    build_peer_section,
    default_subnet_address,
    extract_awg_params,
    extract_client_names,
    extract_listen_port,
    extract_peer_app_types,
    normalize_app_type,
    parse_wg_dump,
    remove_peer_from_raw_config,
)


def test_config_helper_parity_for_peer_sections_and_metadata():
    config = """
[Interface]
Address = 10.8.1.1/24
ListenPort = 51820

[Peer]
# AppType = amnezia_vpn
PublicKey = keep-key
AllowedIPs = 10.8.1.2/32

[Peer]
# AppType = invalid
PublicKey = remove-key
AllowedIPs = 10.8.1.3/32
"""

    assert extract_peer_app_types(config, "amnezia_wg") == {
        "keep-key": "amnezia_vpn",
        "remove-key": "amnezia_wg",
    }
    assert "remove-key" not in remove_peer_from_raw_config(config, "remove-key")
    assert remove_peer_from_raw_config(config, "missing-key") == config
    assert extract_listen_port(config) == 51820
    assert default_subnet_address(config, "10.8.1.0") == "10.8.1.0"


def test_config_helper_parity_for_awg_params_and_peer_section_rendering():
    config = """
[Interface]
# Jc = 7
Jmin = 11
S1 = 99 # inline comment is excluded
"""

    assert extract_awg_params(config, {"Jc": "5", "Jmin": "10", "Jmax": "50"}) == {
        "Jc": "7",
        "Jmin": "11",
        "Jmax": "50",
        "S1": "99",
    }
    assert build_peer_section(
        public_key="peer-public-key",
        allowed_ip="10.8.1.2/32",
        preshared_key="psk",
        app_type="amnezia_wg",
    ) == (
        "\n[Peer]\n"
        "# AppType = amnezia_wg\n"
        "PublicKey = peer-public-key\n"
        "PresharedKey = psk\n"
        "AllowedIPs = 10.8.1.2/32\n"
    )


def test_extract_client_names_reads_clients_table_metadata():
    clients_table = """
[
    {
        "clientId": "first-public-key",
        "userData": {
            "clientName": "dmitry-iphone"
        }
    },
    {
        "clientId": "second-public-key",
        "userData": {
            "allowedIps": "10.8.1.3/32",
            "clientName": "Admin [macOS Tahoe (26.4.1)]"
        }
    },
    {
        "clientId": "missing-name",
        "userData": {}
    }
]
"""

    assert extract_client_names(clients_table) == {
        "first-public-key": "dmitry-iphone",
        "second-public-key": "Admin [macOS Tahoe (26.4.1)]",
    }


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
def test_config_helper_normalizes_app_type_aliases(raw_app_type, expected):
    assert normalize_app_type(raw_app_type) == expected


def test_config_helper_rejects_unknown_app_type():
    with pytest.raises(ValueError, match="Unsupported app_type"):
        normalize_app_type("wireguard")


def test_config_helper_parity_for_wg_dump_and_ip_allocation():
    now = datetime.now()
    recent_ts = int((now - timedelta(seconds=30)).timestamp())
    old_ts = int((now - timedelta(seconds=300)).timestamp())
    dump_output = (
        "private\tpublic\tlisten-port\tfwmark\n"
        f"online-key\tpsk\t203.0.113.10:12345\t10.8.1.2/32\t{recent_ts}\t100\t200\t25\n"
        f"offline-key\tpsk\t(none)\t10.8.1.3/32,fd00::3/128\t{old_ts}\t300\t400\toff\n"
        "invalid\tline\n"
    )

    peers = parse_wg_dump(
        dump_output,
        peer_online_threshold_seconds=180,
        now=now,
    )

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

    allocation_dump = (
        "private\tpublic\tlisten-port\tfwmark\n"
        f"first-key\tpsk\t203.0.113.10:12345\t10.8.1.2/32\t{recent_ts}\t100\t200\t25\n"
        f"second-key\tpsk\t203.0.113.11:12345\t10.8.1.3/32\t{recent_ts}\t100\t200\t25\n"
    )
    wg_config = "[Interface]\nAddress = 10.8.1.1/24\n"
    assert allocate_ip_address(wg_config, allocation_dump) == "10.8.1.4/32"
