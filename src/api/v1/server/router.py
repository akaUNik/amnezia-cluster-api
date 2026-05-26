from fastapi import APIRouter, HTTPException, status

from src.api.v1.server.logger import logger
from src.api.v1.server.schemas import (
    ServerStatusResponse,
    ServerTrafficResponse,
    RestartServerResponse,
)
from src.services.host_service import HostService
from src.services.server_service import ServerNotRunningError, ServerService

router = APIRouter()

try:
    host_service = HostService()
    server_service = ServerService(host_service=host_service)
except Exception as exc:
    import sys
    from src.management.logger import configure_logger
    logger = configure_logger("ServerRouter", "red")
    logger.critical(f"Failed to initialize HostService: {exc}")
    sys.exit(1)


@router.get(
    "/status",
    response_model=ServerStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_server_status() -> ServerStatusResponse:
    """Retrieve the current status of the Amnezia server including container state, port, and interface."""
    try:
        result = await server_service.get_status()
        if result["status"] == "stopped":
            logger.warning(f"Container {result['container_name']} is not running")
        else:
            logger.info(
                f"Server status: {result['container_name']} running on port {result['port']}"
            )
        return ServerStatusResponse(**result)

    except Exception as exc:
        logger.error(f"Failed to get server status: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get(
    "/traffic",
    response_model=ServerTrafficResponse,
    status_code=status.HTTP_200_OK,
)
async def get_server_traffic() -> ServerTrafficResponse:
    """Retrieve aggregated traffic statistics for all peers including bytes and connection metrics."""
    try:
        result = await server_service.get_traffic()

        logger.info(
            f"Traffic retrieved: RX={result['total_rx_bytes']} TX={result['total_tx_bytes']} "
            f"Peers={result['total_peers']} Online={result['online_peers']}"
        )

        return ServerTrafficResponse(**result)

    except Exception as exc:
        logger.error(f"Failed to get server traffic: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.post(
    "/restart",
    response_model=RestartServerResponse,
    status_code=status.HTTP_200_OK,
)
async def restart_server() -> RestartServerResponse:
    """Restart the Amnezia server container to reload configuration and reset connections."""
    try:
        result = await server_service.restart()
        logger.info(result["message"])
        return RestartServerResponse(**result)

    except HTTPException:
        raise
    except ServerNotRunningError as exc:
        logger.warning(str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error(f"Failed to restart server: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
