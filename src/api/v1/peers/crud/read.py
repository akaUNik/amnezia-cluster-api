from fastapi import APIRouter, HTTPException, status

from src.api.v1.errors import internal_server_error
from src.api.v1.peers.logger import logger
from src.api.v1.peers.schemas import ListPeerResponse
from src.services.peers_service import get_peers_service

router = APIRouter()


@router.get(
    "/",
    response_model=list[ListPeerResponse],
    status_code=status.HTTP_200_OK,
)
async def list_peers(
    app_type: str | None = None,
    online_only: bool = False,
) -> list[ListPeerResponse]:
    """List all peers with their status and traffic statistics. Optional filters by app_type and online status."""
    try:
        protocol_name, peers_data = await get_peers_service().list_active_peers(
            app_type=app_type,
            online_only=online_only,
        )

        peers = []
        for peer in peers_data:
            peers.append(
                ListPeerResponse(
                    public_key=peer["public_key"],
                    allocated_ip=peer["allowed_ips"][0] if peer.get("allowed_ips") else "N/A",
                    clientName=peer.get("client_name"),
                    app_type=peer.get("app_type"),
                    protocol=protocol_name,
                    endpoint=peer.get("endpoint") or "N/A",
                    online=peer.get("online", False),
                    last_handshake=peer.get("last_handshake"),
                    rx_bytes=peer.get("rx_bytes", 0),
                    tx_bytes=peer.get("tx_bytes", 0),
                )
            )

        logger.info(f"Listed {len(peers)} peers")
        return peers

    except ValueError as exc:
        logger.error(f"Validation error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception:
        logger.exception("Failed to list peers")
        raise internal_server_error()
