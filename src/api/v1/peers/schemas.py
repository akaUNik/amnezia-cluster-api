from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AppType(str, Enum):
    """Types of applications for creating new peers"""
    AMNEZIA_VPN = "amnezia_vpn"
    AMNEZIA_WG = "amnezia_wg"

class CreatePeerRequest(BaseModel):
    app_type: AppType = Field(..., description="Application type for peer configuration")


class CreatePeerResponse(BaseModel):
    public_key: str
    private_key: str
    allocated_ip: str
    endpoint: str
    app_type: str
    protocol: str
    config: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ListPeerResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    public_key: str
    allocated_ip: str
    client_name: str | None = Field(default=None, alias="clientName")
    app_type: str | None = None
    protocol: str
    endpoint: str
    is_online: bool = Field(alias="online")
    last_handshake: datetime | None = None
    rx_bytes: int = 0
    tx_bytes: int = 0
    created_at: datetime | None = None


class UpdatePeerRequest(BaseModel):
    public_key: str = Field(..., description="Public key of peer to update")
    app_type: AppType = Field(..., description="New application type for peer configuration")


class UpdatePeerResponse(BaseModel):
    old_public_key: str
    new_public_key: str
    allocated_ip: str
    app_type: str
    protocol: str
    config: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeletePeerResponse(BaseModel):
    status: str = "deleted"
    public_key: str
    message: str = "Peer successfully removed from configuration"


class DeletePeerRequest(BaseModel):
    public_key: str = Field(..., description="Public key of peer to delete")
