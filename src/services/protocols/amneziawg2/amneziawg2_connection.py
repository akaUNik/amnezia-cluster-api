from src.management.logger import configure_logger
from src.services.management.container_connection import ContainerConnection


logger = configure_logger("AmneziaWG2Connection", "blue")


class AmneziaWG2Connection(ContainerConnection):
    def __init__(self, protocol_name: str = "amneziawg2"):
        super().__init__(protocol_name=protocol_name)
        if not self.interface:
            raise ValueError(f"Protocol {protocol_name} does not define interface")
        if not self.config_path:
            raise ValueError(f"Protocol {protocol_name} does not define config_path")

    async def get_peers_dump(self) -> str:
        stdout, _ = await self.run_command(f"wg show {self.interface} dump")
        return stdout

    async def sync_config(self) -> None:
        config_file = f"{self.config_path}/{self.interface}.conf"
        cmd = f"wg-quick strip {config_file} | wg syncconf {self.interface} /dev/stdin"
        await self.run_command(cmd)
        logger.info(f"WireGuard config synchronized for {self.interface}")

    async def read_protocol_config(self) -> str:
        config_file = f"{self.config_path}/{self.interface}.conf"
        return await self.read_file(config_file)

    async def write_protocol_config(self, content: str) -> None:
        config_file = f"{self.config_path}/{self.interface}.conf"
        await self.write_file(config_file, content)
        logger.info(f"WireGuard config written to {config_file}")

    async def generate_private_key(self) -> str:
        stdout, _ = await self.run_command("wg genkey")
        return stdout

    async def generate_public_key(self, private_key: str) -> str:
        stdout, _ = await self.run_command(f"echo '{private_key}' | wg pubkey")
        return stdout

    async def read_server_public_key(self) -> str:
        key_file = f"{self.config_path}/wireguard_server_public_key.key"
        return await self.read_file(key_file)

    async def read_preshared_key(self) -> str:
        key_file = f"{self.config_path}/wireguard_psk.key"
        return await self.read_file(key_file)
