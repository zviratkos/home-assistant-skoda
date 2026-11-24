"""Minimal async client for the MyŠkoda Public API (X-API-Key auth)."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import API_BASE_URL, DEFAULT_RETRY_AFTER, MAX_RETRY_AFTER

_LOGGER = logging.getLogger(__name__)

TIMEOUT = ClientTimeout(total=30)


class SkodaApiError(Exception):
    """Generic API error."""


class SkodaConnectionError(SkodaApiError):
    """Network / timeout / 5xx problem."""


class SkodaAuthError(SkodaApiError):
    """401/403: key expired or not authorised for this VIN."""


class SkodaNotFoundError(SkodaApiError):
    """404: unknown VIN."""


class SkodaRateLimitError(SkodaApiError):
    """429: quota exhausted or vehicle not accepting requests."""

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class SkodaData:
    """Parsed response of GET /vehicles/{vin}."""

    vehicle: dict[str, Any]
    errors: list[dict[str, Any]] = field(default_factory=list)
    rate_limit_remaining: int | None = None
    rate_limit_limit: int | None = None
    key_expires_at: str | None = None


def _int_header(headers: Any, name: str) -> int | None:
    try:
        return int(headers[name])
    except (KeyError, TypeError, ValueError):
        return None


def _mask(vin: str) -> str:
    return f"...{vin[-6:]}"


class SkodaPublicApi:
    """Client bound to one API key + one VIN."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        vin: str,
        base_url: str = API_BASE_URL,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self.vin = vin
        self._base_url = base_url.rstrip("/")

    async def async_get_vehicle(self) -> SkodaData:
        """Fetch all vehicle data (costs exactly one request of the quota)."""
        url = f"{self._base_url}/vehicles/{self.vin}"
        headers = {"X-API-Key": self._api_key, "Accept": "application/json"}
        _LOGGER.debug("GET %s (key redacted)", url.replace(self.vin, _mask(self.vin)))

        try:
            async with self._session.get(
                url, headers=headers, timeout=TIMEOUT, allow_redirects=False
            ) as resp:
                remaining = _int_header(resp.headers, "RateLimit-Remaining")
                limit = _int_header(resp.headers, "RateLimit-Limit")
                reset = _int_header(resp.headers, "RateLimit-Reset")
                expires = resp.headers.get("X-API-Key-Expires-At")
                _LOGGER.debug(
                    "Response %s for %s: ratelimit %s/%s reset=%ss key_expires=%s",
                    resp.status, _mask(self.vin), remaining, limit, reset, expires,
                )

                if resp.status == 200:
                    payload = await resp.json(content_type=None)
                    if not isinstance(payload, dict) or "vehicle" not in payload:
                        raise SkodaApiError("Unexpected response: missing 'vehicle'")
                    errors = payload.get("errors") or []
                    for err in errors:
                        # Partial data is normal (unsupported/asleep) -> informational.
                        _LOGGER.debug(
                            "API omitted part for %s: %s - %s",
                            _mask(self.vin), err.get("type"), err.get("description"),
                        )
                    return SkodaData(
                        vehicle=payload["vehicle"] or {},
                        errors=errors,
                        rate_limit_remaining=remaining,
                        rate_limit_limit=limit,
                        key_expires_at=expires,
                    )

                problem = await self._problem(resp)
                if resp.status in (401, 403):
                    raise SkodaAuthError(f"{resp.status} {problem}")
                if resp.status == 404:
                    raise SkodaNotFoundError(f"404 {problem}")
                if resp.status == 429:
                    retry = _int_header(resp.headers, "Retry-After") or reset
                    retry = min(retry or DEFAULT_RETRY_AFTER, MAX_RETRY_AFTER)
                    raise SkodaRateLimitError(f"429 {problem}", retry)
                raise SkodaConnectionError(f"HTTP {resp.status} {problem}")
        except TimeoutError as err:
            raise SkodaConnectionError("Timeout talking to Škoda API") from err
        except ClientError as err:
            raise SkodaConnectionError(f"Connection error: {err}") from err

    @staticmethod
    async def _problem(resp: Any) -> str:
        """Extract RFC 9457 problem type/detail for log messages."""
        try:
            body = await resp.json(content_type=None)
            return f"{body.get('type', '')} {body.get('detail', '')}".strip()
        except Exception:  # noqa: BLE001 - diagnostics only
            return ""
