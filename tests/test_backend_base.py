"""Tests for backend contracts."""

import pytest

from custom_components.miner.backends.base import PowerLimitRange


def test_power_limit_range_accepts_valid_steps() -> None:
    """Values inside the configured stepped range are accepted."""
    power_range = PowerLimitRange(minimum=400, maximum=1000, step=100)

    for value in (400, 500, 600, 700, 800, 900, 1000):
        power_range.validate(value)


@pytest.mark.parametrize("value", [300, 1100, 450, 999])
def test_power_limit_range_rejects_invalid_values(value: int) -> None:
    """Out-of-range and off-step values are rejected."""
    power_range = PowerLimitRange(minimum=400, maximum=1000, step=100)

    with pytest.raises(ValueError):
        power_range.validate(value)
