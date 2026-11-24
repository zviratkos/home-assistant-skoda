"""Shared entity base, safe accessors and dynamic entity discovery."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import SkodaData
from .const import DOMAIN
from .coordinator import SkodaCoordinator

_LOGGER = logging.getLogger(__name__)


def dig(obj: Any, *path: str) -> Any:
    """Nested dict lookup; any missing/non-dict level -> None.

    The API omits unsupported/unavailable parts, so a missing field means
    "unknown", never a specific value.
    """
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def engine(vehicle: dict[str, Any], electric: bool) -> dict[str, Any] | None:
    """Return the electric (or the non-electric) engine block of fuelStatus."""
    for key in ("primaryEngineRange", "secondaryEngineRange"):
        block = dig(vehicle, "fuelStatus", key)
        if isinstance(block, dict) and (block.get("engineType") == "ELECTRIC") == electric:
            return block
    return None


def lower(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) else None


def parse_ts(value: Any) -> datetime | None:
    """Parse ISO-8601 (or HTTP-date) into an aware datetime."""
    if not isinstance(value, str):
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            _LOGGER.debug("Unparseable timestamp %r", value)
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class SkodaEntity(CoordinatorEntity[SkodaCoordinator]):
    """Base entity: one device per VIN, unique_id = <vin>_<key>."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SkodaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        vin = coordinator.api.vin
        self._attr_unique_id = f"{vin}_{key}"
        self._attr_translation_key = key
        name = dig(coordinator.data.vehicle, "name") or f"Škoda ...{vin[-6:]}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vin)},
            manufacturer="Škoda",
            name=name,
            serial_number=vin,
        )

    @property
    def data(self) -> SkodaData:
        return self.coordinator.data


Item = tuple[str, Callable[[SkodaData], Any], Callable[[], Entity]]


def setup_dynamic(
    entry: ConfigEntry,
    coordinator: SkodaCoordinator,
    async_add_entities: AddEntitiesCallback,
    items: Iterable[Item],
) -> None:
    """Add each entity once its data first appears in the API response.

    The API may omit a part temporarily (vehicle asleep), so entities are
    discovered on every update instead of only at setup.
    """
    items = list(items)
    known: set[str] = set()

    @callback
    def _discover() -> None:
        new: list[Entity] = []
        for key, value_fn, factory in items:
            if key not in known and value_fn(coordinator.data) is not None:
                known.add(key)
                new.append(factory())
                _LOGGER.debug("Discovered entity %s", key)
        if new:
            async_add_entities(new)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))
