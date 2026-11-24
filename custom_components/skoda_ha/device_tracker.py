"""Parking position as a device tracker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SkodaConfigEntry
from .entity import SkodaEntity, dig, setup_dynamic


class SkodaTracker(SkodaEntity, TrackerEntity):
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "parking_position")

    def _coords(self) -> dict[str, Any] | None:
        pos = dig(self.data.vehicle, "parkingPosition")
        # While driving (IN_MOTION) the API gives no position -> unknown.
        if dig(pos, "state") == "PARKED" and isinstance(dig(pos, "gpsCoordinates"), dict):
            return pos["gpsCoordinates"]
        return None

    @property
    def latitude(self) -> float | None:
        return (self._coords() or {}).get("latitude")

    @property
    def longitude(self) -> float | None:
        return (self._coords() or {}).get("longitude")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "address": dig(self.data.vehicle, "parkingPosition", "formattedAddress"),
            "parking_state": dig(self.data.vehicle, "parkingPosition", "state"),
        }


async def async_setup_entry(
    hass: HomeAssistant, entry: SkodaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    setup_dynamic(
        entry,
        coordinator,
        async_add_entities,
        [("parking_position", lambda d: dig(d.vehicle, "parkingPosition"), lambda: SkodaTracker(coordinator))],
    )
