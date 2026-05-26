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
    assert awg_config == {
        "H1": "",
        "H2": "",
        "H3": "",
        "H4": "",
        "I1": "",
        "I2": "",
        "I3": "",
        "I4": "",
        "I5": "",
        "Jc": "5",
        "Jmax": "50",
        "Jmin": "10",
        "S1": "1",
        "S2": "",
        "S3": "",
        "S4": "",
        "last_config": awg_config["last_config"],
        "port": "51820",
        "protocol_version": "2",
        "subnet_address": "10.8.1.0",
        "transport_proto": "udp",
    }
    assert last_config == {
        "H1": "",
        "H2": "",
        "H3": "",
        "H4": "",
        "I1": "",
        "I2": "",
        "I3": "",
        "I4": "",
        "I5": "",
        "Jc": "5",
        "Jmax": "50",
        "Jmin": "10",
        "S1": "1",
        "S2": "",
        "S3": "",
        "S4": "",
        "allowed_ips": ["0.0.0.0/0", "::/0"],
        "clientId": "client-public-key",
        "client_ip": "10.8.1.2",
        "client_priv_key": "client-private-key",
        "client_pub_key": "client-public-key",
        "config": last_config["config"],
        "hostName": "vpn.example.test",
        "mtu": "1376",
        "persistent_keep_alive": "25",
        "port": 51820,
        "psk_key": "preshared-key",
        "server_pub_key": "server-public-key",
    }
    assert last_config["config"] == (
        "[Interface]\n"
        "Address = 10.8.1.2/32\n"
        "DNS = $PRIMARY_DNS, $SECONDARY_DNS\n"
        "MTU = 1376\n"
        "PrivateKey = client-private-key\n"
        "Jc = 5\n"
        "Jmin = 10\n"
        "Jmax = 50\n"
        "S1 = 1\n"
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
