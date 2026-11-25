from datetime import timedelta
import copy

import pytest
from homeassistant.config_entries import ConfigEntryState, SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.skoda_ha.const import DOMAIN, CONF_VIN

VIN = "TMBJB9NY5RF999999"
URL = f"https://public.api.connect.skoda-auto.cz/api/v1/vehicles/{VIN}"
HDR = {"RateLimit-Limit": "20", "RateLimit-Remaining": "17", "RateLimit-Reset": "1800",
       "X-API-Key-Expires-At": "2027-05-01T10:00:00Z"}

BEV = {"vehicle": {
    "vin": VIN, "name": "My Enyaq", "licensePlate": "1MB 1234",
    "status": {"carCapturedTimestamp": "2026-11-24T10:00:00Z",
               "overall": {"doorsLocked": "YES", "doors": "CLOSED", "windows": "CLOSED", "lights": "OFF", "reliableLockStatus": "LOCKED"},
               "detail": {"trunk": "CLOSED", "bonnet": "OPEN", "sunroof": "UNSUPPORTED"}},
    "odometer": {"mileageInKm": 12345, "carCapturedTimestamp": "2026-11-24T10:01:00Z"},
    "fuelStatus": {"carType": "ELECTRIC", "totalRangeInKm": 250,
                   "primaryEngineRange": {"engineType": "ELECTRIC", "currentSoCInPercent": 63, "remainingRangeInKm": 250}},
    "charging": {"carCapturedTimestamp": "2026-11-24T10:02:00Z",
                 "status": {"state": "CHARGING", "chargeType": "AC", "chargePowerInKw": 10.8,
                            "chargingRateInKilometersPerHour": 55.0, "remainingTimeToFullyChargedInMinutes": 95,
                            "plugConnectionState": "CONNECTED",
                            "battery": {"stateOfChargeInPercent": 63, "remainingCruisingRangeInMeters": 250000}},
                 "settings": {"targetStateOfChargeInPercent": 80}},
    "airConditioning": {"carCapturedTimestamp": "2026-11-24T10:03:00Z", "state": "HEATING",
                        "targetTemperature": {"value": 21.5, "unit": "CELSIUS"},
                        "estimatedReachOfTargetTemperatureAt": "2026-11-24T10:20:00Z"},
    "parkingPosition": {"state": "PARKED", "gpsCoordinates": {"latitude": 50.08, "longitude": 14.42},
                        "formattedAddress": "Praha"}},
    "errors": []}

DIESEL = {"vehicle": {"vin": VIN, "name": "Octavia",
    "odometer": {"mileageInKm": 99},
    "fuelStatus": {"carType": "DIESEL", "totalRangeInKm": 800, "adBlueRange": 5000,
                   "primaryEngineRange": {"engineType": "DIESEL", "currentFuelLevelInPercent": 70, "remainingRangeInKm": 800}}},
    "errors": [{"type": "charging-unsupported", "description": "x"}]}


def entry(hass):
    e = MockConfigEntry(domain=DOMAIN, unique_id=VIN, title="t", data={CONF_API_KEY: "k", CONF_VIN: VIN})
    e.add_to_hass(hass)
    return e


def state(hass, platform, key):
    reg = er.async_get(hass)
    eid = reg.async_get_entity_id(platform, DOMAIN, f"{VIN}_{key}")
    return hass.states.get(eid) if eid else None


