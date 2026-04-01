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
- **Optimering:** Python, deterministisk två-pass-algoritm (V13.0)
- **Kontroll:** Python, Degree Minutes-bank (GM-kontroller)
- **Databas:** SQLite (`data/nibe_autotuner.db`), WAL-mode
- **Backend API:** FastAPI + Uvicorn — port **8000**
- **Dashboard:** Flask (PWA) — port **5001**
- **Deploy:** rsync → Raspberry Pi 4 (100.100.118.62 via Tailscale)
- **Schemaläggning:** systemd services (`Restart=always`) + smart_planner triggas manuellt/cron

---

## Projektstruktur

```
/
├── src/
│   ├── core/
│   │   └── config.py           # Alla inställningar via Pydantic Settings (.env)
│   ├── data/
│   │   ├── database.py         # SQLAlchemy-engine, init_db(), get_session()
│   │   ├── models.py           # Alla ORM-modeller (utom DailyPerformance, AIEvaluation)
│   │   ├── performance_model.py # DailyPerformance-modell
│   │   ├── evaluation_model.py  # AIEvaluation-modell
│   │   └── data_logger.py      # Datainsamling (myUplink + HA + SMHI)
│   ├── services/
│   │   ├── optimizer.py        # V13.0 två-pass-optimizer
│   │   ├── smart_planner.py    # 24h-planering (kör optimeraren)
│   │   ├── gm_controller.py    # GM-bank, skriver till pump varje minut
│   │   ├── cop_model.py        # Nibe F730 COP-modell (bilinear interpolering)
│   │   ├── price_service.py    # Elpris från elprisetjustnu.se (gratis, ingen nyckel)
│   │   ├── weather_service.py  # SMHI-prognos
│   │   ├── analyzer.py         # Beräknar driftmätvärden (COP, drifttid etc.)
│   │   └── safety_guard.py     # Validerar GM-skrivningar innan de skickas
│   ├── integrations/
│   │   ├── auth.py             # myUplink OAuth2
│   │   └── api_client.py       # myUplink REST-klient
│   ├── api/
│   │   ├── api_server.py       # FastAPI-app
│   │   └── routers/            # status, dashboard_v5, parameters, metrics,
│   │                           # ai_agent, user_settings, ventilation, visualizations
│   └── mobile/
│       ├── mobile_app.py       # Flask-app (PWA-dashboard)
│       └── templates/          # base.html, dashboard*.html, performance.html,
│                               # settings.html, ...
├── nibe-autotuner.service      # systemd: data_logger (5 min)
├── nibe-gm-controller.service  # systemd: gm_controller (1 min), watchdog 120s
├── nibe-api.service            # systemd: FastAPI
├── nibe-mobile.service         # systemd: Flask PWA
├── deploy_v4.sh                # Commit + rsync + restart på RPi
├── requirements.txt
└── data/
    └── nibe_autotuner.db       # SQLite-databas (på RPi)
```

---

## Datatflöde

```
myUplink API  →  data_logger.py  →  parameter_readings
HA Sensors    →  data_logger.py  →  parameter_readings
SMHI          →  data_logger.py  →  parameter_readings

parameter_readings  →  smart_planner.py  →  planned_heating_schedule
elprisetjustnu.se   →  smart_planner.py  →  planned_heating_schedule
SMHI                →  smart_planner.py  →  planned_heating_schedule

planned_heating_schedule  →  gm_controller.py  →  myUplink Write API (GM 40940)
                              gm_controller.py  →  gm_transactions (audit)

data_logger.py  →  prediction_accuracy  (planned vs faktisk temp)
data_logger.py  →  hot_water_usage      (VV-cykler)
data_logger.py  →  daily_performance    (nattaggregering)
```

---

## Databastabeller

| Tabell | Syfte | Uppdateras av |
|--------|-------|---------------|
| `parameter_readings` | Tidsseriedata, 107 parametrar | data_logger (5 min) |
| `parameters` | Parametermetadata (102 Nibe + virtuella) | data_logger (init) |
| `planned_heating_schedule` | 24h-optimeringsplan (timgranularitet) | smart_planner (1/h) |
| `gm_account` | Aktuellt GM-bankssaldo (1 rad) | gm_controller (1 min) |
| `gm_transactions` | Audit-trail, 1 rad/minut, rensas efter 90 dagar | gm_controller (1 min) |
| `prediction_accuracy` | Planerad vs faktisk inomhustemp per timme | data_logger (5 min) |
| `daily_performance` | Aggregerade dagsvärden (COP, kostnad, komfort) | data_logger (midnatt) |
| `hot_water_usage` | Varmvattencykler (start, slut, varaktighet, temp) | data_logger (5 min) |
| `devices` | Enhetsinställningar (komfortintervall, bortaläge) | user_settings API |
| `learning_events` | Termisk inlärning (manuella experiment) | manuellt |
| `parameter_changes` | Logg över parameterförändringar | (ej aktiv ännu) |

**OBS:** `planned_heating_schedule` töms och skrivs om vid varje planeringscykel.

---

## Virtuella parametrar (ej från myUplink)

