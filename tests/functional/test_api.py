import importlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient


API_KEY = "functional-test-api-key"
PROTOCOL = "amneziawg2"


class FakeDockerClient:
    class Containers:
        def list(self) -> list[Any]:
            return []

    containers = Containers()


@dataclass
class FakeHostService:
    running: bool = True
    restarted: list[tuple[str, int]] = field(default_factory=list)

    async def is_container_running(self, container_name: str) -> bool:
        return self.running

    async def get_container_port(self, container_name: str, protocol: str = "udp") -> int:
        return 51820

    async def restart_container(self, container_name: str, timeout: int = 10) -> None:
        self.restarted.append((container_name, timeout))


class FakeProtocolService:
    def __init__(self) -> None:
        self.peers: list[dict[str, Any]] = []
        self.next_peer_id = 1

    async def create_peer(
        self,
        app_type: str,
        allocated_ip: str | None = None,
    ) -> dict[str, str]:
        peer_id = self.next_peer_id
        self.next_peer_id += 1
        public_key = f"public-key-{peer_id}"
        peer_ip = allocated_ip or f"10.8.1.{peer_id + 1}/32"
        endpoint = "198.51.100.10:51820"
        peer = {
            "public_key": public_key,
            "allowed_ips": [peer_ip],
            "app_type": app_type,
            "endpoint": endpoint,
            "online": True,
            "last_handshake": datetime.now(timezone.utc),
            "rx_bytes": 100 * peer_id,
            "tx_bytes": 200 * peer_id,
        }
        self.peers.append(peer)
        return {
            "public_key": public_key,
            "private_key": f"private-key-{peer_id}",
            "allocated_ip": peer_ip,
            "endpoint": endpoint,
            "app_type": app_type,
            "protocol": PROTOCOL,
            "config": f"[Peer]\nPublicKey = {public_key}\n",
        }

    async def get_peers(self) -> list[dict[str, Any]]:
        return [peer.copy() for peer in self.peers]

    async def delete_peer(self, public_key: str) -> bool:
        for index, peer in enumerate(self.peers):
            if peer["public_key"] == public_key:
                del self.peers[index]
                return True
        return False


@pytest.fixture
def functional_client(monkeypatch):
    monkeypatch.setenv("API_KEY", API_KEY)
    monkeypatch.setenv("DEVELOPMENT", "true")
    monkeypatch.setenv("SERVER_PUBLIC_HOST", "vpn.example.test")

    from src.management.security import get_api_key_storage
    from src.management.settings import get_settings

    get_settings.cache_clear()
    get_api_key_storage.cache_clear()

    import docker

    monkeypatch.setattr(docker, "from_env", lambda: FakeDockerClient())

    for module_name in ("src.main", "src.api.v1.server.router"):
        sys.modules.pop(module_name, None)

    main_module = importlib.import_module("src.main")
    server_router = importlib.import_module("src.api.v1.server.router")
    peers_service_module = importlib.import_module("src.services.peers_service")
    fake_service = FakeProtocolService()
    fake_host_service = FakeHostService()

    def get_active_protocol_name() -> str:
        return PROTOCOL

    def get_protocol_config(protocol_name: str) -> dict[str, str]:
        return {
            "container_name": "amneziawg2-container",
            "interface": "awg0",
        }

    def create_protocol_service(protocol_name: str) -> FakeProtocolService:
        assert protocol_name == PROTOCOL
        return fake_service

    patch_modules = [
        "src.api.v1.peers.crud.create",
        "src.api.v1.peers.crud.read",
        "src.api.v1.peers.crud.update",
        "src.api.v1.peers.crud.delete",
        "src.api.v1.server.router",
        "src.services.peers_service",
        "src.services.server_service",
    ]
    for module_name in patch_modules:
        module = importlib.import_module(module_name)
        if hasattr(module, "get_active_protocol_name"):
            monkeypatch.setattr(module, "get_active_protocol_name", get_active_protocol_name)
        if hasattr(module, "create_protocol_service"):
            monkeypatch.setattr(module, "create_protocol_service", create_protocol_service)
        if hasattr(module, "get_protocol_config"):
            monkeypatch.setattr(module, "get_protocol_config", get_protocol_config)

    monkeypatch.setattr(server_router, "host_service", fake_host_service)
    monkeypatch.setattr(server_router.server_service, "host_service", fake_host_service)
    peers_service_module.get_peers_service.cache_clear()

    client = TestClient(main_module.app)
    yield client, fake_service, fake_host_service

    peers_service_module.get_peers_service.cache_clear()
    get_settings.cache_clear()
    get_api_key_storage.cache_clear()


def auth_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}


def test_health_check_does_not_require_api_key(functional_client):
    client, _, _ = functional_client

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"app": "Amnezia API", "status": "running"}


