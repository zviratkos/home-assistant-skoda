"""Sensors - ported from the old MySkoda integration, limited to what the public API offers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SkodaConfigEntry
from .api import SkodaData
from .entity import SkodaEntity, dig, engine, lower, parse_ts, setup_dynamic

_LOGGER = logging.getLogger(__name__)

# Old integration: the API sometimes returned 429_496_729 (uint32 overflow) for mileage.
ODOMETER_MAX_VALID = 400_000_000


@dataclass(frozen=True, kw_only=True)
class SkodaSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SkodaData], Any]


def _soc(d: SkodaData) -> float | None:
    v = dig(d.vehicle, "charging", "status", "battery", "stateOfChargeInPercent")
    if v is None and (e := engine(d.vehicle, True)):
        v = e.get("currentSoCInPercent")
    return None if v is None else min(v, 100)


def _electric_range(d: SkodaData) -> float | None:
    if (e := engine(d.vehicle, True)) and e.get("remainingRangeInKm") is not None:
        return e["remainingRangeInKm"]
    m = dig(d.vehicle, "charging", "status", "battery", "remainingCruisingRangeInMeters")
    return None if m is None else round(m / 1000, 1)


def _fuel(field: str) -> Callable[[SkodaData], Any]:
    # Any non-electric engine: gasoline / diesel / CNG ...
    return lambda d: (e.get(field) if (e := engine(d.vehicle, False)) else None)


def _remaining_charge_time(d: SkodaData) -> int | None:
    if dig(d.vehicle, "charging", "status", "state") == "CONNECT_CABLE":
        return None  # old integration: no estimate without a cable
    return dig(d.vehicle, "charging", "status", "remainingTimeToFullyChargedInMinutes")


def _target_temp(d: SkodaData) -> float | None:
    t = dig(d.vehicle, "airConditioning", "targetTemperature")
    if not isinstance(t, dict) or t.get("value") is None:
        return None
    v = t["value"]
    return round((v - 32) * 5 / 9, 1) if t.get("unit") == "FAHRENHEIT" else v


def _last_update(d: SkodaData) -> datetime | None:
    stamps = [
        parse_ts(dig(d.vehicle, part, "carCapturedTimestamp"))
        for part in ("status", "odometer", "fuelStatus", "charging", "airConditioning", "activeVentilation")
    ]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


def _dist(key: str, fn: Callable[[SkodaData], Any], **kw: Any) -> SkodaSensorDescription:
    return SkodaSensorDescription(
        key=key,
        value_fn=fn,
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        **kw,
    )


SENSORS: tuple[SkodaSensorDescription, ...] = (
    SkodaSensorDescription(
        key="battery_level",
        value_fn=_soc,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _dist("electric_range", _electric_range),
    _dist("total_range", lambda d: dig(d.vehicle, "fuelStatus", "totalRangeInKm")),
    SkodaSensorDescription(
        key="fuel_level",
        value_fn=_fuel("currentFuelLevelInPercent"),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _dist("fuel_range", _fuel("remainingRangeInKm")),
    _dist("adblue_range", lambda d: dig(d.vehicle, "fuelStatus", "adBlueRange")),
    SkodaSensorDescription(  # replaced by OdometerSensor below
        key="odometer",
        value_fn=lambda d: dig(d.vehicle, "odometer", "mileageInKm"),
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SkodaSensorDescription(
        key="charging_state",
        value_fn=lambda d: lower(dig(d.vehicle, "charging", "status", "state")),
    ),
    SkodaSensorDescription(
        key="charge_type",
        value_fn=lambda d: lower(dig(d.vehicle, "charging", "status", "chargeType")),
    ),
    SkodaSensorDescription(
        key="charging_power",
        value_fn=lambda d: dig(d.vehicle, "charging", "status", "chargePowerInKw"),
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SkodaSensorDescription(
        key="charging_rate",
        value_fn=lambda d: dig(d.vehicle, "charging", "status", "chargingRateInKilometersPerHour"),
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SkodaSensorDescription(
        key="remaining_charging_time",
        value_fn=_remaining_charge_time,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    SkodaSensorDescription(
        key="target_battery_level",
        value_fn=lambda d: dig(d.vehicle, "charging", "settings", "targetStateOfChargeInPercent"),
        native_unit_of_measurement=PERCENTAGE,
    ),
    SkodaSensorDescription(
        key="air_conditioning_state",
        value_fn=lambda d: lower(dig(d.vehicle, "airConditioning", "state")),
    ),
    SkodaSensorDescription(
        key="air_conditioning_target_temperature",
        value_fn=_target_temp,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    SkodaSensorDescription(
        key="air_conditioning_ready_at",
        value_fn=lambda d: parse_ts(
            dig(d.vehicle, "airConditioning", "estimatedReachOfTargetTemperatureAt")
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SkodaSensorDescription(
        key="active_ventilation_state",
        value_fn=lambda d: lower(dig(d.vehicle, "activeVentilation", "state")),
    ),
    SkodaSensorDescription(
        key="car_captured",
        value_fn=_last_update,
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # --- API housekeeping (from response headers) ---
    SkodaSensorDescription(
        key="api_requests_remaining",
        value_fn=lambda d: d.rate_limit_remaining,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SkodaSensorDescription(
        key="api_key_expires_at",
        value_fn=lambda d: parse_ts(d.key_expires_at),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


class SkodaSensor(SkodaEntity, SensorEntity):
    entity_description: SkodaSensorDescription

    def __init__(self, coordinator, description: SkodaSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.data)


class OdometerSensor(SkodaSensor):
    """Mileage never goes down and ignores the API's overflow value (old-integration workaround)."""

    _last: int | None = None

    @property
    def native_value(self) -> int | None:
        new = self.entity_description.value_fn(self.data)
        if not isinstance(new, int | float) or new >= ODOMETER_MAX_VALID:
            if new is not None:
                _LOGGER.debug("Ignoring invalid odometer value %r", new)
            return self._last
        if self._last is not None and new < self._last:
            _LOGGER.debug("Ignoring decreasing odometer %s < %s", new, self._last)
            return self._last
        self._last = new
        return new


async def async_setup_entry(
    hass: HomeAssistant, entry: SkodaConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    setup_dynamic(
        entry,
        coordinator,
        async_add_entities,
        [
            (
                d.key,
                d.value_fn,
                (lambda d=d: (OdometerSensor if d.key == "odometer" else SkodaSensor)(coordinator, d)),
            )
            for d in SENSORS
        ],
    )
