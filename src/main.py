from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.management.logger import configure_logger
from src.management.settings import Settings, get_settings
from src.api.v1.peers.router import router as peers_router
from src.api.v1.server.router import router as server_router
from src.api.v1.management.middlewares.auth import get_current_api_key
from src.management.security import get_api_key_storage
from src.services.sync_scheduler import SyncScheduler
from src.services.management.protocol_factory import (
    get_available_protocols,
    load_protocol_config,
)

logger = configure_logger("MAIN", "cyan")
settings = get_settings()
sync_scheduler = SyncScheduler()


def _split_hosts(value: str | None) -> list[str]:
    if not value:
        return []
    return [host.strip() for host in value.split(",") if host.strip()]


def _production_allowed_hosts(settings: Settings) -> list[str]:
    return _split_hosts(settings.api_allowed_hosts) or [settings.server_public_host]


def configure_security_middleware(app: FastAPI, settings: Settings) -> None:
    if settings.development:
        return

    # Production baseline: reject arbitrary Host values before protected routes run.
    if settings.api_enforce_https:
        app.add_middleware(HTTPSRedirectMiddleware)

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_production_allowed_hosts(settings),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Amnezia API...")
    load_protocol_config()
    logger.info(f"Loaded protocols: {get_available_protocols()}")
    get_api_key_storage().get_api_key()
    logger.info("The API key was successfully installed")
    await sync_scheduler.start()
    yield
    await sync_scheduler.stop()
    logger.info("Shutting down Amnezia API...")


app = FastAPI(
    title="Amnezia Cluster API",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/api/v1",
    docs_url="/docs" if settings.development else None,
    redoc_url="/redoc" if settings.development else None,
    openapi_url="/openapi.json" if settings.development else None,
    swagger_ui_parameters={"persistAuthorization": False},
)

configure_security_middleware(app, settings)


app.include_router(
    peers_router,
    prefix="/peers",
    tags=["Peers"],
    dependencies=[Depends(get_current_api_key)]
)

app.include_router(
    server_router,
    prefix="/server",
    tags=["Server"],
    dependencies=[Depends(get_current_api_key)]
)

@app.get("/health")
async def health_check():
    return {
        "app": "Amnezia API",
        "status": "running"
    }
