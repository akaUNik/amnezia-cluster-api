from fastapi import APIRouter, HTTPException, status

from src.api.v1.peers.logger import logger
from src.api.v1.peers.schemas import CreatePeerRequest, CreatePeerResponse
from src.services.peers_service import get_peers_service


router = APIRouter()


@router.post(
    "/",
    response_model=CreatePeerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_peer(payload: CreatePeerRequest) -> CreatePeerResponse:
    """Create a new peer with automatic IP allocation."""
    try:
        result = await get_peers_service().create_active_peer(
            app_type=payload.app_type.value,
        )

        logger.info(
            f"Peer created: {result['public_key'][:16]}... "
            f"app_type={result['app_type']} ip={result['allocated_ip']}"
        )

        return CreatePeerResponse(
            public_key=result["public_key"],
            private_key=result["private_key"],
            allocated_ip=result["allocated_ip"],
            endpoint=result["endpoint"],
            app_type=result["app_type"],
            protocol=result["protocol"],
            config=result["config"],
        )

    except ValueError as exc:
        logger.error(f"Validation error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Failed to create peer: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
