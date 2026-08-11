"""Telemetry regressions from a real Antminer S9 on Braiins OS+ 22.08.1."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import BackendKind
from custom_components.miner.backends.base import MinerSnapshot
from custom_components.miner.backends.braiins_legacy import BraiinsLegacyS9Backend
from custom_components.miner.backends.braiins_legacy import _s9_hashboards_from_temps
from custom_components.miner.backends.pyasic_backend import PyasicBackend

REAL_S9_TEMPS = {
    "STATUS": [
        {
            "STATUS": "S",
            "Code": 201,
            "Msg": "3 Temp(s)",
            "Description": "BOSer boser-openwrt 0.1.0-26ba61b9",
        }
    ],
    "TEMPS": [
        {"Board": 43.5, "Chip": 54.1875, "ID": 6, "TEMP": 0},
        {"Board": 42.625, "Chip": 54.8125, "ID": 7, "TEMP": 1},
        {"Board": 42.3125, "Chip": 54.6875, "ID": 8, "TEMP": 2},
    ],
    "id": 1,
}


def test_real_s9_temps_create_three_normalized_hashboards() -> None:
    """Use the actual BOSer 4028 response instead of assumed S9 topology."""
    boards = _s9_hashboards_from_temps(REAL_S9_TEMPS)

    assert [board.slot for board in boards] == [0, 1, 2]
    assert [board.temperature for board in boards] == [43.5, 42.625, 42.3125]
    assert [board.chip_temperature for board in boards] == [
        54.1875,
        54.8125,
        54.6875,
    ]


@pytest.mark.asyncio
async def test_refresh_exposes_real_hashboard_temps_and_average(monkeypatch) -> None:
    """Populate HA topology when pyasic cannot identify the old BOS+ S9 model."""

    class FakeRPC:
        async def temps(self):
            return REAL_S9_TEMPS

    miner = SimpleNamespace(
        rpc=FakeRPC(),
        supports_autotuning=True,
        supports_shutdown=False,
        supports_power_modes=False,
        expected_fans=0,
        expected_hashboards=0,
    )
    backend = BraiinsLegacyS9Backend(miner)
    backend._identity_validated = True

    async def generic_refresh(_self) -> MinerSnapshot:
        return MinerSnapshot(
            host="192.0.2.10",
            backend=BackendKind.PYASIC,
            firmware="22.08.1",
            power_limit=1000,
            temperature=None,
            active_preset_name=None,
            hashboards=(),
        )

    monkeypatch.setattr(PyasicBackend, "async_refresh", generic_refresh)

    snapshot = await backend.async_refresh()

    assert snapshot.backend is BackendKind.BRAIINS_LEGACY
    assert snapshot.temperature == 42.81
    assert snapshot.active_preset_name == "Power Target"
    assert [board.slot for board in snapshot.hashboards] == [0, 1, 2]
    assert snapshot.hashboards[0].temperature == 43.5
    assert snapshot.hashboards[2].chip_temperature == 54.6875
    assert backend.capabilities.hashboards is True