async def test_bev(hass, aioclient_mock):
    aioclient_mock.get(URL, json=BEV, headers=HDR)
    e = entry(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert e.state is ConfigEntryState.LOADED
    assert aioclient_mock.mock_calls[0][3]["X-API-Key"] == "k"
    s = lambda p, k: state(hass, p, k).state
    assert s("sensor", "battery_level") == "63"
    assert s("sensor", "electric_range") == "250"
    assert s("sensor", "odometer") == "12345"
    assert s("sensor", "charging_state") == "charging"
    assert s("sensor", "charging_power") == "10.8"
    assert s("sensor", "remaining_charging_time") == "95"
    assert s("sensor", "target_battery_level") == "80"
    assert s("sensor", "air_conditioning_target_temperature") == "21.5"
    assert s("sensor", "api_requests_remaining") == "17"
    assert s("sensor", "car_captured").startswith("2026-11-24T10:03")
    assert s("sensor", "api_key_expires_at").startswith("2027-05-01T10:00")
    assert state(hass, "sensor", "fuel_level") is None  # not a combustion car
    assert state(hass, "sensor", "adblue_range") is None
    b = lambda k: state(hass, "binary_sensor", k).state
    assert b("doors") == "off" and b("lock") == "off" and b("bonnet") == "on"
    assert b("charging") == "on" and b("plug") == "on" and b("air_conditioning") == "on"
    assert state(hass, "binary_sensor", "sunroof") is None  # UNSUPPORTED -> no entity
    t = state(hass, "device_tracker", "parking_position")
    assert t.attributes["latitude"] == 50.08 and t.attributes["address"] == "Praha"
    assert state(hass, "sensor", "battery_level").attributes["friendly_name"] == "My Enyaq Battery level"


async def test_diesel_partial(hass, aioclient_mock):
    aioclient_mock.get(URL, json=DIESEL, headers=HDR)
    e = entry(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert state(hass, "sensor", "fuel_level").state == "70"
    assert state(hass, "sensor", "fuel_range").state == "800"
    assert state(hass, "sensor", "adblue_range").state == "5000"
    assert state(hass, "sensor", "battery_level") is None
    assert state(hass, "binary_sensor", "charging") is None
    assert state(hass, "device_tracker", "parking_position") is None


async def test_late_discovery_and_odometer_guard(hass, aioclient_mock):
    aioclient_mock.get(URL, json=DIESEL, headers=HDR)
    e = entry(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert state(hass, "device_tracker", "parking_position") is None
    bad = copy.deepcopy(BEV)
    bad["vehicle"]["odometer"]["mileageInKm"] = 429_496_729  # API overflow value
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=bad, headers=HDR)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert state(hass, "device_tracker", "parking_position") is not None  # appeared later
    assert state(hass, "sensor", "odometer").state == "99"  # overflow ignored, last kept


async def test_rate_limit_keeps_data_and_backs_off(hass, aioclient_mock):
    aioclient_mock.get(URL, json=BEV, headers=HDR)
    e = entry(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=429, headers={"Retry-After": "1200"}, json={"type": "x/rate-limit-exceeded"})
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert state(hass, "sensor", "battery_level").state == "63"  # still available
    assert e.runtime_data.update_interval == timedelta(seconds=1230)
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=BEV, headers=HDR)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1300))
    await hass.async_block_till_done()
    assert e.runtime_data.update_interval == timedelta(minutes=10)  # restored


async def test_auth_failure_starts_reauth(hass, aioclient_mock):
    aioclient_mock.get(URL, status=401, json={"type": "https://public.api.connect.skoda-auto.cz/problems/api-key-expired"})
    e = entry(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert e.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)
    # complete reauth with a new key
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=BEV, headers=HDR)
    flow = next(f for f in flows if f["context"]["source"] == "reauth")
    r = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_API_KEY: "newkey"})
    await hass.async_block_till_done()
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reauth_successful"
    assert e.data[CONF_API_KEY] == "newkey"
    assert e.state is ConfigEntryState.LOADED


async def test_config_flow(hass, aioclient_mock):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    # bad VIN
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_API_KEY: "k", CONF_VIN: "short"})
    assert r["errors"] == {CONF_VIN: "invalid_vin"}
    # rejected key
    aioclient_mock.get(URL, status=401, json={})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_API_KEY: "k", CONF_VIN: VIN.lower()})
    assert r["errors"] == {"base": "invalid_auth"}
    # ok
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=BEV, headers=HDR)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_API_KEY: "k", CONF_VIN: VIN})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["title"] == "My Enyaq" and r["data"] == {CONF_API_KEY: "k", CONF_VIN: VIN}
    await hass.async_block_till_done()
    # duplicate
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_API_KEY: "k", CONF_VIN: VIN})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_options_interval(hass, aioclient_mock):
    aioclient_mock.get(URL, json=BEV, headers=HDR)
    e = entry(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    r = await hass.config_entries.options.async_init(e.entry_id)
    r = await hass.config_entries.options.async_configure(r["flow_id"], {"scan_interval": 30})
    await hass.async_block_till_done()
    assert e.options["scan_interval"] == 30
    assert e.runtime_data.update_interval == timedelta(minutes=30)


async def test_config_flow_shows_reason(hass, aioclient_mock):
    aioclient_mock.get(URL, status=302, headers={"Location": "https://example.invalid/x"})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_API_KEY: "k", CONF_VIN: VIN})
    assert r["errors"] == {"base": "cannot_connect"}
    assert "HTTP 302 -> https://example.invalid/x" in r["description_placeholders"]["detail"]


from unittest.mock import AsyncMock, patch
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

B503 = {"detail": "Vehicle data is temporarily unavailable. Retry after 10 seconds.", "status": 503,
        "title": "Service Unavailable", "type": "about:blank"}


