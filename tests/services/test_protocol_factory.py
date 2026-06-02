import pytest

from src.services.management import protocol_factory


@pytest.fixture(autouse=True)
def clear_protocol_config():
    protocol_factory.clear_protocol_config()
    yield
    protocol_factory.clear_protocol_config()


def test_load_protocol_config_normalizes_names_and_filters_disabled_protocols(tmp_path):
    config_path = tmp_path / "protocols.yaml"
    config_path.write_text(
        """
protocols:
  AmneziaWG2:
    service_class: "package.module.EnabledService"
    enabled: true
  DisabledProtocol:
    service_class: "package.module.DisabledService"
    enabled: false
""",
        encoding="utf-8",
    )

    protocol_factory.load_protocol_config(str(config_path))

    assert protocol_factory.get_available_protocols() == ["amneziawg2"]
    assert protocol_factory.get_active_protocol_name() == "amneziawg2"
    assert (
        protocol_factory.get_protocol_config("AMNEZIAWG2")["service_class"]
        == "package.module.EnabledService"
    )


def test_load_protocol_config_rejects_missing_service_class(tmp_path):
    config_path = tmp_path / "protocols.yaml"
    config_path.write_text(
        """
protocols:
  broken:
    enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required field: service_class"):
        protocol_factory.load_protocol_config(str(config_path))


def test_get_active_protocol_name_rejects_config_without_enabled_protocols(tmp_path):
    config_path = tmp_path / "protocols.yaml"
    config_path.write_text(
        """
protocols:
  disabled:
    service_class: "package.module.DisabledService"
    enabled: false
""",
        encoding="utf-8",
    )

    protocol_factory.load_protocol_config(str(config_path))

    with pytest.raises(ValueError, match="No enabled protocols configured"):
        protocol_factory.get_active_protocol_name()


def test_reload_protocol_config_replaces_cached_protocols(tmp_path):
    first_config = tmp_path / "first-protocols.yaml"
    first_config.write_text(
        """
protocols:
  first:
    service_class: "package.module.FirstService"
    enabled: true
""",
        encoding="utf-8",
    )
    second_config = tmp_path / "second-protocols.yaml"
    second_config.write_text(
        """
protocols:
  second:
    service_class: "package.module.SecondService"
    enabled: true
""",
        encoding="utf-8",
    )

    protocol_factory.load_protocol_config(str(first_config))
    protocol_factory.reload_protocol_config(str(second_config))

    assert protocol_factory.get_available_protocols() == ["second"]
    with pytest.raises(ValueError, match="Unsupported protocol: first"):
        protocol_factory.get_protocol_config("first")
