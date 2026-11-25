"""DataUpdateCoordinator: one poll = one API request per VIN."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SkodaApiError,
    SkodaAuthError,
    SkodaData,
    SkodaPublicApi,
    SkodaRateLimitError,
    SkodaUnavailableError,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class SkodaCoordinator(DataUpdateCoordinator[SkodaData]):
    """Polls the public API and backs off when rate limited."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: SkodaPublicApi) -> None:
        self.api = api
        self.interval_minutes = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        self._base_interval = timedelta(minutes=self.interval_minutes)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} ...{api.vin[-6:]}",
            update_interval=self._base_interval,
        )

    async def _async_update_data(self) -> SkodaData:
        try:
            data = await self.api.async_get_vehicle()
        except SkodaAuthError as err:
            # Key expired / revoked / not valid for this VIN -> HA starts reauth.
            raise ConfigEntryAuthFailed(str(err)) from err
        except SkodaRateLimitError as err:
            wait = err.retry_after + 30
            _LOGGER.warning(
                "Škoda API rate limit hit (%s); pausing polling for %s s", err, wait
            )
            self.update_interval = timedelta(seconds=wait)
            if self.data is not None:
                return self.data  # keep last known state instead of going unavailable
            raise UpdateFailed(f"Rate limited: {err}") from err
        except SkodaUnavailableError as err:
            # Temporary backend/vehicle outage: keep last state, try again next poll.
            _LOGGER.warning("Škoda API temporarily unavailable: %s", err)
            if self.data is not None:
                return self.data
            raise UpdateFailed(str(err)) from err
        except SkodaApiError as err:
            raise UpdateFailed(str(err)) from err

        self.update_interval = self._base_interval
        _LOGGER.debug(
            "Update OK: %d top-level parts, %d omitted, quota remaining=%s",
            len(data.vehicle), len(data.errors), data.rate_limit_remaining,
        )
        return data