async def test_503_is_retried_then_succeeds(hass, aioclient_mock):
    calls = []

    async def side(method, url, data):
        calls.append(1)
        if len(calls) < 3:
            return AiohttpClientMockResponse(method, url, status=503, json=B503)
        return AiohttpClientMockResponse(method, url, json=BEV, headers=HDR)

    aioclient_mock.get(URL, side_effect=side)
    sleep = AsyncMock()
    with patch("custom_components.skoda_ha.api.asyncio.sleep", sleep):
        e = entry(hass)
        await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
    assert e.state is ConfigEntryState.LOADED and len(calls) == 3
    assert [c.args[0] for c in sleep.call_args_list if c.args[0]] == [10, 10]


async def test_config_flow_creates_entry_when_503(hass, aioclient_mock):
    aioclient_mock.get(URL, status=503, json=B503)
    with patch("custom_components.skoda_ha.api.asyncio.sleep", AsyncMock()):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_API_KEY: "k", CONF_VIN: VIN})
        await hass.async_block_till_done()
    assert r["type"] is FlowResultType.CREATE_ENTRY and r["data"][CONF_VIN] == VIN
    e = hass.config_entries.async_entries(DOMAIN)[0]
    assert e.state is ConfigEntryState.SETUP_RETRY  # HA keeps retrying


async def test_503_after_success_keeps_data(hass, aioclient_mock):
    aioclient_mock.get(URL, json=BEV, headers=HDR)
    e = entry(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, status=503, json=B503)
    with patch("custom_components.skoda_ha.api.asyncio.sleep", AsyncMock()):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
        await hass.async_block_till_done()
    assert state(hass, "sensor", "battery_level").state == "63"


# Anonymised copy of a real diesel Octavia response (fake VIN/plate/address/GPS).
REAL_VIN = "TMBXX8NX0RY000000"
REAL = {"vehicle": {
    "activeVentilation": {"state": "OFF", "carCapturedTimestamp": "2026-11-24T17:01:04Z", "durationInSeconds": 600},
    "fuelStatus": {"adBlueRange": 13500, "carCapturedTimestamp": "2026-11-24T17:02:00Z", "carType": "DIESEL",
                   "primaryEngineRange": {"currentFuelLevelInPercent": 37, "currentSoCInPercent": 37,
                                          "engineType": "DIESEL", "remainingRangeInKm": 250},
                   "totalRangeInKm": 250},
    "licensePlate": "1AB 0000", "name": "Octavia",
    "odometer": {"mileageInKm": 62952, "carCapturedTimestamp": "2026-11-24T17:02:00Z"},
    "operations": [{"name": "startActiveVentilation"}, {"name": "stopActiveVentilation"}],
    "parkingPosition": {"state": "PARKED", "formattedAddress": "Testova 1, Praha",
                        "gpsCoordinates": {"latitude": 50.0, "longitude": 14.5}},
    "renderUrl": "https://example.invalid/x.png",
    "status": {"overall": {"doorsLocked": "YES", "locked": "YES", "doors": "CLOSED", "windows": "UNKNOWN",
                           "lights": "OFF", "reliableLockStatus": "LOCKED"},
               "detail": {"sunroof": "UNSUPPORTED", "trunk": "CLOSED", "bonnet": "CLOSED"},
               "carCapturedTimestamp": "2026-11-24T17:02:00Z"},
    "vin": REAL_VIN}}


async def test_real_diesel_response(hass, aioclient_mock):
    url = f"https://public.api.connect.skoda-auto.cz/api/v1/vehicles/{REAL_VIN}"
    aioclient_mock.get(url, json=REAL)  # note: no "errors" key, no ratelimit headers
    e = MockConfigEntry(domain=DOMAIN, unique_id=REAL_VIN, data={CONF_API_KEY: "k", CONF_VIN: REAL_VIN})
    e.add_to_hass(hass)
    await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    assert e.state is ConfigEntryState.LOADED
    reg = er.async_get(hass)

    def st(p, k):
        eid = reg.async_get_entity_id(p, DOMAIN, f"{REAL_VIN}_{k}")
        return hass.states.get(eid) if eid else None

    for k, v in {"fuel_level": "37", "fuel_range": "250", "total_range": "250", "adblue_range": "13500",
                 "odometer": "62952", "active_ventilation_state": "off"}.items():
        assert st("sensor", k).state == v, k
    assert st("sensor", "car_captured").state.startswith("2026-11-24T17:02")
    for k in ("doors", "lock", "lights", "trunk", "bonnet"):
        assert st("binary_sensor", k).state == "off", k
    for k in ("windows", "sunroof"):  # UNKNOWN / UNSUPPORTED -> no entity
        assert st("binary_sensor", k) is None, k
    assert st("sensor", "battery_level") is None  # diesel: bogus currentSoCInPercent ignored
    assert st("sensor", "api_requests_remaining") is None  # no header -> no entity
    assert st("device_tracker", "parking_position").attributes["latitude"] == 50.0
