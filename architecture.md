# Arkitektur: Nibe Autotuner

---

## Hur detta dokument används

Detta är det **primära referensdokumentet** för all utveckling. Läs det innan du skriver kod.

**Claude** är arkitekt: designar lösningar, fattar tekniska beslut, sätter mönster och gränser.

### Regler vid implementation
1. **Läs alltid detta dokument först** — speciellt "Kända fallgropar" innan du rör GM-logik eller DB-migrationer.
2. **Rör aldrig säkerhetsgränserna** utan explicit godkännande: `MIN_BALANCE=-2000`, `MAX_BALANCE=200`, `BASTU_VAKT=23.5°C`, `CRITICAL_TEMP_LIMIT=19.0°C`.
3. **Testa aldrig GM-skrivningar automatiskt** — felaktigt GM-värde kan göra huset för kallt/varmt. Verifiera manuellt.
4. **Sätt alltid `PYTHONPATH=/home/peccz/AI/nibe_autotuner/src`** vid manuell körning.
5. **Commit före deploy.** `deploy_v4.sh` inkluderar git-commit och rsync till RPi.
6. **Uppdatera avsnitten "Senaste ändringar" och "To-do"** efter varje uppgift.
7. **Inga nya bibliotek utan diskussion** — RPi-paketet installeras via requirements.txt på produktionsenheten.
8. **Alla nya DB-tabeller auto-skapas** via `Base.metadata.create_all()` i `init_db()`. Lägg till nya models i importen i `database.py`.

---

## Teknikstack

- **Datainsamling:** Python 3.11+, SQLAlchemy, myUplink REST API
- **Väderdata:** Open-Meteo API (gratis, ingen nyckel) — ersatte SMHI pmp3g som ger 404 för dessa koordinater
- **Optimering:** Python, deterministisk två-pass-algoritm med tvåzonsmodell (V14.0)
- **Kontroll:** Python, Degree Minutes-bank (GM-kontroller)
- **Databas:** SQLite (`data/nibe_autotuner.db`), WAL-mode
- **Backend API:** FastAPI + Uvicorn — port **8000**
- **Dashboard:** Flask (PWA) — port **5001**
- **Deploy:** rsync → Raspberry Pi 4 (100.100.118.62 via Tailscale)
- **Schemaläggning:** systemd services (`Restart=always`) + smart_planner via systemd timer (varje timme)

---

## Hushysik — tre zoner, två modeller

Huset har tre termiska zoner med olika värmesystem:

| Zon | Våning | System | Styrtemp |
|-----|--------|--------|----------|
| **Floor** | Bottenplan | Golvvärme (shuntreglerad) | `HA_TEMP_DOWNSTAIRS` |
| **Radiator** | Mellanvåning (Dexters rum) | Radiatorer | `HA_TEMP_DEXTER` |
| *(ej mätt)* | Övervåning | Radiatorer | — |

Optimeraren behandlar Floor och Radiator som separata zoner. Övervåningen saknar sensor och antas bete sig likt mellanvåningen.

**Shuntfysik:** Shunten håller golvkretsens temperatur runt 40°C oavsett framledning. Under den gränsen är golvvärmen priori­terad och radiatorerna undermatade. Över 40°C börjar shunten strypa golvflödet — överskottsvärmen driver radiatorerna. Effekten:
- Framledning 30–40°C: gapet Dexter−Nedervåning är ca −1.3 till −1.5°C (golvvärme dominerar)
- Framledning >45°C: gapet minskar till ca −1.1°C (radiatorer börjar ta del av överskottet)

**Empirisk grund:** Parameter_readings 2026-01 till 2026-04 (outdoor < 15°C, n=1 664 timmätningar).

---

## Projektstruktur

