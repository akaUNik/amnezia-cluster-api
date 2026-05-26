from pydantic import BaseModel


class ServerStatusResponse(BaseModel):
    status: str
    container_name: str
    port: int | None
    interface: str
    protocol: str


class ServerTrafficResponse(BaseModel):
    total_rx_bytes: int
    total_tx_bytes: int
    total_peers: int
    online_peers: int


class RestartServerResponse(BaseModel):
    status: str
    message: str