| parameter_id | Källa | Beskrivning |
|---|---|---|
| `VP_SYSTEM_MODE` | data_logger (beräknad) | 0=idle, 1=heating, 2=hw, 3=defrost |
| `HA_TEMP_DOWNSTAIRS` | Home Assistant | IKEA-sensor nedervåning (primär styrtemp) |
| `HA_TEMP_DEXTER` | Home Assistant | IKEA-sensor Dexters rum (min 20.0°C) |
| `HA_HUMIDITY_DOWNSTAIRS` | Home Assistant | Luftfuktighet nedervåning |
| `HA_HUMIDITY_DEXTER` | Home Assistant | Luftfuktighet Dexters rum |
| `EXT_WIND_SPEED` | SMHI | Vindstyrka (m/s) |
| `EXT_WIND_DIRECTION` | SMHI | Vindriktning (grader) |

---

## Nyckelparametrar (myUplink)

| Parameter ID | Namn | R/W | Syfte |
|---|---|---|---|
| 40004 | BT1 Utomhustemp | R | Värmekurvans ingångsvärde |
| 40008 | BT2 Tilloppstemperatur | R | Vatten till radiatorer |
| 40012 | BT3 Returtemperatur | R | Retur från radiatorer |
| 40013 | BT7 VV-topptemperatur | R | Detekterar VV-läge |
| 40033 | BT50 Rumstemperatur | R | Nibes inbyggda sensor (sämre än HA) |
| 40941 | Degree Minutes (läs) | R | Faktiskt GM-värde från pump |
| **40940** | **Degree Minutes (skriv)** | **W** | **Primär styrparameter** |
| 41778 | Kompressorfrekvens | R | >5 Hz = kompressor igång |
| 43066 | Defrost Active | R | 1 = avfrostning aktiv |
| 47007 | Värmekurva | W | Lutning (0–15), default 7.0 |
| 47011 | Kurva Offset | W | Offset (−10 till +10), styrs via plan |

---

## Optimizer V13.0 — konstanter

Alla konfigurerbara via `.env`:

| Konstant | Default | Beskrivning |
|---|---|---|
| `OPTIMIZER_K_LEAK` | 0.002 | Värmeförlust per °C delta per timme |
| `OPTIMIZER_K_GAIN` | 0.15 | Inomhustemperaturökning per offset-enhet per timme |
| `OPTIMIZER_MIN_TEMP` | 20.5 | Komfortgolv — Pass 1 höjer offset tills aldrig under |
| `OPTIMIZER_TARGET_TEMP` | 21.0 | Komfortmål — Pass 2 sänker offset tills här |
| `OPTIMIZER_MIN_OFFSET` | −3.0 | Lägsta tillåtna offset (aktivt lastnedskärning) |
| `OPTIMIZER_MAX_OFFSET` | 5.0 | Högsta tillåtna offset |
| `OPTIMIZER_REST_THRESHOLD` | −2.5 | Offset ≤ detta → action = REST |
| `OPTIMIZER_HOURLY_LOSS_FACTORS` | 1.0×…4.0×… | Per-timme K_LEAK-multiplikatorer (kl 15–18: 4×) |

**Kalibrering:** Övervaka `prediction_accuracy`. Positiv `bias` → sänk `K_GAIN`. Negativ `bias` → sänk `K_LEAK`.

---

## GM-kontroller — säkerhetslogik

Exekveras i ordning varje tick (1 min):

1. **Hämta API-data** (supply, outdoor, indoor, GM från pump)
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
11. **Logga** GMTransaction

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

---

## To-do

### Väntar på data (~2 veckor körning)

- **K_LEAK/K_GAIN auto-kalibrering** — kräver `prediction_accuracy`-historik.
  Kontroll: `SELECT AVG(error_c) as bias, AVG(ABS(error_c)) as mae FROM prediction_accuracy;`
  Positiv bias → sänk K_GAIN. Negativ → sänk K_LEAK.

- **VV pre-heat i optimeraren** — kräver `hot_water_usage`-mönster.
  Kontroll: `SELECT hour, weekday, AVG(duration_minutes), COUNT(*) FROM hot_water_usage GROUP BY hour, weekday ORDER BY COUNT(*) DESC;`

- **Dexter two-zone kalibrering** — verifiera att +1.5°C-heuristiken håller med faktisk data.

---

## Senaste ändringar

| Datum | Vad |
|-------|-----|
| 2026-04-01 | V13.0 optimizer: två-pass-algoritm, COPModel bilinear, negativa offset, linjär turboramp, defrost-detektion, timvis förlustkonstanter |
| 2026-04-01 | Datainsamling: gm_transactions, prediction_accuracy, daily_performance, hot_water_usage |
| 2026-04-01 | Bugfix: bank-frysning vid ≥22°C, BT50→HA_TEMP_DOWNSTAIRS, timezone i prisjämförelse, timedelta-import |
| 2026-04-01 | Funktioner: bortaläge (komplett), prediction accuracy-visualisering, systemd watchdog (sdnotify) |
| 2026-04-01 | Komfortintervall läses nu från devices-tabellen (ej hårdkodat 20.5/22.0) |