def test_openapi_contract_exposes_current_routes(functional_client):
    client, _, _ = functional_client

    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert set(paths) >= {
        "/peers/",
        "/server/status",
        "/server/traffic",
        "/server/restart",
        "/health",
    }
    assert set(paths["/peers/"]) == {"get", "post", "patch", "delete"}
    assert set(paths["/server/status"]) == {"get"}
    assert set(paths["/server/traffic"]) == {"get"}
    assert set(paths["/server/restart"]) == {"post"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-API-Key": "wrong-key"},
    ],
)
def test_protected_routes_reject_missing_or_invalid_api_key(functional_client, headers):
    client, _, _ = functional_client

    response = client.get("/peers/", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API key"}


def test_peer_lifecycle_and_traffic_endpoints(functional_client):
    client, _, _ = functional_client

    create_response = client.post(
        "/peers/",
        headers=auth_headers(),
        json={"app_type": "amnezia_vpn"},
    )
    assert create_response.status_code == 201
    created_peer = create_response.json()
    assert created_peer["public_key"] == "public-key-1"
    assert created_peer["allocated_ip"] == "10.8.1.2/32"
    assert created_peer["app_type"] == "amnezia_vpn"
    assert created_peer["protocol"] == PROTOCOL

    list_response = client.get("/peers/", headers=auth_headers())
    assert list_response.status_code == 200
    assert list_response.json() == [
        {
            "public_key": "public-key-1",
            "allocated_ip": "10.8.1.2/32",
            "app_type": "amnezia_vpn",
            "protocol": PROTOCOL,
            "endpoint": "198.51.100.10:51820",
            "online": True,
            "last_handshake": list_response.json()[0]["last_handshake"],
            "rx_bytes": 100,
            "tx_bytes": 200,
            "created_at": None,
        }
    ]

    traffic_response = client.get("/server/traffic", headers=auth_headers())
    assert traffic_response.status_code == 200
    assert traffic_response.json() == {
        "total_rx_bytes": 100,
        "total_tx_bytes": 200,
        "total_peers": 1,
        "online_peers": 1,
    }

    update_response = client.patch(
        "/peers/",
        headers=auth_headers(),
        json={
            "public_key": created_peer["public_key"],
            "app_type": "amnezia_wg",
        },
    )
    assert update_response.status_code == 200
    updated_peer = update_response.json()
    assert updated_peer["old_public_key"] == "public-key-1"
    assert updated_peer["new_public_key"] == "public-key-2"
    assert updated_peer["allocated_ip"] == "10.8.1.2/32"
    assert updated_peer["app_type"] == "amnezia_wg"

    delete_response = client.request(
        "DELETE",
        "/peers/",
        headers=auth_headers(),
        json={"public_key": updated_peer["new_public_key"]},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"
    assert delete_response.json()["public_key"] == "public-key-2"

    assert client.get("/peers/", headers=auth_headers()).json() == []


def test_peer_filters_and_validation(functional_client):
    client, fake_service, _ = functional_client

    client.post("/peers/", headers=auth_headers(), json={"app_type": "amnezia_vpn"})
    client.post("/peers/", headers=auth_headers(), json={"app_type": "amnezia_wg"})
    fake_service.peers[1]["online"] = False

    app_type_response = client.get(
        "/peers/",
        headers=auth_headers(),
        params={"app_type": "amnezia_vpn"},
    )
    assert app_type_response.status_code == 200
    assert [peer["public_key"] for peer in app_type_response.json()] == ["public-key-1"]

    online_response = client.get(
        "/peers/",
        headers=auth_headers(),
        params={"online_only": "true"},
    )
    assert online_response.status_code == 200
    assert [peer["public_key"] for peer in online_response.json()] == ["public-key-1"]

    invalid_filter_response = client.get(
        "/peers/",
        headers=auth_headers(),
        params={"app_type": "wireguard"},
    )
    assert invalid_filter_response.status_code == 400
    assert invalid_filter_response.json() == {"detail": "Invalid app_type: wireguard"}

    invalid_payload_response = client.post(
        "/peers/",
        headers=auth_headers(),
        json={"app_type": "wireguard"},
    )
    assert invalid_payload_response.status_code == 422


def test_server_status_and_restart(functional_client):
    client, _, fake_host_service = functional_client

    status_response = client.get("/server/status", headers=auth_headers())
    assert status_response.status_code == 200
    assert status_response.json() == {
        "status": "running",
        "container_name": "amneziawg2-container",
        "port": 51820,
        "interface": "awg0",
        "protocol": PROTOCOL,
    }

    restart_response = client.post("/server/restart", headers=auth_headers())
    assert restart_response.status_code == 200
    assert restart_response.json() == {
        "status": "restarted",
        "message": "Server amneziawg2-container has been restarted successfully",
    }
    assert fake_host_service.restarted == [("amneziawg2-container", 10)]

    fake_host_service.running = False
    stopped_response = client.get("/server/status", headers=auth_headers())
    assert stopped_response.status_code == 200
    assert stopped_response.json()["status"] == "stopped"

    restart_stopped_response = client.post("/server/restart", headers=auth_headers())
    assert restart_stopped_response.status_code == 400
    assert restart_stopped_response.json() == {
        "detail": "Container amneziawg2-container is not running"
    }
