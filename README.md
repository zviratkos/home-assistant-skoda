# Škoda (Public API) – minimální custom integrace pro Home Assistant

Read-only náhrada za `homeassistant-myskoda` nad **oficiálním MyŠkoda Public API**
(https://public.api.connect.skoda-auto.cz/docs). Žádné heslo, žádná externí knihovna.

## Instalace
1. Zkopíruj `custom_components/skoda_ha` do `<config>/custom_components/`, restartuj HA.
2. V aplikaci MyŠkoda vytvoř API klíč: https://go.skoda.eu/api-keys (vyber vozidlo).
3. Nastavení → Zařízení a služby → Přidat integraci → „Škoda (Public API)“ → API klíč + VIN.
   Více aut = přidej integraci znovu s dalším VIN (limit se počítá na VIN).

## Limity veřejného API
- 20 požadavků/hod na VIN (zatím „not final“). Jeden poll = 1 požadavek. Interval v Konfigurovat.
- Klíč expiruje, datum je v diagnostickém senzoru „Platnost API klíče do“. Při expiraci HA nabídne
  přihlášení znovu; předem to jde přes ⋮ → Překonfigurovat.
- Jen osobní použití (podmínky Škody).
- API nemá: zámek/odemknutí, houkání, wake-up, servisní intervaly, venkovní teplotu, verzi SW,
  statistiky jízd, MQTT push. Tyto senzory ze staré integrace tedy **nelze** portovat.

## Mapování ze staré integrace
| Stará entita | Nová |
|---|---|
| battery_percentage, range, electric_range | battery_level, total_range, electric_range |
| fuel_level, combustion_range, gas_level/range | fuel_level, fuel_range (jakýkoli neelektrický motor vč. CNG) |
| adblue_range, mileage | adblue_range, odometer |
| charging_state, charge_type, charging_power, charging_rate, remaining_charging_time, target_battery_percentage | totéž |
| car_captured | car_captured |
| climatisation time left | air_conditioning_ready_at (časová značka místo sekund) |
| doors/windows/lights/lock/trunk/bonnet, charging, plug | binary senzory totéž |
| device_tracker | parking_position |
| outside_temperature, software_version, inspection/oil, trip stats, camping, operation, service_event | nedostupné v public API |

Ovládání (start/stop nabíjení, limit, klimatizace) API umí (`POST .../charging/start|stop`,
`PUT .../charging/limit`, `POST .../air-conditioning/start|stop`), v 0.1.0 záměrně chybí.
