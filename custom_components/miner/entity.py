"""Shared Home Assistant entity helpers for Miner."""
from __future__ import annotations

from homeassistant.helpers import device_registry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MinerCoordinator


class MinerEntity(CoordinatorEntity[MinerCoordinator]):
    """Base entity with shared device metadata."""

    @property
    def device_info(self) -> DeviceInfo:
        """Return normalized device metadata for the miner."""
        mac = self.coordinator.data.get("mac")
        ip = self.coordinator.data.get("ip")

        identifiers = {(DOMAIN, mac or ip or self.coordinator.config_entry.entry_id)}
        connections = set()
        if ip:
            connections.add(("ip", ip))
        if mac:
            connections.add((device_registry.CONNECTION_NETWORK_MAC, mac))

        return DeviceInfo(
            identifiers=identifiers,
            connections=connections,
            configuration_url=f"http://{ip}" if ip else None,
            manufacturer=self.coordinator.data.get("make"),
            model=self.coordinator.data.get("model"),
            sw_version=self.coordinator.data.get("fw_ver"),
            name=self.coordinator.config_entry.title,
        )

    @property
    def available(self) -> bool:
        """Return whether the underlying coordinator is available."""
        return self.coordinator.available
