# Changelog

## 0.1.4
- Ověřeno na skutečné odpovědi API (Octavia diesel): palivo, dojezd, AdBlue, najeto, dveře, zámek, kapota,
  kufr, světla i poloha se mapují správně. Pole `windows: UNKNOWN` a `sunroof: UNSUPPORTED` entitu nevytvoří.
- Nový senzor „Aktivní větrání“ (`activeVentilation.state`), který API vrací.
- `currentSoCInPercent` u dieselového motoru (API ho vrací shodné s palivem) se správně ignoruje, baterie se nevytvoří.
- Test s anonymizovanou kopií reálné odpovědi.

## 0.1.3
- **Oprava:** API často odpovídá `503 Vehicle data is temporarily unavailable. Retry after 10 seconds`.
  Dřív to skončilo jako „Cannot connect“. Teď se 502/503/504 zopakuje (max. 2x, čeká se `Retry-After`,
  nejvýše 30 s; 5xx se počítá do limitu 20/h, proto tak málo).
- Config flow: pokud i po opakování zůstane 503, záznam se přesto vytvoří (klíč a VIN API přijalo,
  jinak by vrátilo 401/403/404) a HA to načítá znovu automaticky.
- Za běhu při 503 zůstanou poslední známé hodnoty místo „nedostupné“.

## 0.1.2
- Config flow už u „Cannot connect“ / „Unknown error“ zobrazí konkrétní důvod (HTTP stav, přesměrování,
  timeout, chyba TLS) a zapíše ho do logu jako warning. Dřív se příčina ztrácela.
- Neplatná JSON odpověď už nevyvolá nezachycenou výjimku.

## 0.1.1
- **Breaking:** doména a složka přejmenovány `skoda_public_api` -> `skoda_ha`
  (`custom_components/skoda_ha`). Pro HA je to nová integrace: původní záznam odeber,
  smaž starou složku, restartuj a přidej znovu (API klíč + VIN). Entity ID se nemění
  (odvozují se z názvu auta). Žádná funkční změna.

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
