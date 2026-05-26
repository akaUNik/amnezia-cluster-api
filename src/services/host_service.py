import asyncio
import docker
from src.management.logger import configure_logger

logger = configure_logger("HostService", "cyan")


class HostService:
    def __init__(self):
        try:
            self.docker_client = docker.from_env()
            logger.debug("Docker client initialized successfully")
        except Exception as exc:
            logger.error(f"Failed to initialize Docker client: {exc}")
            raise RuntimeError(f"Docker client initialization failed: {exc}")

    async def run_command(self, cmd: str, timeout: int = 2000, check: bool = True) -> tuple[str, str]:
        logger.debug(f"Executing host command: {cmd}")

        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout / 1000
            )
        except asyncio.TimeoutError:
            process.kill()
            raise TimeoutError(f"Command timed out after {timeout}ms: {cmd}")

        stdout_decoded = stdout.decode().strip()
        stderr_decoded = stderr.decode().strip()

        if check and process.returncode != 0:
            logger.error(
                f"Host command failed with code {process.returncode}: {stderr_decoded}"
            )
            raise RuntimeError(
                f"Command failed: {stderr_decoded or 'Unknown error'}"
            )

        return stdout_decoded, stderr_decoded

    async def list_running_containers(self) -> set[str]:
        try:
            containers = await asyncio.to_thread(self.docker_client.containers.list)
            container_names = {container.name for container in containers}
            logger.debug(f"Found {len(container_names)} running containers: {container_names}")
            return container_names
        except Exception as e:
            logger.warning(f"Failed to list Docker containers: {e}")
            return set()

    async def is_container_running(self, container_name: str) -> bool:
        if not container_name:
            logger.warning("Empty container name provided")
            return False

        containers = await self.list_running_containers()
        is_running = container_name in containers
        logger.debug(f"Container {container_name} running: {is_running}")
        return is_running

    async def get_container_port(self, container_name: str, protocol: str = "udp") -> int | None:
        try:
            container = await asyncio.to_thread(self.docker_client.containers.get, container_name)
            ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})

            logger.debug(f"Container {container_name} ports: {ports}")

            for port_spec, bindings in ports.items():
                if protocol in port_spec.lower() and bindings:
                    host_port = bindings[0].get("HostPort")
                    if host_port:
                        logger.debug(f"Found {protocol} port {host_port} for {container_name}")
                        return int(host_port)

            logger.warning(f"No {protocol} port found for container {container_name}")
            return None

        except docker.errors.NotFound:
            logger.warning(f"Container {container_name} not found")
            return None
        except Exception as e:
            logger.warning(f"Failed to get port for container {container_name}: {e}")
            return None

    async def restart_container(self, container_name: str, timeout: int = 10) -> None:
        try:
            container = await asyncio.to_thread(self.docker_client.containers.get, container_name)
            await asyncio.to_thread(container.restart, timeout=timeout)
            logger.info(f"Container {container_name} restarted successfully")
        except docker.errors.NotFound:
            raise RuntimeError(f"Container {container_name} not found")
        except Exception as exc:
            raise RuntimeError(f"Failed to restart container {container_name}: {exc}")

    async def read_file(self, path: str) -> str:
        stdout, _ = await self.run_command(f"cat {path}")
        return stdout

    @staticmethod
    async def get_system_info() -> dict:
        import os

        try:
            cpu_count = os.cpu_count() or 1

            loadavg = os.getloadavg()

            import psutil
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return {
                "cpu": {
                    "cores": cpu_count,
                },
                "loadavg": list(loadavg),
                "memory": {
                    "total_bytes": mem.total,
                    "free_bytes": mem.available,
                    "used_bytes": mem.used,
                },
                "disk": {
                    "total_bytes": disk.total,
                    "used_bytes": disk.used,
                    "available_bytes": disk.free,
                    "used_percent": disk.percent,
                }
            }
        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return {}
