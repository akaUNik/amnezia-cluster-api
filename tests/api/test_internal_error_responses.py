import pytest
from fastapi import HTTPException, status

from src.api.v1.errors import INTERNAL_SERVER_ERROR_DETAIL
from src.api.v1.peers.crud import create as create_module
from src.api.v1.peers.crud import delete as delete_module
from src.api.v1.peers.crud import read as read_module
from src.api.v1.peers.crud import update as update_module
from src.api.v1.peers.schemas import (
    AppType,
    CreatePeerRequest,
    DeletePeerRequest,
    UpdatePeerRequest,
)
from src.api.v1.server import router as server_router


SENSITIVE_ERROR = "docker exec /opt/amnezia/private.conf failed with secret-key"


def assert_internal_error_is_sanitized(exc_info: pytest.ExceptionInfo[HTTPException]):
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert exc_info.value.detail == INTERNAL_SERVER_ERROR_DETAIL
    assert SENSITIVE_ERROR not in str(exc_info.value.detail)


class FailingServerService:
    async def get_status(self):
        raise RuntimeError(SENSITIVE_ERROR)

    async def get_traffic(self):
        raise RuntimeError(SENSITIVE_ERROR)

    async def restart(self):
        raise RuntimeError(SENSITIVE_ERROR)


class FailingPeersService:
    async def create_active_peer(self, app_type: str):
        raise RuntimeError(SENSITIVE_ERROR)

    async def list_active_peers(
        self,
        app_type: str | None = None,
        online_only: bool = False,
    ):
        raise RuntimeError(SENSITIVE_ERROR)

    async def update_active_peer(self, public_key: str, app_type: str):
        raise RuntimeError(SENSITIVE_ERROR)

    async def delete_active_peer(self, public_key: str):
        raise RuntimeError(SENSITIVE_ERROR)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "handler_name",
    [
        "get_server_status",
        "get_server_traffic",
        "restart_server",
    ],
)
async def test_server_routes_sanitize_unexpected_errors(monkeypatch, handler_name):
    monkeypatch.setattr(server_router, "server_service", FailingServerService())
    handler = getattr(server_router, handler_name)

    with pytest.raises(HTTPException) as exc_info:
        await handler()

    assert_internal_error_is_sanitized(exc_info)


@pytest.mark.anyio
async def test_create_peer_sanitizes_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        create_module,
        "get_peers_service",
        lambda: FailingPeersService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_module.create_peer(
            CreatePeerRequest(app_type=AppType.AMNEZIA_VPN),
        )

    assert_internal_error_is_sanitized(exc_info)


@pytest.mark.anyio
async def test_list_peers_sanitizes_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        read_module,
        "get_peers_service",
        lambda: FailingPeersService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await read_module.list_peers()

    assert_internal_error_is_sanitized(exc_info)


@pytest.mark.anyio
async def test_update_peer_sanitizes_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        update_module,
        "get_peers_service",
        lambda: FailingPeersService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await update_module.update_peer(
            UpdatePeerRequest(
                public_key="public-key",
                app_type=AppType.AMNEZIA_VPN,
            ),
        )

    assert_internal_error_is_sanitized(exc_info)


@pytest.mark.anyio
async def test_delete_peer_sanitizes_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        delete_module,
        "get_peers_service",
        lambda: FailingPeersService(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_module.delete_peer(DeletePeerRequest(public_key="public-key"))

    assert_internal_error_is_sanitized(exc_info)
