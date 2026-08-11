"""Power-limit range regression tests."""

import pytest

from custom_components.miner.backends.base import PowerLimitRange
from custom_components.miner.backends.braiins_legacy import S9_POWER_RANGE
from custom_components.miner.backends.braiins_legacy import update_power_target


VALID_S9_CONFIG = """[format]
version = '2.0'
model = 'Antminer S9'

[autotuning]
enabled = true
power_target = 1000
"""


def test_default_power_range_allows_single_watt_steps() -> None:
    """Manual Home Assistant number control should accept arbitrary integer watts."""
    power_range = PowerLimitRange(minimum=15, maximum=10000)

    power_range.validate(1200)
    power_range.validate(1234)


def test_s9_range_uses_single_watt_granularity() -> None:
    """Validated S9 power targets may be any integer watt inside the safe range."""
    assert S9_POWER_RANGE.minimum == 400
    assert S9_POWER_RANGE.maximum == 1400
    assert S9_POWER_RANGE.step == 1

    updated = update_power_target(VALID_S9_CONFIG, 1234)
    assert "power_target = 1234" in updated


@pytest.mark.parametrize("value", [399, 1401])
def test_s9_range_still_rejects_values_outside_safe_bounds(value: int) -> None:
    """Removing the artificial 100 W step must not relax the S9 safety bounds."""
    with pytest.raises(ValueError):
        update_power_target(VALID_S9_CONFIG, value)
