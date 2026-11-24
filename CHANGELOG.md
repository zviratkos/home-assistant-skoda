# Changelog

## 0.1.0
První verze. Read-only, bez externích závislostí (jen `aiohttp` z HA).

- Přihlášení API klíčem (`X-API-Key`), jeden config entry = jeden VIN.
- Jeden `GET /api/v1/vehicles/{vin}` na poll, výchozí interval 10 min (6 req/h z limitu 20/h), minimum 4 min.
- Reauth + reconfigure pro výměnu klíče (klíče expirují), options flow pro interval.
- Při HTTP 429 se drží poslední známá data a poll se odloží o `Retry-After` + 30 s.
- Entity se vytvářejí dynamicky, jakmile API vrátí příslušnou část (API vynechává nepodporované/nedostupné části).
- Senzory: baterie, dojezd (elektro / palivo / celkový / AdBlue), najeto, stav/typ/výkon/rychlost/zbývající čas nabíjení,
  cílové SoC, stav a cílová teplota klimatizace, "klimatizace připravena v", poslední data z vozu,
  diagnostika: zbývající API požadavky, platnost API klíče.
- Binární senzory: dveře, okna, světla, zámek, kufr, kapota, střešní okno, nabíjení, kabel, klimatizace.
- Device tracker: poloha zaparkování.
- Ochrana kilometrů z původní integrace (ignoruje přetečení 429496729 a pokles).
- Testy (`tests/`) běží proti reálnému jádru HA 2025.1.4 s mockovaným API.
