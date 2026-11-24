"""Škoda (Public API) - minimal read-only integration."""

from __future__ import annotations

import logging

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SkodaPublicApi
from .const import CONF_SCAN_INTERVAL, CONF_VIN, DEFAULT_SCAN_INTERVAL
from .coordinator import SkodaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER]

type SkodaConfigEntry = ConfigEntry[SkodaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SkodaConfigEntry) -> bool:
    """Set up one vehicle (one VIN per config entry)."""
    api = SkodaPublicApi(
        async_get_clientsession(hass), entry.data[CONF_API_KEY], entry.data[CONF_VIN]
    )
    coordinator = SkodaCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Reload when the polling interval option changes (key changes reload via the config flow).
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: SkodaConfigEntry) -> None:
    new = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    if new != entry.runtime_data.interval_minutes:
        _LOGGER.debug("Polling interval changed to %s min, reloading", new)
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SkodaConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
