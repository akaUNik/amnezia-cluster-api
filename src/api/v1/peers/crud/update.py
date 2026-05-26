from fastapi import APIRouter, HTTPException, status

from src.api.v1.peers.logger import logger
from src.api.v1.peers.schemas import UpdatePeerRequest, UpdatePeerResponse
from src.services.peers_service import get_peers_service


router = APIRouter()


@router.patch(
    "/",
    response_model=UpdatePeerResponse,
    status_code=status.HTTP_200_OK,
)
async def update_peer(payload: UpdatePeerRequest) -> UpdatePeerResponse:
    """Recreate a peer with a new application type while preserving its allocated IP address."""
    try:
        public_key = payload.public_key.strip()
        result = await get_peers_service().update_active_peer(
            public_key=public_key,
            app_type=payload.app_type.value,
        )

        logger.info(
            f"Peer {public_key[:16]}... updated: "
            f"{result['app_type']} ip={result['allocated_ip']}"
        )

        return UpdatePeerResponse(
            old_public_key=result["old_public_key"],
            new_public_key=result["new_public_key"],
            allocated_ip=result["allocated_ip"],
            app_type=result["app_type"],
            protocol=result["protocol"],
            config=result["config"],
        )

    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ValueError as exc:
        logger.error(f"Validation error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Failed to update peer: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