```
/
├── src/
│   ├── core/
│   │   └── config.py           # Alla inställningar via Pydantic Settings (.env)
│   ├── data/
│   │   ├── database.py         # SQLAlchemy-engine, init_db(), get_session()
│   │   ├── models.py           # ORM-modeller: Device, Parameter, ParameterReading,
│   │   │                       #   GMAccount, GMTransaction, PlannedHeatingSchedule,
│   │   │                       #   HotWaterUsage, PredictionAccuracy, m.fl.
│   │   ├── performance_model.py # DailyPerformance-modell
│   │   ├── evaluation_model.py  # AIEvaluation-modell
│   │   └── data_logger.py      # Datainsamling (myUplink + HA + Open-Meteo/SMHI)
│   ├── services/
│   │   ├── optimizer.py        # V14.0 tvåzons-optimizer (floor + radiator)
│   │   ├── smart_planner.py    # 24h-planering — kör optimeraren, sparar plan
│   │   ├── gm_controller.py    # GM-bank, skriver till pump varje minut
│   │   ├── cop_model.py        # Nibe F730 COP-modell (bilinear interpolering)
│   │   ├── price_service.py    # Elpris från elprisetjustnu.se (gratis, ingen nyckel)
│   │   ├── weather_service.py  # Open-Meteo väderprognoser (klass heter SMHIWeatherService)
│   │   ├── analyzer.py         # Beräknar driftmätvärden (COP, drifttid etc.)
│   │   └── safety_guard.py     # Validerar GM-skrivningar innan de skickas
│   ├── integrations/
│   │   ├── auth.py             # myUplink OAuth2 (token sparas i ~/.myuplink_tokens.json)
│   │   └── api_client.py       # myUplink REST-klient
│   ├── api/
│   │   ├── api_server.py       # FastAPI-app (port 8000), CORS allow_origins=["*"]
│   │   └── routers/            # dashboard_v5, parameters, metrics,
│   │                           # ai_agent, user_settings, ventilation, visualizations
│   └── mobile/
│       ├── mobile_app.py       # Flask-app (PWA-dashboard, port 5001)
│       └── templates/          # dashboard_v7.html, performance.html, settings.html, ...
├── nibe-autotuner.service      # systemd: data_logger (5 min, Restart=always)
├── nibe-gm-controller.service  # systemd: gm_controller (1 min), watchdog 120s
├── nibe-api.service            # systemd: FastAPI (port 8000)
├── nibe-mobile.service         # systemd: Flask PWA (port 5001)
├── nibe-smart-planner.service  # systemd: smart_planner (oneshot, körs av timer)
├── nibe-smart-planner.timer    # systemd: triggar smart_planner varje timme
├── deploy_v4.sh                # Commit + rsync + restart på RPi (se nedan)
├── requirements.txt
└── data/
    └── nibe_autotuner.db       # SQLite-databas (på RPi, ej i git)
```

---

## Deploy-flöde (`deploy_v4.sh`)

1. `git add . && git commit` (valfritt meddelande, default: "Deploy: Auto-update DATUM")
2. `git push origin main`
3. `rsync` till RPi `100.100.118.62:/home/peccz/nibe_autotuner/` (exkluderar `venv/`, `__pycache__/`, `data/nibe_autotuner.db`, `.git/`)
4. SSH: `pip install -r requirements.txt --quiet`
5. SSH: `sudo systemctl restart nibe-autotuner nibe-api nibe-gm-controller`
6. SSH: `sudo systemctl enable --now nibe-smart-planner.timer && sudo systemctl start nibe-smart-planner.service`

**OBS:** `nibe-mobile` startas **inte** om av deploy_v4.sh. Starta manuellt: `sudo systemctl restart nibe-mobile`.
**OBS:** Service-filerna i repot refererar `/home/peccz/AI/nibe_autotuner` (dev-sökväg). `deploy_v4.sh` kör `sed` för att byta till `/home/peccz/nibe_autotuner` vid installation av `nibe-smart-planner.*` på RPi. Övriga service-filer är manuellt skapade på RPi med rätt sökvägar.

---

## Datatflöde

```
myUplink API   →  data_logger.py  →  parameter_readings
HA Sensors     →  data_logger.py  →  parameter_readings
Open-Meteo     →  data_logger.py  →  parameter_readings  (EXT_WIND_SPEED etc.)

parameter_readings  →  smart_planner.py  →  planned_heating_schedule
elprisetjustnu.se   →  smart_planner.py  →  planned_heating_schedule
Open-Meteo          →  smart_planner.py  →  planned_heating_schedule
  (fallback: senaste 40004-värde från DB om Open-Meteo ej svarar)

planned_heating_schedule  →  gm_controller.py  →  myUplink Write API (GM 40940)
                              gm_controller.py  →  gm_transactions (audit)

data_logger.py  →  prediction_accuracy  (planned vs faktisk temp, per timme)
data_logger.py  →  hot_water_usage      (VV-cykler, VP_SYSTEM_MODE=2.0)
data_logger.py  →  daily_performance    (nattaggregering: COP, kWh, komfort)
```

