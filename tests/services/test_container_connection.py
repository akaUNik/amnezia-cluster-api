import pytest

from src.services.management.container_connection import ContainerConnection
from src.services.protocols.amneziawg2.amneziawg2_connection import AmneziaWG2Connection


def test_container_config_validators_accept_expected_values():
    assert ContainerConnection._validate_container_name("amnezia-awg2") == "amnezia-awg2"
    assert ContainerConnection._validate_interface_name("awg0") == "awg0"
    assert (
        ContainerConnection._validate_container_path(
            "/opt/amnezia/awg",
            field_name="config_path",
        )
        == "/opt/amnezia/awg"
    )


@pytest.mark.parametrize(
    "container_name",
    ["", "bad name", ";reboot", "../container"],
)
def test_container_name_validator_rejects_shell_sensitive_values(container_name):
    with pytest.raises(ValueError, match="container_name"):
        ContainerConnection._validate_container_name(container_name)


@pytest.mark.parametrize(
    "interface_name",
    ["", "awg0;reboot", "awg0 name", "a" * 16],
)
def test_interface_validator_rejects_shell_sensitive_values(interface_name):
    with pytest.raises(ValueError, match="interface"):
        ContainerConnection._validate_interface_name(interface_name)


@pytest.mark.parametrize(
    "path",
    ["relative/path", "/", "/opt/amnezia/../secret", "/opt/amnezia/bad\npath"],
)
def test_container_path_validator_rejects_unsafe_paths(path):
    with pytest.raises(ValueError, match="path"):
        ContainerConnection._validate_container_path(path, field_name="path")


@pytest.mark.anyio
async def test_generate_public_key_uses_argv_and_stdin():
    instance = object.__new__(AmneziaWG2Connection)
    calls = []

    async def fake_run_command(args, check=True, input_data=None):
        calls.append((args, check, input_data))
        return "public-key", ""

    instance.run_command = fake_run_command

    assert await instance.generate_public_key("private-key") == "public-key"
    assert calls == [(["wg", "pubkey"], True, "private-key\n")]


@pytest.mark.anyio
async def test_sync_config_uses_argv_and_stdin():
    instance = object.__new__(AmneziaWG2Connection)
    instance.protocol_name = "amneziawg2"
    instance.interface = "awg0"
    instance.config_path = "/opt/amnezia/awg"
    calls = []

    async def fake_run_command(args, check=True, input_data=None):
        calls.append((args, check, input_data))
        return "stripped-config", ""

    instance.run_command = fake_run_command

    await instance.sync_config()

    assert calls == [
        (["wg-quick", "strip", "/opt/amnezia/awg/awg0.conf"], True, None),
        (["wg", "syncconf", "awg0", "/dev/stdin"], True, "stripped-config\n"),
    ]
