from types import SimpleNamespace

import pytest

from src.services.peers_service import PeersService


class FakeSyncResponse:
    def raise_for_status(self) -> None:
        return None


class RecordingAsyncClient:
    requests: list[dict] = []
    init_kwargs: dict = {}

    def __init__(self, **kwargs):
        self.__class__.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url: str, json: dict, headers: dict[str, str]):
        self.__class__.requests.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
            }
        )
        return FakeSyncResponse()


@pytest.fixture
def sync_service():
    service = object.__new__(PeersService)
    service.settings = SimpleNamespace(
        development=False,
        central_api_url="https://central.example.test/api/v1",
        central_api_key="central-sync-key",
        central_api_allowed_hosts="central.example.test",
    )

    async def get_status_snapshot(protocol: str) -> dict:
        return {"protocol": protocol}

    service.get_status_snapshot = get_status_snapshot
    return service


@pytest.mark.anyio
async def test_sync_uses_dedicated_central_api_key(monkeypatch, sync_service):
    RecordingAsyncClient.requests = []
    RecordingAsyncClient.init_kwargs = {}
    monkeypatch.setattr("src.services.peers_service.httpx.AsyncClient", RecordingAsyncClient)

    synced = await sync_service.sync_peers_status(protocols=["amnezia_wg"])

    assert synced == 1
    assert RecordingAsyncClient.init_kwargs["follow_redirects"] is False
    assert RecordingAsyncClient.requests[0]["url"] == (
        "https://central.example.test/api/v1/clusters/sync"
    )
    assert RecordingAsyncClient.requests[0]["headers"] == {
        "X-API-Key": "central-sync-key"
    }


@pytest.mark.anyio
async def test_sync_skips_without_central_api_key(sync_service):
    sync_service.settings.central_api_key = None

    synced = await sync_service.sync_peers_status(protocols=["amnezia_wg"])

    assert synced == 0


@pytest.mark.anyio
async def test_sync_rejects_http_url_outside_development(sync_service):
    sync_service.settings.central_api_url = "http://central.example.test/api/v1"

    with pytest.raises(ValueError, match="must use https outside development"):
        await sync_service.sync_peers_status(protocols=["amnezia_wg"])


@pytest.mark.anyio
async def test_sync_rejects_hosts_missing_from_allowlist(sync_service):
    sync_service.settings.central_api_url = "https://evil.example.test/api/v1"

    with pytest.raises(ValueError, match="host is not allowed"):
        await sync_service.sync_peers_status(protocols=["amnezia_wg"])


@pytest.mark.anyio
async def test_sync_rejects_enabled_sync_without_allowlist(sync_service):
    sync_service.settings.central_api_allowed_hosts = None

    with pytest.raises(ValueError, match="CENTRAL_API_ALLOWED_HOSTS"):
        await sync_service.sync_peers_status(protocols=["amnezia_wg"])