---

## Databastabeller

| Tabell | Syfte | Uppdateras av |
|--------|-------|---------------|
| `parameter_readings` | Tidsseriedata, ~107 parametrar | data_logger (5 min) |
| `parameters` | Parametermetadata (102 Nibe + virtuella) | data_logger (init) |
| `planned_heating_schedule` | 24h-optimeringsplan (timgranularitet), inkl. simulated_dexter_temp | smart_planner (1/h) |
| `gm_account` | Aktuellt GM-bankssaldo (1 rad), `last_updated` uppdateras ej automatiskt | gm_controller (1 min) |
| `gm_transactions` | Audit-trail, 1 rad/minut, rensas efter 90 dagar | gm_controller (1 min) |
| `prediction_accuracy` | Planerad vs faktisk inomhustemp per timme | data_logger (5 min) |
| `daily_performance` | Aggregerade dagsvärden (COP, kostnad, komfort) | data_logger (midnatt) |
| `hot_water_usage` | Varmvattencykler (start, slut, varaktighet, temp) | data_logger (5 min) |
| `devices` | Enhetsinställningar (komfortintervall, bortaläge) | user_settings API |
| `learning_events` | Termisk inlärning (manuella experiment) | manuellt |
| `parameter_changes` | Logg över parameterförändringar | (ej aktiv ännu) |

**OBS:** `planned_heating_schedule` töms och skrivs om vid varje planeringscykel.
**OBS:** `gm_account.last_updated` sätts vid skapande men uppdateras inte av gm_controller — använd `gm_transactions` för att se senaste aktivitet.

---

## Virtuella parametrar (ej från myUplink)

| parameter_id | Källa | Beskrivning |
|---|---|---|
| `VP_SYSTEM_MODE` | data_logger (beräknad) | 0=idle, 1=heating, 2=hw, 3=defrost |
| `HA_TEMP_DOWNSTAIRS` | Home Assistant | IKEA-sensor bottenplan (primär styrtemp, Floor-zon) |
| `HA_TEMP_DEXTER` | Home Assistant | IKEA-sensor Dexters rum mellanvåning (Radiator-zon, min 20.0°C) |
| `HA_HUMIDITY_DOWNSTAIRS` | Home Assistant | Luftfuktighet bottenplan |
| `HA_HUMIDITY_DEXTER` | Home Assistant | Luftfuktighet Dexters rum |
| `EXT_WIND_SPEED` | Open-Meteo | Vindstyrka (m/s) |
| `EXT_WIND_DIRECTION` | Open-Meteo | Vindriktning (grader) |

---

## Nyckelparametrar (myUplink)

| Parameter ID | Namn | R/W | Syfte |
|---|---|---|---|
| 40004 | BT1 Utomhustemp | R | Värmekurvans ingångsvärde; DB-fallback för optimizer |
| 40008 | BT2 Tilloppstemperatur | R | Vatten till radiatorer |
| 40012 | BT3 Returtemperatur | R | Retur från radiatorer |
| 40013 | BT7 VV-topptemperatur | R | Detekterar VV-läge |
| 40033 | BT50 Rumstemperatur | R | Nibes inbyggda sensor (används ej — HA-sensor föredras) |
| 40941 | Degree Minutes (läs) | R | Faktiskt GM-värde från pump |
| **40940** | **Degree Minutes (skriv)** | **W** | **Primär styrparameter** |
| 41778 | Kompressorfrekvens | R | >5 Hz = kompressor igång |
| 43066 | Defrost Active | R | 1 = avfrostning aktiv |
| 47007 | Värmekurva | W | Lutning (0–15), default 7.0 |
| 47011 | Kurva Offset | W | Fast offset i Nibe (−10 till +10); GM-kontroller skriver ej hit |

