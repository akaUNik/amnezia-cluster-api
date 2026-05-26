from fastapi import APIRouter, HTTPException, status

from src.api.v1.errors import internal_server_error
from src.api.v1.peers.logger import logger
from src.api.v1.peers.schemas import DeletePeerRequest, DeletePeerResponse
from src.services.peers_service import get_peers_service


router = APIRouter()


@router.delete(
    "/",
    response_model=DeletePeerResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_peer(payload: DeletePeerRequest) -> DeletePeerResponse:
    """Delete a peer and remove it from the protocol configuration."""
    try:
        public_key = payload.public_key.strip()
        deleted = await get_peers_service().delete_active_peer(public_key)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Peer {public_key[:16]}... not found",
            )

        logger.info(f"Peer {public_key[:16]}... deleted")

        return DeletePeerResponse(
            status="deleted",
            public_key=public_key,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to delete peer")
        raise internal_server_error()
