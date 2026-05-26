import json

from src.services.protocols.amneziawg2.amneziawg2_config_generator import (
    AmneziaWG2ConfigGenerator,
)


def test_generate_and_decode_vpn_link_round_trip():
    generator = AmneziaWG2ConfigGenerator()

    link = generator.generate_amnezia_vpn_config(
        client_private_key="client-private-key",
        client_public_key="client-public-key",
        server_public_key="server-public-key",
        psk="preshared-key",
        client_ip="10.8.1.2/32",
        awg_params={"Jc": "5", "Jmin": "10", "Jmax": "50", "S1": "1"},
        server_endpoint="vpn.example.test",
        server_port=51820,
        primary_dns="1.1.1.1",
        secondary_dns="1.0.0.1",
        container_name="amnezia-awg2",
        description="Test server",
    )

    decoded = generator.decode_vpn_link(link)
    awg_config = decoded["containers"][0]["awg"]
    last_config = json.loads(awg_config["last_config"])

    assert link.startswith("vpn://")
    assert decoded["defaultContainer"] == "amnezia-awg2"
    assert decoded["dns1"] == "1.1.1.1"
    assert decoded["hostName"] == "vpn.example.test"
    assert awg_config["port"] == "51820"
    assert awg_config["protocol_version"] == "2"
    assert last_config["client_ip"] == "10.8.1.2"
    assert last_config["port"] == 51820
    assert last_config["client_pub_key"] == "client-public-key"
    assert "Address = 10.8.1.2/32" in last_config["config"]
    assert "Endpoint = vpn.example.test:51820" in last_config["config"]