---

## API-endpoints (FastAPI, port 8000)

| Endpoint | Metod | Router | Beskrivning |
|----------|-------|--------|-------------|
| `/` | GET | api_server | Versioninfo |
| `/docs` | GET | FastAPI | Swagger UI |
| `/dashboard` | GET | api_server | Servar dashboard HTML (FileResponse) |
| `/api/status` | GET | dashboard_v5 | Aktuell systemstatus (temp, GM, plan) |
| `/api/plan` | GET | dashboard_v5 | Aktuell 24h-plan |
| `/api/metrics` | GET | metrics | Nyckeltal (COP, drifttid etc.) |
| `/api/parameters` | GET | parameters | Lista alla parametrar |
| `/api/parameters/{id}/history` | GET | parameters | Tidsseriedata för parameter |
| `/api/settings` | GET | user_settings | Hämta enhetsinställningar |
| `/api/settings` | POST | user_settings | Uppdatera inställningar |
| `/api/settings/away-mode` | POST | user_settings | Sätt/avaktivera bortaläge |
| `/api/ai-agent/run` | POST | ai_agent | Kör AI-agent manuellt |
| `/api/ai-agent/decisions` | GET | ai_agent | Beslutlogg |
| `/api/ventilation` | GET/POST | ventilation | Ventilationsstyrning |
| `/api/visualizations/prediction-accuracy` | GET | visualizations | Prediktionsnoggrannhet som bild |

**Flask-dashboard (port 5001):** `/`, `/dashboard`, `/performance`, `/api/v7/dashboard`, `/api/performance`, `/api/changes`

---

## Hjälptjänster

| Tjänst | Fil | Beskrivning |
|--------|-----|-------------|
| `HeatPumpAnalyzer` | `services/analyzer.py` | Beräknar COP, drifttid, systemläge; `get_latest_value()` för parameter-queries |
| `SafetyGuard` | `services/safety_guard.py` | Validerar GM-värden innan skrivning; kontrollerar gränser och tillstånd |
| `COPModel` | `services/cop_model.py` | Bilinear interpolering av Nibe F730 COP (utetemperatur × tilloppstemperatur) |
| `PriceService` | `services/price_service.py` | Hämtar spotpriser från elprisetjustnu.se (gratis, ingen nyckel) |
| `SMHIWeatherService` | `services/weather_service.py` | Open-Meteo-prognos (klassnamn behållet för bakåtkompatibilitet) |

---

## Optimizer V14.0 — konstanter

Alla konfigurerbara via `.env`:

### Ettzonskonstanter (globala)

| Konstant | Default | Beskrivning |
|---|---|---|
| `OPTIMIZER_K_LEAK` | 0.002 | Värmeförlust (Floor-zon) per °C delta per timme |
| `OPTIMIZER_MIN_TEMP` | 20.5 | Komfortgolv Floor — Pass 1 höjer offset tills aldrig under |
| `OPTIMIZER_TARGET_TEMP` | 21.0 | Komfortmål Floor — Pass 2 sänker offset tills här |
| `OPTIMIZER_MIN_OFFSET` | −3.0 | Lägsta tillåtna offset (aktivt lastnedskärning) |
| `OPTIMIZER_MAX_OFFSET` | 5.0 | Högsta tillåtna offset |
| `OPTIMIZER_REST_THRESHOLD` | −2.5 | Offset ≤ detta → action = REST |
| `OPTIMIZER_HOURLY_LOSS_FACTORS` | 1.0×…4.0×… | Per-timme K_LEAK-multiplikatorer (kl 15–18: 4×) |

### Tvåzonskonstanter (V14.0)

| Konstant | Default | Beskrivning |
|---|---|---|
| `K_GAIN_FLOOR` | 0.10 | Temp-ökning bottenplan per offset-enhet per timme (golvvärme, dämpad av shunt) |
| `K_GAIN_RADIATOR` | 0.15 | Temp-ökning radiatorzon per offset-enhet per timme (baslinje) |
| `K_LEAK_RADIATOR` | 0.003 | Värmeförlust radiatorzon per °C delta per timme |
| `SHUNT_SETPOINT` | 40.0 | Framledning (°C) där shunten börjar begränsa golvflödet → överskott till radiatorer |
| `RAD_BOOST_FACTOR` | 0.012 | Extra radiatorzon-gain (°C/h) per °C framledning över SHUNT_SETPOINT |
| `DEXTER_MIN_TEMP` | 20.0 | Komfortgolv Radiatorzon (Dexters rum) |
| `DEFAULT_HEATING_CURVE` | 7.0 | Nibes värmekurva — används för att approximera framledning av given offset |

