"""Telemetry regressions from a real Antminer S9 on Braiins OS+ 22.08.1."""

from types import SimpleNamespace

import pytest

from custom_components.miner.backends.base import BackendKind
from custom_components.miner.backends.base import HashboardData
from custom_components.miner.backends.base import MinerSnapshot
from custom_components.miner.backends.braiins_legacy import BraiinsLegacyS9Backend
from custom_components.miner.backends.braiins_legacy import _s9_hashboards_from_temps
from custom_components.miner.backends.braiins_legacy import _s9_hashrates_from_devs
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

# Same device/offset scheme as REAL_S9_TEMPS (IDs 6/7/8); MHS values chosen so
# the boards sum to roughly the 8.928 TH/s the aggregate sensor reports.
REAL_S9_DEVS = {
    "STATUS": [
        {
            "STATUS": "S",
            "Code": 9,
            "Msg": "3 PGA(s)",
            "Description": "BOSer boser-openwrt 0.1.0-26ba61b9",
        }
    ],
    "DEVS": [
        {"ASC": 0, "ID": 6, "MHS 1m": 2976500.25, "Status": "Alive"},
        {"ASC": 1, "ID": 7, "MHS 1m": 2981200.5, "Status": "Alive"},
        {"ASC": 2, "ID": 8, "MHS 1m": 2965300.75, "Status": "Alive"},
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


def test_real_s9_devs_produce_per_board_hashrate_in_th() -> None:
    """Parse the real BOSer 4028 'devs' response into TH/s per board."""
    hashrates = _s9_hashrates_from_devs(REAL_S9_DEVS)

    assert hashrates == {
        0: pytest.approx(2.97650025),
        1: pytest.approx(2.9812005),
        2: pytest.approx(2.96530075),
    }


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
    # Without a devs() RPC on the fake miner, board hashrate stays whatever
    # pyasic's generic snapshot provided (nothing here) - must not error out.
    assert snapshot.hashboards[0].hashrate is None


@pytest.mark.asyncio
async def test_refresh_exposes_real_per_board_hashrate_from_devs_rpc(
    monkeypatch,
) -> None:
    """Regression: pyasic resolved this device to a web/gRPC hashboard reader.

    That reader has no endpoint on this old firmware, so board_hashrate
    silently stayed 'unknown' forever even though the aggregate hashrate
    sensor worked. Board hashrate must now come from the same legacy devs
    RPC that already supplies temps.
    """

    class FakeRPC:
        async def temps(self):
            return REAL_S9_TEMPS

        async def devs(self):
            return REAL_S9_DEVS

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
            # pyasic's own (broken, web/gRPC-based) reading for this legacy
            # device: boards exist but never got a hashrate.
            hashboards=(
                HashboardData(slot=0),
                HashboardData(slot=1),
                HashboardData(slot=2),
            ),
        )

    monkeypatch.setattr(PyasicBackend, "async_refresh", generic_refresh)

    snapshot = await backend.async_refresh()

    assert [board.hashrate for board in snapshot.hashboards] == [
        pytest.approx(2.97650025),
        pytest.approx(2.9812005),
        pytest.approx(2.96530075),
    ]
