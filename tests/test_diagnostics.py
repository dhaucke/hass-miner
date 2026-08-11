"""Diagnostics redaction regression tests."""

from types import SimpleNamespace

import pytest

from custom_components.miner.const import DOMAIN
from custom_components.miner.diagnostics import async_get_config_entry_diagnostics


class FakeBackend:
    """Return diagnostics containing data that must be redacted or preserved."""

    async def async_diagnostics(self) -> dict[str, object]:
        """Return representative backend diagnostics."""
        return {
            "backend": "braiins_legacy",
            "host": "192.168.1.60",
            "hostname": "s9miner1",
            "ip": "192.168.1.60",
            "mac": "00:11:22:33:44:55",
            "model": "Antminer S9",
            "firmware": "Braiins OS+",
            "capabilities": {"power_limit": True},
        }


@pytest.mark.asyncio
async def test_diagnostics_redact_network_identity() -> None:
    """Public diagnostics must hide local network identifiers."""
    coordinator = SimpleNamespace(
        backend=FakeBackend(),
        last_update_success=True,
        _failure_count=0,
    )
    entry = SimpleNamespace(
        entry_id="entry-1",
        title="S9 Miner",
        domain=DOMAIN,
        version=2,
        minor_version=0,
    )
    hass = SimpleNamespace(data={DOMAIN: {entry.entry_id: coordinator}})

    result = await async_get_config_entry_diagnostics(hass, entry)

    backend = result["backend"]
    for key in ("host", "hostname", "ip", "mac"):
        assert backend[key] == "**REDACTED**"

    assert backend["model"] == "Antminer S9"
    assert backend["firmware"] == "Braiins OS+"
    assert backend["capabilities"] == {"power_limit": True}
    assert result["last_update_success"] is True
    assert result["failure_count"] == 0


@pytest.mark.asyncio
async def test_diagnostics_do_not_rediscover_when_backend_exists() -> None:
    """Generating diagnostics should not create a second backend session."""
    async def unexpected_discovery():
        raise AssertionError("diagnostics unexpectedly rediscovered the miner")

    coordinator = SimpleNamespace(
        backend=FakeBackend(),
        get_miner=unexpected_discovery,
        last_update_success=False,
        _failure_count=2,
    )
    entry = SimpleNamespace(
        entry_id="entry-2",
        title="Miner",
        domain=DOMAIN,
        version=2,
        minor_version=0,
    )
    hass = SimpleNamespace(data={DOMAIN: {entry.entry_id: coordinator}})

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["failure_count"] == 2
    assert result["last_update_success"] is False
