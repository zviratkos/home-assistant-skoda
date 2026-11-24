"""Binary sensors: doors, windows, lights, lock, charging, plug, air conditioning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SkodaConfigEntry
from .api import SkodaData
from .entity import SkodaEntity, dig, setup_dynamic


@dataclass(frozen=True, kw_only=True)
class SkodaBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[SkodaData], bool | None]


def _flag(path: tuple[str, ...], on: str, off: str) -> Callable[[SkodaData], bool | None]:
    """True/False for the two known values, None for UNKNOWN/UNSUPPORTED/missing."""

    def fn(d: SkodaData) -> bool | None:
        v = dig(d.vehicle, *path)
        return True if v == on else False if v == off else None

    return fn


def _unlocked(d: SkodaData) -> bool | None:
    """HA LOCK class: on = unlocked. reliableLockStatus wins over doorsLocked."""
    rel = dig(d.vehicle, "status", "overall", "reliableLockStatus")
    if rel in ("LOCKED", "UNLOCKED"):
        return rel == "UNLOCKED"
    dl = dig(d.vehicle, "status", "overall", "doorsLocked")
    if dl == "YES":
        return False
    if dl in ("NO", "OPENED", "TRUNK_OPENED"):
        return True
    return None


_CABLE_IN = {"CHARGING", "CONSERVING", "READY_FOR_CHARGING", "CHARGING_INTERRUPTED"}


def _charging(d: SkodaData) -> bool | None:
    state = dig(d.vehicle, "charging", "status", "state")
    return None if state is None else state == "CHARGING"


def _plug(d: SkodaData) -> bool | None:
    p = dig(d.vehicle, "charging", "status", "plugConnectionState")
    if p in ("CONNECTED", "DISCONNECTED"):
        return p == "CONNECTED"
    state = dig(d.vehicle, "charging", "status", "state")  # fallback as in the old integration
    if state in _CABLE_IN:
        return True
    return False if state == "CONNECT_CABLE" else None


def _ac_active(d: SkodaData) -> bool | None:
    s = dig(d.vehicle, "airConditioning", "state")
    if s in ("COOLING", "HEATING", "HEATING_AUXILIARY", "VENTILATION"):
        return True
    return False if s in ("OFF", "COMPLETED") else None


_OVERALL = ("status", "overall")
_DETAIL = ("status", "detail")

BINARY_SENSORS: tuple[SkodaBinaryDescription, ...] = (
    SkodaBinaryDescription(key="doors", value_fn=_flag((*_OVERALL, "doors"), "OPEN", "CLOSED"),
                           device_class=BinarySensorDeviceClass.DOOR),
    SkodaBinaryDescription(key="windows", value_fn=_flag((*_OVERALL, "windows"), "OPEN", "CLOSED"),
                           device_class=BinarySensorDeviceClass.WINDOW),
    SkodaBinaryDescription(key="lights", value_fn=_flag((*_OVERALL, "lights"), "ON", "OFF"),
                           device_class=BinarySensorDeviceClass.LIGHT),
    SkodaBinaryDescription(key="lock", value_fn=_unlocked, device_class=BinarySensorDeviceClass.LOCK),
    SkodaBinaryDescription(key="trunk", value_fn=_flag((*_DETAIL, "trunk"), "OPEN", "CLOSED"),
                           device_class=BinarySensorDeviceClass.DOOR),
    SkodaBinaryDescription(key="bonnet", value_fn=_flag((*_DETAIL, "bonnet"), "OPEN", "CLOSED"),
                           device_class=BinarySensorDeviceClass.DOOR),
    SkodaBinaryDescription(key="sunroof", value_fn=_flag((*_DETAIL, "sunroof"), "OPEN", "CLOSED"),
                           device_class=BinarySensorDeviceClass.OPENING),
    SkodaBinaryDescription(key="charging", value_fn=_charging,
                           device_class=BinarySensorDeviceClass.BATTERY_CHARGING),
    SkodaBinaryDescription(key="plug", value_fn=_plug, device_class=BinarySensorDeviceClass.PLUG),
    SkodaBinaryDescription(key="air_conditioning", value_fn=_ac_active,
                           device_class=BinarySensorDeviceClass.RUNNING),
)


class SkodaBinarySensor(SkodaEntity, BinarySensorEntity):
    entity_description: SkodaBinaryDescription

    def __init__(self, coordinator, description: SkodaBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.data)


async def async_setup_entry(
    hass: HomeAssistant, entry: SkodaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    setup_dynamic(
        entry,
        coordinator,
        async_add_entities,
        [
            (d.key, d.value_fn, (lambda d=d: SkodaBinarySensor(coordinator, d)))
            for d in BINARY_SENSORS
        ],
    )
