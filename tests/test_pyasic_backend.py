"""Safety tests for the generic pyasic compatibility backend."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import UnsafeConfigurationError
from custom_components.miner.backends.pyasic_backend import PyasicBackend


class BOSMiner(SimpleNamespace):
    """Minimal object whose runtime type matches pyasic's legacy BOSMiner."""


@pytest.mark.asyncio
async def test_unknown_bosminer_is_read_only_for_config_writes() -> None:
    """Unknown legacy BOSMiner hardware must not use pyasic TOML rewrite paths."""
    miner = BOSMiner(
        supports_autotuning=True,
        supports_shutdown=True,
        supports_power_modes=True,
        expected_fans=4,
        expected_hashboards=3,
    )
    backend = PyasicBackend(miner, minimum_power=400, maximum_power=1400)

    assert backend.capabilities.power_limit is False
    assert backend.capabilities.power_modes is False
    assert backend.capabilities.pause_resume is True

    with pytest.raises(UnsafeConfigurationError):
        await backend.async_set_power_limit(600)

    with pytest.raises(UnsafeConfigurationError):
        await backend.async_set_power_mode("low")
