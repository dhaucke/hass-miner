"""Pure config-flow helper regression tests."""

from types import SimpleNamespace

from custom_components.miner.config_flow import MinerConfigFlow
from custom_components.miner.config_flow import _looks_like_auth_error
from custom_components.miner.const import CONF_IP


def test_auth_error_classification() -> None:
    """Common authentication failures should map to invalid_auth."""
    assert _looks_like_auth_error(RuntimeError("Permission denied"))
    assert _looks_like_auth_error(RuntimeError("HTTP 401 Unauthorized"))
    assert not _looks_like_auth_error(RuntimeError("connection timed out"))


def test_duplicate_host_matching_is_case_and_space_insensitive() -> None:
    """Configured hosts must not be added twice due to cosmetic differences."""
    flow = SimpleNamespace(
        _async_current_entries=lambda: [
            SimpleNamespace(data={CONF_IP: " Miner-One.Local "}),
            SimpleNamespace(data={CONF_IP: "192.168.1.20"}),
        ]
    )

    assert MinerConfigFlow._host_is_configured(flow, "miner-one.local")
    assert MinerConfigFlow._host_is_configured(flow, " 192.168.1.20 ")
    assert not MinerConfigFlow._host_is_configured(flow, "192.168.1.21")


def test_device_placeholders_do_not_expose_credentials() -> None:
    """Setup descriptions should contain only safe identification data."""
    flow = SimpleNamespace(
        _data={CONF_IP: "192.168.1.30", "ssh_password": "secret"},
        _miner=SimpleNamespace(
            make=SimpleNamespace(value="Bitmain"),
            raw_model="Antminer S9",
            model=None,
        ),
    )

    placeholders = MinerConfigFlow._device_placeholders(flow)

    assert placeholders == {
        "host": "192.168.1.30",
        "make": "Bitmain",
        "model": "Antminer S9",
    }
    assert "secret" not in repr(placeholders)