**Kalibrering:** Övervaka `prediction_accuracy` per zon.
- Positiv bias Floor → sänk `K_GAIN_FLOOR`
- Positiv bias Radiator → sänk `K_GAIN_RADIATOR` eller `RAD_BOOST_FACTOR`
- Negativ bias → sänk respektive `K_LEAK`

---

## GM-kontroller — säkerhetslogik

Exekveras i ordning varje tick (1 min):

1. **Hämta API-data** (supply, outdoor, indoor BT50, GM från pump)
2. **Läs systemläge** från DB (`VP_SYSTEM_MODE`)
3. **Beräkna target_supply** = `20 + (20 − outdoor) × curve × 0.12 + offset`
4. **Beräkna delta_gm** = `diff_temp × dt_min × multiplier`
   - Turboramp: 1.0× vid deficit 2°C → 3.0× vid deficit 8°C (linjär)
   - Paus vid HW (mode 2.0) och defrost (mode 3.0)
5. **Uppdatera saldo** (alltid, ingen frysning)
6. **Klampning**: `balance = max(−2000, min(200, balance))`
7. **Bastu-vakt**: om indoor > 23.5°C → balance = 100, action = MUST_REST
8. **Bestäm GM att skriva**: saldo / 10 avrundat, skyddsgränser
9. **Validera** via SafetyGuard innan skrivning
10. **Skriv till pump** om avvikelse >50 GM eller mål ändrat >10 GM
11. **Logga** GMTransaction (inkl. supply_target, supply_actual, safety_override)

**Notering vår/sommar:** När utomhustemperaturen är hög (>20°C) sjunker target_supply under faktisk supply → delta_gm positivt → balance träffar +200-taket. GM-kontrollern skriver GM=200 (undertrycker Nibes interna start) men pumpen kan ändå köra för VV-produktion.

---

## Kända fallgropar

### 1. PYTHONPATH (KRITISK)
Alla script måste köras med `PYTHONPATH=/home/peccz/AI/nibe_autotuner/src`. Utan detta misslyckas alla interna importer. systemd-tjänsterna har detta satt.

### 2. Timezone i smart_planner
elprisetjustnu.se returnerar priser i CET/CEST. Jämförs alltid via `.astimezone(timezone.utc)` mot `datetime.now(timezone.utc)`. Glöms detta bort → alla priser faller tillbaka på 1.0 SEK/kWh.

### 3. GM-skrivningar är irreversibla under körning
Ett felaktigt GM-värde håller pumpen i fel läge tills nästa tick (1 min). Vid negativa värden runt −400 startar elvärmen. Testa aldrig automatiserat mot produktionspumpen.

### 4. planned_heating_schedule töms vid varje körning
smart_planner använder `DELETE FROM planned_heating_schedule` + `BEGIN EXCLUSIVE` för att undvika race condition med gm_controller. Kraschar smart_planner mitt i → tabellen tom → gm_controller faller tillbaka på offset=0.

### 5. VP_SYSTEM_MODE måste finnas i parameters-tabellen
`investigate_system_mode()` skriver bara om parametern finns. Vid fresh install kan den saknas. Kontrollera: `SELECT * FROM parameters WHERE parameter_id = 'VP_SYSTEM_MODE'`.

### 6. HW-detektionslogik (VP_SYSTEM_MODE=2.0)
Villkor: `comp_freq > 5 AND supply > hw_top + 1.0 AND supply > 42.0`. Defrost (43066 > 0) har prioritet. Om parametern 43066 inte är registrerad → defrost detekteras aldrig.

