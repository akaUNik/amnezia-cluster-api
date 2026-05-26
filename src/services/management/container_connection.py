import asyncio
from abc import ABC, abstractmethod
from typing import cast

import docker

from src.management.logger import configure_logger
from src.services.management.protocol_factory import get_protocol_config


logger = configure_logger("ContainerConnection", "blue")


class DockerError(Exception):
    pass


class ContainerConnection(ABC):
    def __init__(self, protocol_name: str):
        self.protocol_name = protocol_name
        self.protocol_config = get_protocol_config(protocol_name)
        container_name = self.protocol_config.get("container_name")
        self.interface = self.protocol_config.get("interface")
        self.config_path = self.protocol_config.get("config_path")

        if not container_name:
            raise ValueError(f"Protocol {protocol_name} does not define container_name")
        self.container_name = str(container_name)

        try:
            self.docker_client = docker.from_env()
        except Exception as exc:
            logger.error(f"Failed to initialize Docker client: {exc}")
            raise DockerError(f"Docker client initialization failed: {exc}")

    async def run_command(self, cmd: str, check: bool = True) -> tuple[str, str]:
        logger.debug(f"Executing in {self.container_name}: {cmd}")

        try:
            container = await asyncio.to_thread(
                self.docker_client.containers.get,
                self.container_name,
            )

            exec_result = await asyncio.to_thread(
                container.exec_run,
                cmd=["sh", "-c", cmd],
                stdout=True,
                stderr=True,
                demux=True,
            )

            exit_code, output = exec_result
            stdout, stderr = cast(tuple[bytes | None, bytes | None], output)
            stdout_decoded = stdout.decode().strip() if stdout else ""
            stderr_decoded = stderr.decode().strip() if stderr else ""

            if check and exit_code != 0:
                logger.error(f"Command failed with code {exit_code}: {stderr_decoded}")
                raise DockerError(f"Command failed: {stderr_decoded or 'Unknown error'}")

            return stdout_decoded, stderr_decoded
        except docker.errors.NotFound:
            logger.error(f"Container {self.container_name} not found")
            raise DockerError(f"Container {self.container_name} not found")
        except Exception as exc:
            logger.error(f"Docker API error: {exc}")
            raise DockerError(f"Docker API error: {exc}")

    async def read_file(self, path: str) -> str:
        stdout, _ = await self.run_command(f"cat {path}")
        return stdout

    async def write_file(self, path: str, content: str) -> None:
        escaped_content = content.replace("'", "'\\''")
        cmd = f"cat > {path} <<'EOF'\n{escaped_content}\nEOF"
        await self.run_command(cmd)
        logger.debug(f"File written: {path}")

    @abstractmethod
    async def get_peers_dump(self) -> str:
        pass

    @abstractmethod
    async def sync_config(self) -> None:
        pass

    @abstractmethod
    async def read_protocol_config(self) -> str:
        pass

    @abstractmethod
    async def write_protocol_config(self, content: str) -> None:
        pass

    @abstractmethod
    async def generate_private_key(self) -> str:
        pass

    @abstractmethod
    async def generate_public_key(self, private_key: str) -> str:
        pass

    @abstractmethod
    async def read_server_public_key(self) -> str:
        pass

    @abstractmethod
    async def read_preshared_key(self) -> str:
        pass
