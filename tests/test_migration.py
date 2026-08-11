"""Config-entry migration regression tests."""

from types import SimpleNamespace

import pytest

from custom_components.miner import async_migrate_entry
from custom_components.miner.const import CONF_IP
from custom_components.miner.const import CONF_MAX_POWER
from custom_components.miner.const import CONF_MIN_POWER


class FakeConfigEntries:
    """Capture Home Assistant config-entry updates."""

    def __init__(self) -> None:
        """Initialize the update recorder."""
        self.updates: list[dict[str, object]] = []

    def async_update_entry(self, entry, **kwargs) -> None:
        """Record one migration update."""
        self.updates.append(kwargs)


@pytest.mark.asyncio
async def test_version_one_power_ranges_move_to_options() -> None:
    """Legacy min/max values should migrate without touching host data."""
    config_entries = FakeConfigEntries()
    hass = SimpleNamespace(config_entries=config_entries)
    entry = SimpleNamespace(
        version=1,
        data={CONF_IP: "192.168.1.50", CONF_MIN_POWER: 300, CONF_MAX_POWER: 1500},
        options={},
    )

    assert await async_migrate_entry(hass, entry)

    assert config_entries.updates == [
        {
            "data": {CONF_IP: "192.168.1.50"},
            "options": {CONF_MIN_POWER: 300, CONF_MAX_POWER: 1500},
            "version": 2,
            "minor_version": 0,
        }
    ]


@pytest.mark.asyncio
async def test_existing_options_win_during_migration() -> None:
    """User options must not be overwritten by stale version-one data."""
    config_entries = FakeConfigEntries()
    hass = SimpleNamespace(config_entries=config_entries)
    entry = SimpleNamespace(
        version=1,
        data={CONF_IP: "miner.local", CONF_MIN_POWER: 100, CONF_MAX_POWER: 900},
        options={CONF_MIN_POWER: 400, CONF_MAX_POWER: 1000},
    )

    assert await async_migrate_entry(hass, entry)

    update = config_entries.updates[0]
    assert update["data"] == {CONF_IP: "miner.local"}
    assert update["options"] == {CONF_MIN_POWER: 400, CONF_MAX_POWER: 1000}


@pytest.mark.asyncio
async def test_current_entry_needs_no_update() -> None:
    """Version-two entries should remain untouched."""
    config_entries = FakeConfigEntries()
    hass = SimpleNamespace(config_entries=config_entries)
    entry = SimpleNamespace(version=2, data={CONF_IP: "miner.local"}, options={})

    assert await async_migrate_entry(hass, entry)
    assert config_entries.updates == []
