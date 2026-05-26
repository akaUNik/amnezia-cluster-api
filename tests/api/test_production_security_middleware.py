import importlib
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


class FakeDockerClient:
    class Containers:
        def list(self) -> list[object]:
            return []

    containers = Containers()


@pytest.fixture
def production_main(monkeypatch) -> Iterator[object]:
    monkeypatch.setenv("DEVELOPMENT", "false")
    monkeypatch.setenv("SERVER_PUBLIC_HOST", "api.example.test")
    monkeypatch.setenv("API_ALLOWED_HOSTS", "api.example.test")

    import docker

    monkeypatch.setattr(docker, "from_env", lambda: FakeDockerClient())

    from src.management.settings import get_settings

    get_settings.cache_clear()
    for module_name in ("src.main", "src.api.v1.server.router"):
        sys.modules.pop(module_name, None)

    module = importlib.import_module("src.main")
    yield module

    get_settings.cache_clear()
    for module_name in ("src.main", "src.api.v1.server.router"):
        sys.modules.pop(module_name, None)


def test_production_rejects_untrusted_host(production_main):
    client = TestClient(production_main.app, base_url="https://evil.example.test")

    response = client.get("/health")

    assert response.status_code == 400


def test_production_accepts_configured_host(production_main):
    client = TestClient(production_main.app, base_url="https://api.example.test")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"app": "Amnezia API", "status": "running"}


def test_production_https_redirect_can_be_enabled(monkeypatch, production_main):
    monkeypatch.setenv("API_ENFORCE_HTTPS", "true")

    from src.management.settings import get_settings

    get_settings.cache_clear()
    for module_name in ("src.main", "src.api.v1.server.router"):
        sys.modules.pop(module_name, None)

    main_module = importlib.import_module("src.main")
    client = TestClient(main_module.app, base_url="http://api.example.test")

    response = client.get("/health", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://api.example.test/health"
