import asyncio
import io
import posixpath
import re
import socket
import tarfile
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import cast

import docker
from docker.models.containers import Container
from docker.utils.socket import STDERR, STDOUT, frames_iter

from src.management.logger import configure_logger
from src.services.management.protocol_factory import get_protocol_config


logger = configure_logger("ContainerConnection", "blue")


class DockerError(Exception):
    """Raised when Docker command or client access fails."""


class ContainerConnection(ABC):
    _CONTAINER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    _INTERFACE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")

    def __init__(self, protocol_name: str):
        self.protocol_name = protocol_name
        self.protocol_config = get_protocol_config(protocol_name)
        container_name = self.protocol_config.get("container_name")
        interface = self.protocol_config.get("interface")
        config_path = self.protocol_config.get("config_path")

        if not container_name:
            raise ValueError(f"Protocol {protocol_name} does not define container_name")
        self.container_name = self._validate_container_name(str(container_name))
        self.interface = (
            self._validate_interface_name(str(interface)) if interface else None
        )
        self.config_path = (
            self._validate_container_path(str(config_path), field_name="config_path")
            if config_path
            else None
        )

        try:
            self.docker_client = docker.from_env()
        except Exception as exc:
            logger.error(f"Failed to initialize Docker client: {exc}")
            raise DockerError(f"Docker client initialization failed: {exc}")

    async def run_command(
        self,
        args: Sequence[str],
        check: bool = True,
        input_data: str | None = None,
    ) -> tuple[str, str]:
        argv = [str(arg) for arg in args]
        if not argv:
            raise ValueError("Command arguments must not be empty")

        logger.debug(f"Executing in {self.container_name}: {' '.join(argv)}")

        try:
            container = await self._get_container()
            if input_data is None:
                exit_code, stdout_decoded, stderr_decoded = await asyncio.to_thread(
                    self._exec_without_input,
                    container,
                    argv,
                )
            else:
                exit_code, stdout_decoded, stderr_decoded = await asyncio.to_thread(
                    self._exec_with_input,
                    container,
                    argv,
                    input_data,
                )

            if check and exit_code != 0:
                logger.error(f"Command failed with code {exit_code}: {stderr_decoded}")
                raise DockerError(f"Command failed: {stderr_decoded or 'Unknown error'}")

            return stdout_decoded, stderr_decoded
        except docker.errors.NotFound:
            logger.error(f"Container {self.container_name} not found")
            raise DockerError(f"Container {self.container_name} not found")
        except DockerError:
            raise
        except Exception as exc:
            logger.error(f"Docker API error: {exc}")
            raise DockerError(f"Docker API error: {exc}")

    async def read_file(self, path: str) -> str:
        safe_path = self._validate_container_path(path, field_name="path")
        try:
            container = await self._get_container()
            archive_bytes = await asyncio.to_thread(
                self._read_file_archive,
                container,
                safe_path,
            )
            return archive_bytes.decode("utf-8").strip()
        except docker.errors.NotFound:
            logger.error(f"Container {self.container_name} not found")
            raise DockerError(f"Container {self.container_name} not found")
        except DockerError:
            raise
        except Exception as exc:
            logger.error(f"Docker API error: {exc}")
            raise DockerError(f"Docker API error: {exc}")

    async def write_file(self, path: str, content: str) -> None:
        safe_path = self._validate_container_path(path, field_name="path")
        try:
            container = await self._get_container()
            await asyncio.to_thread(
                self._write_file_archive,
                container,
                safe_path,
                content.encode("utf-8"),
            )
            logger.debug(f"File written: {safe_path}")
        except docker.errors.NotFound:
            logger.error(f"Container {self.container_name} not found")
            raise DockerError(f"Container {self.container_name} not found")
        except DockerError:
            raise
        except Exception as exc:
            logger.error(f"Docker API error: {exc}")
            raise DockerError(f"Docker API error: {exc}")

    async def _get_container(self) -> Container:
        return await asyncio.to_thread(
            self.docker_client.containers.get,
            self.container_name,
        )

    @classmethod
    def _validate_container_name(cls, value: str) -> str:
        if not cls._CONTAINER_NAME_PATTERN.fullmatch(value):
            raise ValueError("Protocol container_name contains unsupported characters")
        return value

    @classmethod
    def _validate_interface_name(cls, value: str) -> str:
        if not cls._INTERFACE_NAME_PATTERN.fullmatch(value):
            raise ValueError("Protocol interface contains unsupported characters")
        return value

    @staticmethod
    def _validate_container_path(value: str, field_name: str) -> str:
        if not value or "\x00" in value:
            raise ValueError(f"Protocol {field_name} must be a non-empty path")

        path = PurePosixPath(value)
        if not path.is_absolute():
            raise ValueError(f"Protocol {field_name} must be an absolute path")
        if path == PurePosixPath("/"):
            raise ValueError(f"Protocol {field_name} must not point to container root")
        if any(part == ".." or "\n" in part or "\r" in part for part in path.parts):
            raise ValueError(f"Protocol {field_name} contains unsupported path segments")

        return posixpath.normpath(str(path))

    @classmethod
    def _join_container_path(cls, base_path: str, filename: str) -> str:
        if "/" in filename or filename in {"", ".", ".."}:
            raise ValueError("Container filename contains unsupported path segments")
        return cls._validate_container_path(
            posixpath.join(base_path, filename),
            field_name="path",
        )

    @staticmethod
    def _exec_without_input(
        container: Container,
        argv: Sequence[str],
    ) -> tuple[int, str, str]:
        exit_code, output = container.exec_run(
            cmd=list(argv),
            stdout=True,
            stderr=True,
            demux=True,
        )
        stdout, stderr = cast(tuple[bytes | None, bytes | None], output)
        return (
            int(exit_code if exit_code is not None else 0),
            stdout.decode().strip() if stdout else "",
            stderr.decode().strip() if stderr else "",
        )

    def _exec_with_input(
        self,
        container: Container,
        argv: Sequence[str],
        input_data: str,
    ) -> tuple[int, str, str]:
        exec_response = self.docker_client.api.exec_create(
            container.id,
            list(argv),
            stdout=True,
            stderr=True,
            stdin=True,
            tty=False,
        )
        exec_id = exec_response["Id"]
        exec_socket = self.docker_client.api.exec_start(
            exec_id,
            socket=True,
            tty=False,
        )
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []

        try:
            self._write_socket_input(exec_socket, input_data.encode("utf-8"))
            for stream, chunk in frames_iter(exec_socket, tty=False):
                if stream == STDOUT:
                    stdout_chunks.append(chunk)
                elif stream == STDERR:
                    stderr_chunks.append(chunk)
        finally:
            self._close_socket(exec_socket)

        inspect_result = self.docker_client.api.exec_inspect(exec_id)
        exit_code = int(inspect_result.get("ExitCode") or 0)
        return (
            exit_code,
            b"".join(stdout_chunks).decode().strip(),
            b"".join(stderr_chunks).decode().strip(),
        )

    @staticmethod
    def _write_socket_input(exec_socket: object, data: bytes) -> None:
        raw_socket = getattr(exec_socket, "_sock", exec_socket)
        if hasattr(raw_socket, "sendall"):
            raw_socket.sendall(data)
        elif hasattr(exec_socket, "write"):
            exec_socket.write(data)
            if hasattr(exec_socket, "flush"):
                exec_socket.flush()
        else:
            raise DockerError("Docker exec socket does not support stdin writes")

        if hasattr(raw_socket, "shutdown"):
            raw_socket.shutdown(socket.SHUT_WR)

    @staticmethod
    def _close_socket(exec_socket: object) -> None:
        if hasattr(exec_socket, "close"):
            exec_socket.close()

    @staticmethod
    def _read_file_archive(container: Container, path: str) -> bytes:
        archive_stream, _ = container.get_archive(path)
        archive_data = b"".join(archive_stream)
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r") as archive:
            for member in archive.getmembers():
                if member.isfile():
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        break
                    return extracted.read()

        raise DockerError(f"File not found in archive: {path}")

    @staticmethod
    def _write_file_archive(container: Container, path: str, content: bytes) -> None:
        parent_dir = posixpath.dirname(path)
        filename = posixpath.basename(path)
        tar_stream = io.BytesIO()

        with tarfile.open(fileobj=tar_stream, mode="w") as archive:
            tar_info = tarfile.TarInfo(name=filename)
            tar_info.size = len(content)
            tar_info.mode = 0o600
            archive.addfile(tar_info, io.BytesIO(content))

        tar_stream.seek(0)
        if not container.put_archive(parent_dir, tar_stream.getvalue()):
            raise DockerError(f"Failed to write file: {path}")

    @abstractmethod
    async def get_peers_dump(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def sync_config(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def read_protocol_config(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def write_protocol_config(self, content: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def generate_private_key(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def generate_public_key(self, private_key: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def read_server_public_key(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def read_preshared_key(self) -> str:
        raise NotImplementedError