### 7. HA-sensorer via Matter/Thread
IKEA-sensorerna kopplar via Google Nest WiFi Pro (Thread Border Router) → Home Assistant (Docker, `ws://127.0.0.1:5580/ws`). Om HA IP-adress ändras → Matter-integrationen kraschar. Config finns i HA:s storage, inte i vår kod.

### 8. myUplink rate limit
Free tier: 15 anrop/min. data_logger: ~1 anrop/5 min. gm_controller: ~2 anrop/min (läs + eventuell skrivning). Totalt ~3 anrop/min normalt — säkert.

### 9. SMHIWeatherService använder Open-Meteo, inte SMHI
Klassnamnet är kvar för bakåtkompatibilitet. SMHI pmp3g-endpointen ger 404 för Upplands Väsby-koordinaterna. Byt inte tillbaka utan att verifiera att SMHI-URL:en svarar.

### 10. Tvåzonsmodellen kräver att HA_TEMP_DEXTER finns i DB
Om Dexter-sensorn tappar kontakt och `HA_TEMP_DEXTER` saknas i senaste timmes readings faller smart_planner tillbaka på `start_floor - 1.0` som start_radiator. Optimeraren kör då i praktiken som ettzon.

---

## To-do

### Kvar att göra

- **Solvinst-heuristik** — Dexters rum överhettas av sol på varma dagar (observerat +1.5°C relativt nedervåning vid outdoor > 20°C). En faktor baserad på tid+utomhustemperatur kan förebygga detta i planeringen.

- **Övervåningsensor** — saknas helt. Utan den är radiatorzonens modell begränsad till Dexters rum. En tredje sensor (IKEA) skulle förbättra tvåzonsmodellen avsevärt.

- **K_LEAK_RADIATOR / K_GAIN_RADIATOR kalibrering** — kräver prediction_accuracy per zon. `simulated_dexter_temp` finns i planned_heating_schedule men valideras inte än mot HA_TEMP_DEXTER i data_logger.

---

## Senaste ändringar

| Datum | Vad |
|-------|-----|
| 2026-04-01 | V13.0 optimizer: två-pass-algoritm, COPModel bilinear, negativa offset, linjär turboramp, defrost-detektion, timvis förlustkonstanter |
| 2026-04-01 | Datainsamling: gm_transactions, prediction_accuracy, daily_performance, hot_water_usage |
| 2026-04-01 | Bugfix: bank-frysning vid ≥22°C, BT50→HA_TEMP_DOWNSTAIRS, timezone i prisjämförelse, timedelta-import |
| 2026-04-01 | Funktioner: bortaläge (komplett), prediction accuracy-visualisering, systemd watchdog (sdnotify) |
| 2026-04-01 | Komfortintervall läses nu från devices-tabellen (ej hårdkodat 20.5/22.0) |
| 2026-04-01 | Smart planner automatiserad: nibe-smart-planner.service + .timer (varje timme) |
| 2026-04-01 | V14.0: Tvåzonsmodell (golvvärme + radiatorer), Open-Meteo ersätter SMHI (404), DB-fallback för utomhustemp |
| 2026-04-01 | Dexter-skydd symmetriskt: varmt (>22°C) och kallt (<20°C) justerar starttemp åt rätt håll |
| 2026-04-02 | Bugfix: SafetyGuard INDOOR_TEMP_PARAM_ID='13' (hårdkodat DB-rad-ID, nu korrekt uppslag via '40033') |
| 2026-04-02 | Bugfix: away_mode datetime-jämförelse (timezone-naiv vs UTC) |
| 2026-04-02 | Bugfix: planned_heating_schedule töms ej retroaktivt — prediction_accuracy kan nu fyllas |
| 2026-04-02 | Tvåzons-temperaturmål: target_radiator_temp i devices, optimizer, API och settings-UI |
| 2026-04-02 | Autonom kalibrering: _calibrate_thermal_model() i data_logger — nattligt K_LEAK/K_GAIN-jobb med EMA, lagras i calibration_history, läses av smart_planner |
| 2026-04-02 | VV pre-heat: smart_planner blockerar REST för timmar med historiska VV-mönster (>= 2 obs) + föregående timme |
| 2026-04-02 | Dexter-skydd i regulatorn: gm_controller overridar REST→RUN om HA_TEMP_DEXTER < 19°C |
