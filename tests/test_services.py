"""Tests for Miner Home Assistant service helpers."""

from custom_components.miner.services import _normalize_device_ids


def test_normalize_device_ids_handles_single_selector_value() -> None:
    """A single device id must not be iterated character-by-character."""
    assert _normalize_device_ids("device-123") == ["device-123"]


def test_normalize_device_ids_handles_multiple_values() -> None:
    """Multiple selection remains a list of device ids."""
    assert _normalize_device_ids(["device-1", "device-2"]) == [
        "device-1",
        "device-2",
    ]


def test_normalize_device_ids_handles_empty_value() -> None:
    """Missing selectors resolve to no target devices."""
    assert _normalize_device_ids(None) == []
