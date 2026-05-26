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
        interface = self._interface_name()
        stdout, _ = await self.run_command(["wg", "show", interface, "dump"])
        return stdout

    async def sync_config(self) -> None:
        interface = self._interface_name()
        config_file = self._protocol_config_file()
        stripped_config, _ = await self.run_command(["wg-quick", "strip", config_file])
        await self.run_command(
            ["wg", "syncconf", interface, "/dev/stdin"],
            input_data=f"{stripped_config}\n",
        )
        logger.info(f"WireGuard config synchronized for {interface}")

    async def read_protocol_config(self) -> str:
        return await self.read_file(self._protocol_config_file())

    async def write_protocol_config(self, content: str) -> None:
        config_file = self._protocol_config_file()
        await self.write_file(config_file, content)
        logger.info(f"WireGuard config written to {config_file}")

    async def generate_private_key(self) -> str:
        stdout, _ = await self.run_command(["wg", "genkey"])
        return stdout

    async def generate_public_key(self, private_key: str) -> str:
        stdout, _ = await self.run_command(
            ["wg", "pubkey"],
            input_data=f"{private_key.strip()}\n",
        )
        return stdout

    async def read_server_public_key(self) -> str:
        key_file = self._join_container_path(
            self._config_path(),
            "wireguard_server_public_key.key",
        )
        return await self.read_file(key_file)

    async def read_preshared_key(self) -> str:
        key_file = self._join_container_path(
            self._config_path(),
            "wireguard_psk.key",
        )
        return await self.read_file(key_file)

    def _interface_name(self) -> str:
        if self.interface is None:
            raise ValueError(f"Protocol {self.protocol_name} does not define interface")
        return self.interface

    def _config_path(self) -> str:
        if self.config_path is None:
            raise ValueError(f"Protocol {self.protocol_name} does not define config_path")
        return self.config_path

    def _protocol_config_file(self) -> str:
        return self._join_container_path(
            self._config_path(),
            f"{self._interface_name()}.conf",
        )
