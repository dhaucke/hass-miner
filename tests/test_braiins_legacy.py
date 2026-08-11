"""Regression tests for the legacy Braiins S9 backend."""

import pytest

from custom_components.miner.backends.base import UnsafeConfigurationError
from custom_components.miner.backends.braiins_legacy import update_power_target

VALID_CONFIG = """[format]
version = \"2.0\"
generator = \"pyasic\"
model = \"Antminer S9\"
timestamp = 1786375662

[temp_control]
mode = \"manual\"
hot_temp = 90

[fan_control]
min_fans = 1
speed = 100

[autotuning]
enabled = true
mode = \"power_target\"
power_target = 1000

[[group]]
name = \"Default\"
pool = [{url = \"stratum+tcp://example.invalid:3333\", user = \"worker\", password = \"\"}]
quota = 1
"""


def test_update_power_target_changes_only_target() -> None:
    """Changing power must preserve unrelated configuration text."""
    updated = update_power_target(VALID_CONFIG, 600)

    assert "power_target = 600" in updated
    assert 'model = "Antminer S9"' in updated
    assert 'user = "worker"' in updated
    assert updated.replace("power_target = 600", "power_target = 1000") == VALID_CONFIG


@pytest.mark.parametrize("value", [399, 1100, 450])
def test_update_power_target_rejects_unsafe_range(value: int) -> None:
    """S9-specific range and step must be enforced before a write."""
    with pytest.raises(ValueError):
        update_power_target(VALID_CONFIG, value)


def test_update_power_target_rejects_blank_model() -> None:
    """Regression test for the pyasic model corruption incident."""
    corrupt = VALID_CONFIG.replace('model = "Antminer S9"', 'model = " "')

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(corrupt, 600)


def test_update_power_target_rejects_other_model() -> None:
    """S9 write logic must never be applied to another Antminer model."""
    other = VALID_CONFIG.replace('model = "Antminer S9"', 'model = "Antminer S19"')

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(other, 600)


def test_update_power_target_rejects_schema_change() -> None:
    """The backend must not invent a power_target schema it did not find."""
    missing = VALID_CONFIG.replace("power_target = 1000\n", "")

    with pytest.raises(UnsafeConfigurationError):
        update_power_target(missing, 600)
