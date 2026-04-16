# Project DNA - Nibe Autotuner
*Source of Truth för Nibe F730-värmepumpsoptimeringen. Alla AI-agenter MÅSTE läsa detta dokument innan de agerar.*

---

## 0. AI AGENT PROTOCOL (LÄS FÖRST — OBLIGATORISKT)

### Obligatoriskt före varje uppgift
- Läs detta dokument med Read-verktyget i varje ny session
- Kvittera med **"DNA.md läst"** direkt i svaret innan arbetet påbörjas
- Verifiera att planerad åtgärd stämmer med arkitekturen nedan

### Obligatoriskt efter varje uppgift
- Uppdatera sektion **11. Active Work & State** med vad som förändrats
- Om ett systemnivåbeslut fattades, dokumentera det i sektion **12. Decision Log**
- Uppdatera "Senaste ändringar"-tabellen i sektion 11
- Kvittera med **"DNA.md uppdaterad"** i svaret

### Hårda begränsningar (BRYT ALDRIG dessa)
- **RÖR ALDRIG** säkerhetsgränserna utan explicit godkännande: `MIN_BALANCE=-2000`, `MAX_BALANCE=200`, `BASTU_VAKT=23.5°C`, `CRITICAL_TEMP_LIMIT=19.0°C`
- **TESTA ALDRIG** GM-skrivningar automatiskt — felaktigt GM-värde kan göra huset för kallt/varmt
- **SÄTT ALLTID** `PYTHONPATH=/home/peccz/AI/nibe_autotuner/src` vid manuell körning
- **COMMIT FÖRE DEPLOY** — `deploy_v4.sh` inkluderar git-commit och rsync till RPi
- **INGA NYA BIBLIOTEK** utan diskussion — RPi-paketet installeras via `requirements.txt`
- **ALLA NYA DB-TABELLER** skapas via `Base.metadata.create_all()` i `init_db()` — lägg till modeller i importen i `database.py`
- **SKAPA INTE** `_v2`, `_final`, `_fixed`-varianter av filer — redigera den kanoniska filen

### Claude-specifika noter
- Läs alltid med Read-verktyget — force fresh read vid misstanke om cache
- Bekräfta alltid innan: push till remote, radering av filer, modifiering av systemd-units
- Undvik överkonstruktion — håll lösningar minimala och direkta

### AI Project Review Protocol
Before final response, merge, deploy, or handoff, perform this review:
- **Scope check:** The change solves the requested task and nothing materially outside it
- **Canonical check:** Only canonical files from section 3 were changed, unless an exception is documented
- **Architecture check:** No duplicate patterns, `_v2` files, or bypassed layers were introduced
- **Safety/data check:** No secrets, live data, DB schema, service units, safety limits, GM writes, or production paths were changed without explicit approval
- **Verification check:** Tests, lint, build, or manual validation were run; if not, document verification debt in section 11
- **State check:** Section 11 reflects what changed, what was verified, and what remains open
- **Decision check:** Any durable system decision is recorded in section 12

Production-sensitive changes require explicit user approval, a rollback path, and exact verification steps. Do not restart services, deploy, migrate databases, write GM values, or alter live configuration unless the task explicitly requires it.

### AI Review Trigger & Scope
Initiate review at the earliest matching level:

#### Level 0 - No Formal Review
Use only for pure reading, answering questions, or planning with no file changes. No DNA update is required unless a durable decision or new project fact is discovered.

#### Level 1 - Light Review
Use for docs-only changes, comments, formatting, typo fixes, or non-runtime governance updates. Required: scope check, canonical check, and state check if project state changed.

#### Level 2 - Standard Review
Use for normal code changes, tests, scripts, non-live config, or project-local tooling. Required: full AI Project Review Protocol, relevant test/lint/build when available, and documented verification debt if not verified.

#### Level 3 - Deep Review
Use for architecture changes, data model changes, cross-project changes, generated code, refactors, dependency changes, auth/API behavior, optimizer logic, control-loop behavior, or anything touching persistent data. Required: full protocol, explicit architecture check against DNA.md, before/after behavior explanation, verification, and Decision Log entry if design changed.

#### Level 4 - Production/Safety Review
Use for service units, deploy scripts, DB migrations, live config, secrets, safety limits, GM writes, heat-pump control behavior, automation controlling real devices, or destructive file operations. Required: explicit user approval before action, rollback path, exact verification steps, no service restart/deploy/migration/deletion/live write/GM write unless explicitly requested, and updates to Active Work & State plus Decision Log.

Review must be initiated when AI writes or edits files, a diff crosses project boundaries, a canonical file map entry changes, a new file is created, DB/schema/data migration is proposed, service/deploy/secret/env/production path is touched, tests cannot be run, architecture drift is noticed, DNA is stale, or the outcome affects money, safety, live automation, heat-pump behavior, or user decisions.

### AI Feedback Loop
When working in this project, actively surface reusable improvements instead of keeping them local. If you discover a smarter workflow, safer constraint, better review rule, recurring failure mode, useful script, architecture pattern, or project-specific lesson:
- Record it in this project DNA under Active Work, Known Pitfalls, Decision Log, or the relevant canonical section
- If it could benefit other projects, also update `/home/peccz/AI/MASTER_DNA.md` or explicitly report it in the final response as a cross-project recommendation
- Do not apply cross-project changes automatically unless the task asks for it; propose or document the transfer first
- Prefer concrete, reusable rules over vague advice


---

## 1. Systemöversikt & Teknikstack

**Version:** V14.0 (Tvåzons Proaktiv Optimering)

| Komponent | Teknik |
|-----------|--------|
| Datainsamling | Python 3.11+, SQLAlchemy, myUplink REST API |
| Väderdata | Open-Meteo API (gratis, ingen nyckel) |
| Optimering | Python, deterministisk två-pass-algoritm med tvåzonsmodell |
| Kontroll | Python, Degree Minutes-bank (GM-kontroller) |
| Databas | SQLite (`data/nibe_autotuner.db`), WAL-mode |
| Backend API | FastAPI + Uvicorn — port **8000** |
| Dashboard | Flask (PWA) — port **5001** |
| Deploy | rsync → Raspberry Pi 4 (`100.100.118.62` via Tailscale) |
| Schemaläggning | systemd services (`Restart=always`) + smart_planner via systemd timer (varje timme) |

### Tre kritiska tjänster

| Tjänst | Intervall | Syfte |
|--------|-----------|-------|
| `data_logger.py` | 5 min | Hämtar 102+ parametrar från Nibe + HA + Open-Meteo, beräknar virtuella parametrar |
| `smart_planner.py` | 1 h (timer) | 24h-optimeringsplan — elpris + väderprognos → offset-schema |
| `gm_controller.py` | 1 min | GM-bank — skriver GM-setpoint (40940) till pump, säkerhetslogik |

---

## 2. Husphysik — tre zoner, två modeller

| Zon | Våning | System | Styrtemp |
|-----|--------|--------|----------|
| **Floor** | Bottenplan | Golvvärme (shuntreglerad) | `HA_TEMP_DOWNSTAIRS` |
| **Radiator** | Mellanvåning (Dexters rum) | Radiatorer | `HA_TEMP_DEXTER` |
| *(ej mätt)* | Övervåning | Radiatorer | — |

**Shuntfysik:** Shunten håller golvkretsens temperatur runt 40°C oavsett framledning.
- Framledning 30–40°C: gapet Dexter−Nedervåning ≈ −1.3 till −1.5°C (golvvärme dominerar)
- Framledning >45°C: gapet minskar till ≈ −1.1°C (radiatorer börjar ta del av överskottet)

**Empirisk grund:** parameter_readings 2026-01 till 2026-04 (outdoor < 15°C, n=1 664 timmätningar).

**Zonprioritering:** Styrs via `target_radiator_temp` i `devices`-tabellen. Om `target_radiator_temp` > `target_indoor_temp_max` väljer optimeraren naturligt högre offset → supply > SHUNT_SETPOINT → radiatorer prioriteras.

---

## 3. Kanoniska filer

*Redigera dessa — inte varianter eller kopior.*

| Komponent | Fil | Syfte |
|-----------|-----|-------|
| Konfiguration | `src/core/config.py` | Alla inställningar via Pydantic Settings (.env) |
| Databas | `src/data/database.py` | SQLAlchemy-engine, `init_db()`, `get_session()` |
| Modeller | `src/data/models.py` | Alla ORM-modeller |
| Datainsamling | `src/data/data_logger.py` | myUplink + HA + Open-Meteo + kalibrering |
| Optimizer | `src/services/optimizer.py` | V14.0 tvåzons-optimizer |
| Planerare | `src/services/smart_planner.py` | 24h-planering, sparar till planned_heating_schedule |
| GM-kontroller | `src/services/gm_controller.py` | GM-bank, skriver till pump varje minut |
| Säkerhet | `src/services/safety_guard.py` | Validerar GM-skrivningar |
| Priser | `src/services/price_service.py` | elprisetjustnu.se (gratis, ingen nyckel) |
| Väder | `src/services/weather_service.py` | Open-Meteo (klassen heter `SMHIWeatherService` — bakåtkompatibilitet) |
| FastAPI | `src/api/api_server.py` | Port 8000, CORS allow_origins=["*"] |
| Flask PWA | `src/mobile/mobile_app.py` | Port 5001, primärt användargränssnitt |
| Deploy | `deploy_v4.sh` | Commit + rsync + restart på RPi |
| systemd | `nibe-autotuner.service` | data_logger (5 min) |
| systemd | `nibe-gm-controller.service` | gm_controller (1 min), watchdog 120s |
| systemd | `nibe-smart-planner.timer` | Triggar smart_planner varje timme |

```
/
├── src/
│   ├── core/config.py
│   ├── data/
│   │   ├── database.py, models.py, data_logger.py
│   │   └── performance_model.py, evaluation_model.py
│   ├── services/
│   │   ├── optimizer.py, smart_planner.py, gm_controller.py
│   │   ├── cop_model.py, price_service.py, weather_service.py
│   │   ├── analyzer.py, safety_guard.py
│   ├── integrations/
│   │   ├── auth.py        # myUplink OAuth2 (token → ~/.myuplink_tokens.json)
│   │   └── api_client.py  # myUplink REST-klient
│   ├── api/
│   │   ├── api_server.py
│   │   └── routers/       # dashboard_v5, parameters, metrics, ai_agent,
│   │                      # user_settings, ventilation, visualizations
│   └── mobile/
│       ├── mobile_app.py
│       └── templates/     # dashboard_v7.html, performance.html, settings.html
├── nibe-autotuner.service
├── nibe-gm-controller.service
├── nibe-api.service
├── nibe-mobile.service
├── nibe-smart-planner.service + .timer
├── deploy_v4.sh
├── requirements.txt
└── data/nibe_autotuner.db   # På RPi, ej i git
```

---

## 4. Deploy-flöde (`deploy_v4.sh`)

1. `git add . && git commit` (valfritt meddelande, default: "Deploy: Auto-update DATUM")
2. `git push origin main`
3. `rsync` till RPi `100.100.118.62:/home/peccz/nibe_autotuner/` (exkluderar `venv/`, `__pycache__/`, `data/nibe_autotuner.db`, `.git/`)
4. SSH: `pip install -r requirements.txt --quiet`
5. SSH: `PYTHONPATH=src python src/data/migrate_zone_priority.py` (+ ev. andra migrationer)
6. SSH: `sudo systemctl restart nibe-autotuner nibe-api nibe-gm-controller`
7. SSH: `sudo systemctl enable --now nibe-smart-planner.timer && sudo systemctl start nibe-smart-planner.service`

**OBS:** `nibe-mobile` startas **inte** om av deploy_v4.sh — starta manuellt vid behov.
**OBS:** Service-filer i repot har dev-sökväg `/home/peccz/AI/nibe_autotuner`. `deploy_v4.sh` kör `sed` för att byta till `/home/peccz/nibe_autotuner` vid installation av `nibe-smart-planner.*` på RPi.

---

## 5. Dataflöde

```
myUplink API   →  data_logger.py  →  parameter_readings
HA Sensors     →  data_logger.py  →  parameter_readings
Open-Meteo     →  data_logger.py  →  parameter_readings  (EXT_WIND_SPEED etc.)

parameter_readings  →  smart_planner.py  →  planned_heating_schedule
elprisetjustnu.se   →  smart_planner.py  →  planned_heating_schedule
Open-Meteo          →  smart_planner.py  →  planned_heating_schedule
  (fallback: senaste 40004-värde från DB om Open-Meteo ej svarar)
calibration_history →  smart_planner.py  →  optimizer (k_leak, k_gain_floor override)
hot_water_usage     →  smart_planner.py  →  optimizer (must_run_hours för VV pre-heat)

planned_heating_schedule  →  gm_controller.py  →  myUplink Write API (GM 40940)
                              gm_controller.py  →  gm_transactions (audit)

data_logger.py  →  prediction_accuracy   (planerad vs faktisk temp, per timme)
data_logger.py  →  hot_water_usage       (VV-cykler, VP_SYSTEM_MODE=2.0)
data_logger.py  →  daily_performance     (nattaggregering: COP, kWh, komfort)
data_logger.py  →  calibration_history   (nattlig K_LEAK/K_GAIN-kalibrering med EMA)
```

---

## 6. Databas & Parametrar

### Databastabeller

| Tabell | Syfte | Uppdateras av |
|--------|-------|---------------|
| `parameter_readings` | Tidsseriedata, ~107 parametrar | data_logger (5 min) |
| `parameters` | Parametermetadata | data_logger (init) |
| `planned_heating_schedule` | 24h-plan (timgranularitet), inkl. simulated_dexter_temp | smart_planner (1/h) |
| `gm_account` | Aktuellt GM-bankssaldo (1 rad) | gm_controller (1 min) |
| `gm_transactions` | Audit-trail, 1 rad/minut, rensas efter 90 dagar | gm_controller (1 min) |
| `prediction_accuracy` | Planerad vs faktisk inomhustemp per timme (Floor-zon) | data_logger (5 min) |
| `daily_performance` | Aggregerade dagsvärden (COP, kostnad, komfort) | data_logger (midnatt) |
| `hot_water_usage` | Varmvattencykler (start, slut, varaktighet, temp, weekday, hour) | data_logger (5 min) |
| `calibration_history` | Nattlig K_LEAK/K_GAIN_FLOOR-kalibrering med EMA | data_logger (midnatt) |
| `devices` | Enhetsinställningar (komfortintervall, zonmål, bortaläge) | user_settings API |
| `learning_events` | Termisk inlärning (manuella experiment) | manuellt |
| `parameter_changes` | Logg över parameterförändringar | (ej aktiv) |

**`devices`-kolumner av vikt:**
| Kolumn | Default | Beskrivning |
|--------|---------|-------------|
| `target_indoor_temp_min` | 20.5 | Floor-zon: Pass 1-golv |
| `target_indoor_temp_max` | 22.0 | Floor-zon: Pass 2-mål |
| `target_radiator_temp` | 21.0 | Radiatorzon: Pass 2-mål (Dexter). Högre = övervåningsprioritet |
| `min_indoor_temp_user_setting` | 20.5 | SafetyGuard-gräns (hårdgräns 5°C) |
| `away_mode_enabled` | False | Bortaläge aktivt |
| `away_mode_end_date` | NULL | Naiv datetime — jämförs mot `datetime.now()` |

**OBS:** `planned_heating_schedule` raderas från `now` och framåt vid varje planeringscykel. Historiska rader (< now) bevaras upp till 48h för prediction_accuracy-validering.

### Virtuella parametrar (ej från myUplink)

| parameter_id | Källa | Beskrivning |
|---|---|---|
| `VP_SYSTEM_MODE` | data_logger (beräknad) | 0=idle, 1=heating, 2=hw, 3=defrost |
| `HA_TEMP_DOWNSTAIRS` | Home Assistant | IKEA-sensor bottenplan (Floor-zon, primär styrtemp) |
| `HA_TEMP_DEXTER` | Home Assistant | IKEA-sensor Dexters rum (Radiator-zon, min 20.0°C) |
| `HA_HUMIDITY_DOWNSTAIRS` | Home Assistant | Luftfuktighet bottenplan |
| `HA_HUMIDITY_DEXTER` | Home Assistant | Luftfuktighet Dexters rum |
| `EXT_WIND_SPEED` | Open-Meteo | Vindstyrka (m/s) |
| `EXT_WIND_DIRECTION` | Open-Meteo | Vindriktning (grader) |

### Nyckelparametrar (myUplink)

| Parameter ID | Namn | R/W | Syfte |
|---|---|---|---|
| 40004 | BT1 Utomhustemp | R | Värmekurvans ingångsvärde; DB-fallback för optimizer. Givaren sitter på fasad i västläge och kan visa solpåverkade eftermiddagstoppar som inte motsvarar verklig lufttemperatur |
| 40008 | BT2 Tilloppstemperatur | R | Vatten till radiatorer |
| 40012 | BT3 Returtemperatur | R | Retur från radiatorer |
| 40013 | BT7 VV-topptemperatur | R | Detekterar VV-läge |
| 40033 | BT50 Rumstemperatur | R | Nibes inbyggda sensor (SafetyGuard; annars föredras HA-sensor) |
| 40941 | Degree Minutes (läs) | R | Faktiskt GM-värde från pump |
| **40940** | **Degree Minutes (skriv)** | **W** | **Primär styrparameter** |
| 41778 | Kompressorfrekvens | R | >5 Hz = kompressor igång |
| 43066 | Defrost Active | R | 1 = avfrostning aktiv |
| 47007 | Värmekurva | W | Lutning (0–15), default 7.0 |
| 47011 | Kurva Offset | W | Fast offset i Nibe (−10 till +10); GM-kontroller skriver ej hit |

---

## 7. Optimizer V14.0 & GM-kontroller

### Optimizer — konstanter

Alla konfigurerbara via `.env`. Smart_planner kan overrida K_LEAK och K_GAIN_FLOOR med kalibrerade värden från `calibration_history`.

#### Floor-zon (global)

| Konstant | Default | Beskrivning |
|---|---|---|
| `OPTIMIZER_K_LEAK` | 0.002 | Värmeförlust Floor per °C delta per timme (override: calibration_history) |
| `OPTIMIZER_MIN_TEMP` | 20.5 | Komfortgolv Floor — Pass 1 |
| `OPTIMIZER_TARGET_TEMP` | 21.0 | Komfortmål Floor — Pass 2 |
| `OPTIMIZER_MIN_OFFSET` | −3.0 | Lägsta tillåtna offset |
| `OPTIMIZER_MAX_OFFSET` | 5.0 | Högsta tillåtna offset |
| `OPTIMIZER_REST_THRESHOLD` | −2.5 | Offset ≤ detta → action = REST |
| `OPTIMIZER_HOURLY_LOSS_FACTORS` | 1.0×…4.0×… | Per-timme K_LEAK-multiplikatorer (kl 15–18: 4×) |

#### Radiatorzon / Tvåzon (V14.0)

| Konstant | Default | Beskrivning |
|---|---|---|
| `K_GAIN_FLOOR` | 0.10 | Temp-ökning bottenplan per offset-enhet per timme (override: calibration_history) |
| `K_GAIN_RADIATOR` | 0.15 | Temp-ökning radiatorzon per offset-enhet per timme |
| `K_LEAK_RADIATOR` | 0.003 | Värmeförlust radiatorzon per °C delta per timme |
| `SHUNT_SETPOINT` | 40.0 | Framledning (°C) där shunten börjar begränsa golvflödet |
| `RAD_BOOST_FACTOR` | 0.012 | Extra radiatorzon-gain (°C/h) per °C framledning över SHUNT_SETPOINT |
| `DEXTER_MIN_TEMP` | 20.0 | Komfortgolv Radiatorzon — Pass 1 |
| `DEXTER_TARGET_TEMP` | 21.0 | Komfortmål Radiatorzon — Pass 2 (override: devices.target_radiator_temp) |
| `DEFAULT_HEATING_CURVE` | 7.0 | Nibes värmekurva — approximerar framledning givet offset |

**Kalibrering:** `calibration_history` uppdateras nattligen med EMA.
- Positiv bias Floor (REST) → K_LEAK för hög → sänks automatiskt
- Negativ bias Floor (REST) → K_LEAK för låg → höjs automatiskt
- Positiv bias Floor (RUN) → K_GAIN_FLOOR för låg → höjs automatiskt
- Radiator-bias → justera K_GAIN_RADIATOR eller RAD_BOOST_FACTOR (manuellt tills vidare)

### GM-kontroller — säkerhetslogik (per tick, 1 min)

1. Hämta API-data (supply, outdoor, indoor BT50, GM från pump)
2. Läs systemläge från DB (`VP_SYSTEM_MODE`)
3. Läs plan från `planned_heating_schedule` — offset och action för aktuell timme
4. **Dexter-skydd:** om `HA_TEMP_DEXTER` < 19°C och action=REST → override till RUN
5. Filtrera BT1/40004 mot planens Open-Meteo-baserade `outdoor_temp` om BT1 har tydlig västsolbias
6. Beräkna `target_supply = 20 + (20 − effective_outdoor) × curve × 0.12 + offset`
7. Beräkna `delta_gm = diff_temp × dt_min × multiplier` (turboramp 1×→3× vid deficit 2→8°C; paus vid HW och defrost)
8. Uppdatera saldo (alltid, ingen frysning)
9. **Klampning:** `balance = max(−2000, min(200, balance))`
10. **Bastu-vakt:** om BT50 > 23.5°C → balance = 100, action = MUST_REST
11. Bestäm GM att skriva: `saldo / 10` avrundat, skyddsgränser
12. Validera via SafetyGuard
13. Skriv till pump om avvikelse >50 GM eller mål ändrat >10 GM
14. Logga GMTransaction

**Vår/sommar:** outdoor >20°C → target_supply < faktisk supply → delta_gm positivt → balance träffar +200-taket. GM-kontrollern skriver GM=200 men pumpen kan ändå köra för VV-produktion.

---

## 8. API-endpoints

**FastAPI (port 8000):**

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/docs` | GET | Swagger UI |
| `/api/status` | GET | Aktuell systemstatus (temp, GM, plan) |
| `/api/plan` | GET | Aktuell 24h-plan |
| `/api/metrics` | GET | Nyckeltal (COP, drifttid) |
| `/api/parameters` | GET | Lista alla parametrar |
| `/api/parameters/{id}/history` | GET | Tidsseriedata för parameter |
| `/api/settings` | GET/POST | Enhetsinställningar (inkl. target_radiator_temp) |
| `/api/settings/away-mode` | POST | Sätt/avaktivera bortaläge |
| `/api/ai-agent/run` | POST | Kör AI-agent manuellt |
| `/api/visualizations/prediction-accuracy` | GET | Prediktionsnoggrannhet som bild |

**Flask-dashboard (port 5001):** `/`, `/dashboard`, `/performance`, `/settings`, `/api/v7/dashboard`

---

## 9. Kända fallgropar

### 1. PYTHONPATH (KRITISK)
Alla script kräver `PYTHONPATH=/home/peccz/AI/nibe_autotuner/src`. Utan detta misslyckas alla interna importer.

### 2. Timezone i smart_planner
elprisetjustnu.se returnerar priser i CET/CEST. Jämförs alltid via `.astimezone(timezone.utc)` mot `datetime.now(timezone.utc)`. Glöms detta bort → alla priser faller tillbaka på 1.0 SEK/kWh.

### 3. GM-skrivningar är irreversibla under körning
Felaktigt GM-värde håller pumpen i fel läge till nästa tick (1 min). Vid GM ≈ −400 startar elvärmen.

### 4. planned_heating_schedule — partiell radering
smart_planner raderar rader `WHERE timestamp >= now`. Om den kraschar mitt i → framtida rader kan saknas → gm_controller faller tillbaka på offset=0.

### 5. VP_SYSTEM_MODE måste finnas i parameters-tabellen
`investigate_system_mode()` skriver bara om parametern finns. Kontrollera vid fresh install: `SELECT * FROM parameters WHERE parameter_id = 'VP_SYSTEM_MODE'`.

### 6. HW-detektionslogik (VP_SYSTEM_MODE=2.0)
Villkor: `comp_freq > 5 AND supply > hw_top + 1.0 AND supply > 42.0`. Defrost (43066 > 0) har prioritet. Om 43066 saknas → defrost detekteras aldrig.

### 7. HA-sensorer via Matter/Thread
IKEA-sensorerna kopplar via Google Nest WiFi Pro (Thread Border Router) → Home Assistant (Docker, `ws://127.0.0.1:5580/ws`). Om HA:s IP ändras → Matter-integrationen kraschar.

### 8. myUplink rate limit
Free tier: 15 anrop/min. Normalt ~3 anrop/min — säkert. Öka aldrig polling-frekvensen utan att räkna anropen.

### 9. SMHIWeatherService använder Open-Meteo, inte SMHI
Klassnamnet är kvar för bakåtkompatibilitet. SMHI pmp3g-endpointen ger 404 för Upplands Väsby-koordinaterna.

### 10. Tvåzonsmodellen kräver HA_TEMP_DEXTER i DB
Om Dexter-sensorn tappar kontakt faller smart_planner tillbaka på `start_floor - 1.0` som start_radiator. Optimeraren kör då i praktiken som ettzon.

### 11. SafetyGuard använder BT50 (40033), inte HA-sensorer
BT50 sitter i teknikrummet — kan visa annan temp än HA_TEMP_DOWNSTAIRS. Gränsen är frysskydd (5°C hårdgräns), inte komfortskydd.

### 12. Kalibrering aktiveras först efter 24 rena prediction_accuracy-rader
`_calibrate_thermal_model()` kräver minst 24 samples med `|error_c| < 1.5°C`. De första 1–2 dygnen används config-defaults.

### 13. VV pre-heat kräver minst 2 historiska observationer per timme/veckodag
`_get_vv_must_run_hours()` ignorerar mönster med färre än 2 observationer. Pre-heat-skyddet är passivt de första veckorna.

### 14. BT1/40004 är solpåverkad i västläge
Utomhusgivaren sitter på fasaden i västläge. Eftermiddagssol kan ge artificiellt höga 40004-värden, t.ex. 30°C+ när verklig lufttemperatur är lägre. Kontroll 2026-04-14 till 2026-04-16 mot Open-Meteo visade maxbias cirka 14.8°C, 19.2°C respektive 15.7°C runt kl 14-15 UTC. `gm_controller` ska därför använda filtrerad `effective_outdoor_temp` för target_supply när aktuell planrad ger Open-Meteo-referens. Rå BT1 finns kvar i parameter_readings för analys av vad pumpen faktiskt ser.

---

## 10. To-do

- **Solvinst-heuristik** — Dexters rum överhettas av sol på varma dagar (+1.5°C vid outdoor > 20°C). En faktor baserad på tid + utomhustemperatur kan förebygga detta i planeringen.
- **Övervåningsensor** — saknas helt. En tredje IKEA-sensor skulle förbättra tvåzonsmodellen.
- **K_LEAK_RADIATOR / K_GAIN_RADIATOR kalibrering** — kräver prediction_accuracy per zon. `simulated_dexter_temp` finns i planned_heating_schedule men valideras inte mot HA_TEMP_DEXTER.

---

## 11. Active Work & State
*AI-agenter: uppdatera detta avsnitt efter varje session.*

```
last_updated: 2026-04-16
last_agent: Codex GPT-5
status: monitoring
current_task: effective_outdoor_temp deployad till RPi och första live-tick verifierad
recent_change: |
  - Commit a1b3d26 pushad till origin/main och riktat deployad till RPi utan att ta med orelaterade arbetskatalogändringar
  - RPi-verifiering före restart passerade: compileall för outdoor_temperature/gm_controller/smart_planner och pytest för berörda tester (9 passed)
  - nibe-gm-controller restartades och nibe-smart-planner.service kördes manuellt; nibe-autotuner, nibe-gm-controller, nibe-api, nibe-mobile och nibe-smart-planner.timer är active
  - Första live-tick efter restart verifierade filtret: raw BT1=32.0°C, Open-Meteo/planreferens=16.0°C, effective_outdoor=18.0°C och target_supply=21.7°C
  - Första live-tick skrev GM=100 i REST/WARM_OVERRIDE_DOWNSTAIRS enligt befintlig leash-logik; bank låg vid +200 och inga failed systemd-units rapporterades
  - smart_planner genererade ny plan till 2026-04-17 13:00:00 och framtida plan-dubbletter är fortsatt 0
  - Implementerat lokal helper `services/outdoor_temperature.py`: tydlig BT1-solbias klipps till referens + 2°C när BT1 är minst 4°C över referens och BT1 >= 15°C
  - gm_controller använder nu `effective_outdoor_temp` för `target_supply`, med aktuell planrads Open-Meteo-baserade `outdoor_temp` som referens; rå BT1 finns fortsatt i parameter_readings
  - smart_planner DB-fallback för outdoor filtrerar senaste BT1-värdet mot 6h median om väder-API saknas
  - Mätning 2026-04-14 till 2026-04-16 mot Open-Meteo bekräftade västfasadbias: max cirka +14.8°C, +19.2°C och +15.7°C; 2026-04-15 hade 8 timmar med BT1 mer än 4°C över Open-Meteo
  - Testtäckning tillagd för outdoor-filter och gm_controller-target_supply vid BT1-spik; hela lokala pytest-sviten passerar (15 passed)
  - Driftkontroll 2026-04-16: Produktions-DB på RPi passerar PRAGMA quick_check=ok och integrity_check=ok; journal_mode=wal och framtida planned_heating_schedule-dubbletter är 0
  - Ny projektfakta: BT1/40004-utomhusgivaren sitter på fasad i västläge, vilket förklarar solpåverkade eftermiddagstoppar och bör beaktas i framtida styr-/optimizerändringar
  - nibe-autotuner, nibe-gm-controller, nibe-api, nibe-mobile och nibe-smart-planner.timer är active; inga failed systemd-units rapporteras
  - Journalen visar endast två nibe-smart-planner-fel 2026-04-14 09:29 i samband med tidigare DB/WAL-låsproblematik; inga nya warnings/errors efter WAL-återställningen hittades i kontrollerad period
  - Komfort 2026-04-14 till 2026-04-16: huset har fortfarande legat varmt men trenden förbättras; downstairs snitt 22.59 → 22.46 → 21.94°C och Dexter snitt 22.10 → 22.25 → 21.58°C
  - Varmoverride arbetar aktivt: 2026-04-14 var alla GM-ticks REST via warm override, 2026-04-15 förekom 214 BASTU_VAKT-ticks, och 2026-04-16 hittills inga BASTU_VAKT-ticks
  - Prediction_accuracy byggs upp igen efter DB-reparationen och är bra för Floor-zonen: MAE 0.148°C 2026-04-14, 0.143°C 2026-04-15 och 0.088°C hittills 2026-04-16
  - Produktionsdatabasen på RPi visade verklig SQLite-korruption: ogiltiga sidreferenser i svansen av filen, främst i parameter_readings, prediction_accuracy och index kopplade till parameter_readings
  - nibe-smart-planner.service failade mot live-DB med "database disk image is malformed" vid läsning av senaste timmens HA_TEMP_DOWNSTAIRS, HA_TEMP_DEXTER och 40004
  - Tjänster stoppades kontrollerat, live-DB säkrades som backup och korrupt kopia behölls för rollback/forensik: nibe_autotuner.db.corrupt_20260414_070759 samt tidigare *.bak_
  - Ny frisk DB byggdes med exakt prod-schema från sqlite_master/.schema; läsbara tabeller kopierades över och parameter_readings salvades upp till verifierat säker cutoff id <= 800000
  - prediction_accuracy kunde inte salvagas rent från den korrupta filen och är tom efter reparation; tabellen finns kvar i schema
  - Reparerad DB passerar PRAGMA quick_check=ok på RPi efter swap
  - nibe-autotuner, nibe-gm-controller och nibe-api startades igen; smart_planner kördes manuellt framgångsrikt och genererade ny plan utan DB-fel
  - Rotorsaksanalys: inga kernel/ext4/mmc/undervoltage-fel hittades i tillgängliga loggar; vcgencmd visar throttled=0x0
  - RPi saknar persistent journal (journald Storage=volatile), vilket kraftigt försvårar bevisning för äldre I/O- eller power-event
  - RPi root-mount använder ext4 med noatime,commit=600; lång commit-intervall ökar risk för större SQLite-förlust vid abrupt avbrott
  - Tidigare crash-händelser finns i last -x historiken, men inte tidsmässigt kopplade till denna incident
  - Efter DB-swap fortsatte nibe-mobile.service kasta "database disk image is malformed" eftersom processen hållit den gamla korrupta DB-filen öppen sedan 2026-03-24; detta var ett separat restart-behov, inte ny korruption i den reparerade DB:n
  - nibe-mobile.service restartades därefter explicit; ny process öppnar endast data/nibe_autotuner.db och /api/v7/dashboard svarar 200 igen
  - Persistent journald aktiverades på RPi via /etc/systemd/journald.conf.d/persistent.conf med Storage=persistent, SystemMaxUse=200M, RuntimeMaxUse=100M och MaxRetentionSec=14day
  - systemd-journald restartades och journalctl rapporterar nu 71.0M använd diskjournal; /var/log/journal finns och används
  - ext4 root-mount på RPi sänktes från commit=600 till commit=30 via /etc/fstab-backup + kontrollerad reboot
  - Efter reboot verifierades root som ext4 rw,noatime,commit=30 och nibe-autotuner, nibe-gm-controller, nibe-api samt nibe-mobile kom upp igen
  - /api/v7/dashboard svarar fortsatt 200 efter reboot
  - Vid manuell planner-verifiering efter reboot failade smart_planner med sqlite3.OperationalError: database is locked på BEGIN EXCLUSIVE; detta är låsrelaterat, inte ny korruption
  - Produktions-DB växlades tillbaka till WAL på RPi efter backup av livefilen (nibe_autotuner.db.prewal_20260414_093144) och kontrollerad stop/start av alla DB-konsumenter
  - Efter WAL-återställning verifierades journal_mode=wal, planned_heating_schedule uppdaterades till 2026-04-15 06:00:00 och smart_planner körde igenom utan database is locked
  - nibe-mobile, nibe-autotuner, nibe-gm-controller och nibe-api är active efter WAL-återställningen; /api/v7/dashboard svarar 200
open_issues:
  - prediction_accuracy-historik förlorades i reparationen och behöver byggas upp igen över tid eller backfillas från annan källa om sådan finns
  - parameter_readings efter ungefär 2026-04-04 salvagades inte från den korrupta svansen; ny data skrivs igen från live-drift
  - Trolig grundorsak är lagrings-/avbrottsrelaterad truncering eller annan SQLite-filskada i svansen av DB:n; exakt event kan inte bevisas med nuvarande loggnivå
  - ext4 root kör nu med commit=30; följ upp eventuell påverkan på SD-slitage och normal drift kommande dagar
  - WAL-filer beter sig normalt vid kontroll 2026-04-16; fortsätt följa upp över längre tid att inga nya database is locked- eller malformed-fel uppstår
  - Historiska plan-dubbletter finns kvar i produktionsdatabasen men framtida plan-dubbletter är 0 efter deploy
  - Behöver 24-48h uppföljning för att se om varmoverride sänker andelen tid över 22°C och minskar BASTU_VAKT
  - Ren RPi-deploy ska fortsätta exkludera/protecta .env och logs/ för att undvika servicefel
  - Vid gm_controller-restart kan regulatorn skriva GM direkt enligt befintlig leash-logik; följ första minutens write efter restart
  - Pytest passerar lokalt (15 passed) men visar Python 3.14-deprecation-varningar för utcnow/sqlite datetime
  - myUplink-tokens som tidigare låg i repo/history bör roteras
```

### Senaste ändringar

| Datum | Vad |
|-------|-----|
| 2026-04-16 | Commit a1b3d26 deployad riktat till RPi; gm_controller restartad; första tick verifierade BT1-filter raw 32.0°C → effective 18.0°C mot planreferens 16.0°C och GM=100 i REST/warm override |
| 2026-04-16 | Implementerat `effective_outdoor_temp` lokalt: gm_controller filtrerar västsolpåverkad BT1 mot planens Open-Meteo-referens; smart_planner DB-fallback dämpar BT1-spikar via 6h median; pytest 15 passed |
| 2026-04-16 | Dokumenterat att BT1/40004-utomhusgivaren sitter på västfasad och kan ge solpåverkade eftermiddagstoppar; framtida styrlogik bör överväga filtrerad/blandad utetemp |
| 2026-04-16 | Driftkontroll efter DB-reparation: DB quick_check/integrity_check ok, WAL aktivt, huvudtjänster active, dashboard svarar, inga framtida plan-dubbletter; komfort fortsatt varm men förbättrad och BASTU_VAKT ej observerad hittills under dagen |
| 2026-04-14 | Produktions-DB återställd till WAL efter backup av livefil; journal_mode=wal verifierad; smart_planner kör nu igen utan database is locked; dashboard och huvudtjänster verifierade active |
| 2026-04-14 | RPi rootfs ändrad från ext4 `commit=600` till `commit=30` med reboot; mount verifierad efter uppstart; dashboard och huvudtjänster uppe; planner-verifiering visade nytt `database is locked` i DELETE-mode |
| 2026-04-14 | Persistent journald aktiverad på RPi med Storage=persistent, 200M diskgräns och 14 dagars retention; journald verifierad aktiv och skrivande till disk |
| 2026-04-14 | nibe-mobile.service restartad efter DB-recovery; ny process verifierad mot endast data/nibe_autotuner.db och /api/v7/dashboard returnerar 200 |
| 2026-04-14 | Rotorsaksanalys klar: inga kernel/mmc/ext4/undervoltage-fel i tillgängliga loggar; journald är volatile; rootfs kör ext4 `commit=600`; nibe-mobile visades hålla korrupt DB-fil öppen efter swap och förklarar fortsatta dashboard-500 |
| 2026-04-14 | Produktions-DB på RPi reparerad efter SQLite-korruption; backup + korrupt kopia sparade; ny DB byggd från prod-schema med frisk data + parameter_readings upp till id 800000; quick_check ok; smart_planner kördes framgångsrikt igen |
| 2026-04-13 | Commit 7f4d43a deployad till RPi; första live-tick gav WARM_OVERRIDE_DOWNSTAIRS och GM write 100; nibe-gm-controller verifierad active |
| 2026-04-13 | Varmoverride i gm_controller implementerad lokalt: HA_TEMP_DOWNSTAIRS/HA_TEMP_DEXTER kan tvinga REST med hysteresis; pytest 10 passed |
| 2026-04-10 | Commit c0a6367 deployad till RPi; tjänster verifierade; prediction_accuracy backfill skapade 47 rader; framtida plan-dubbletter 0 |
| 2026-04-10 | Lokal venv återskapad och requirements installerade; pytest.ini begränsar testinsamling till tests/; pytest: 6 passed |
| 2026-04-10 | Testtäckning skapad för feedbackloopen: dubblettplaner, prediction_accuracy-backfill och saknad CalibrationHistory |
| 2026-04-10 | Autonom feedbackloop lokalt: 7-dagars backfill av prediction_accuracy och ikappkörning av saknad CalibrationHistory |
| 2026-04-10 | Review-fixar lokalt: token-sanering, GM-testspärr, planner-raderingsfix, deterministiskt planval och deploy-preflight |
| 2026-04-10 | RPi-drift utvärderad för 2026-04-03 till 2026-04-10: tjänster uppe, övervärme/BASTU_VAKT, plan-dubbletter, saknad prediction_accuracy |
| 2026-04-07 | DNA.md skapad — primärt referensdokument (ersätter architecture.md) |
| 2026-04-02 | Autonom kalibrering: `_calibrate_thermal_model()` med EMA, lagras i calibration_history |
| 2026-04-02 | VV pre-heat: smart_planner blockerar REST för timmar med historiska VV-mönster (≥2 obs) |
| 2026-04-02 | Dexter-skydd i regulatorn: gm_controller overridar REST→RUN om HA_TEMP_DEXTER < 19°C |
| 2026-04-02 | Tvåzons-temperaturmål: target_radiator_temp i devices, optimizer, API och settings-UI |
| 2026-04-02 | Bugfix: SafetyGuard BT50-uppslag via korrekt FK (ej hårdkodat rad-ID) |
| 2026-04-02 | Bugfix: away_mode datetime-jämförelse (timezone-naiv vs UTC) |
| 2026-04-01 | V14.0: Tvåzonsmodell (golvvärme + radiatorer), Open-Meteo ersätter SMHI |
| 2026-04-01 | V13.0: Två-pass-algoritm, COPModel bilinear, negativa offset, linjär turboramp |
| 2026-04-01 | Ny data: gm_transactions, prediction_accuracy, daily_performance, hot_water_usage |
| 2026-04-01 | Bortaläge (komplett), prediction accuracy-visualisering, systemd watchdog |

---

## 12. Decision Log
*Varför viktiga arkitektoniska val gjordes.*

| Datum | Beslut | Anledning |
|-------|--------|-----------|
| 2026-04-16 | GM-kontrollerns `target_supply` ska baseras på filtrerad `effective_outdoor_temp` när BT1/40004 tydligt överstiger Open-Meteo-referensen från aktuell planrad | BT1 sitter på västfasad och visade upp till cirka +19°C solbias mot Open-Meteo. Rå BT1 ger då orimligt låg target_supply och kan störa GM-bankens energibalans. Filtreringen är konservativ: den aktiveras bara vid tydlig varm bias och klipper till referens + 2°C, medan rå BT1 behålls i mätdata. |
| 2026-04-14 | Produktions-DB på RPi ska köras i WAL-läge | DELETE-mode i kombination med samtidiga läsare gjorde att smart_planner failade på `BEGIN EXCLUSIVE` med `database is locked`. WAL återställde den samtidighetsmodell som projektet utgår från och plannern verifierades fungera igen. |
| 2026-04-14 | ext4 rootfs på RPi ska inte använda `commit=600`; `commit=30` används tills vidare | 600 sekunders commit-intervall ökar mängden osynkad data vid abrupt avbrott. 30 sekunder minskar återhämtningsfönstret utan att vara extremt aggressivt mot SD-kortet. |
| 2026-04-14 | Persistent journald ska vara standard på RPi för denna installation, med explicit storleksgräns | SQLite-/driftincidenten kunde inte bevisas i efterhand när journald var volatile. Persistent journal med begränsad storlek ger incidentspår utan okontrollerad loggtillväxt på SD-kortet. |
| 2026-04-14 | Vid framtida DB-swap/recovery på RPi måste även `nibe-mobile.service` räknas som DB-konsument och restartas eller stoppas explicit | Flask-PWA:n kan hålla gamla DB/WAL-filhandtag öppna i veckor. Efter recovery fortsatte den läsa `nibe_autotuner.db.corrupt_20260414_070759`, vilket gav falska fortsatta `malformed`-fel trots frisk live-DB. |
| 2026-04-14 | Raspberry Pi-observability för DB-incidenter ska inte förlita sig på volatil journal ensam | `Storage=volatile` gjorde att tidigare bootloggar saknades. För att kunna bevisa SD/I/O/power-orsaker vid SQLite-korruption behövs persistent journald eller separat loggning. |
| 2026-04-14 | Vid partiell SQLite-korruption på RPi ska återställning ske via exakt prod-schema + selektiv table-copy från läsbara tabeller, inte via lokal ORM-init eller blind `.recover` | Prod-schema hade drivit från lokala modeller och `.recover` gav inte användbar databas för denna skada. Exakt schema från sqlite_master bevarar kompatibilitet, och selektiv copy möjliggör kontrollerad salvage med tydlig rollback. |
| 2026-04-13 | Varm-sida override ska ske i gm_controller med HA-zoner och hysteresis | Övervärmen kvarstod trots fungerande planner/feedbackloop. BT50/BASTU_VAKT reagerar för sent; HA_TEMP_DOWNSTAIRS och HA_TEMP_DEXTER ska kunna blockera fortsatt uppvärmning innan huset blir bastuvarmt. |
| 2026-04-10 | Hårdkodade myUplink-tokens får inte finnas i repo eller maintenance-script | Tokens har WRITESYSTEM-scope och kan påverka verklig värmepump; autentisering ska ske via OAuth-flödet till `~/.myuplink_tokens.json`. |
| 2026-04-10 | Live-GM-verktyg måste kräva explicit dubbel bekräftelse | GM 40940 påverkar live-styrning direkt; manuella verktyg ska inte kunna köras av misstag eller via automatisk testkörning. |
| 2026-04-10 | Deploy ska ha preflight före commit/sync/restart | `deploy_v4.sh` gör produktionsändringar; synlig status och token-check minskar risken att oavsiktliga filer eller credentials skickas till RPi. |
| 2026-04-10 | Feedbackloop ska vara passiv mot live-styrning | Kalibrering får bara skriva feedback-/kalibreringstabeller och användas av smart_planner i nästa planeringscykel; den får inte skriva GM, ändra safety limits eller starta om tjänster. |
| 2026-04-07 | Standardisera på DNA.md som Source of Truth | Koordinera AI-agenter (Claude, Gemini) över tid — samma metod som sys-projektet |
| 2026-04-01 | GM-bank (Degree Minutes) som primär styrparameter, ej Curve Offset 47011 | GM ger direkt kontroll av kompressionsstartpunkten utan att konflikta med Nibes interna PID. Curve Offset (47011) påverkar hela värmekurvan permanent. |
| 2026-04-01 | Deterministisk optimizer (två-pass) ersätter LLM-baserad AI-agent | LLM-agenten fattade oförutsägbara beslut, svår att debugga och felsäkra. Deterministisk algoritm ger reproducerbara, verifierbara resultat. |
| 2026-04-01 | Open-Meteo ersätter SMHI pmp3g | SMHI pmp3g returnerar 404 för Upplands Väsby-koordinaterna. Open-Meteo är gratis, global och ger timvisa prognoser utan nyckel. |
| 2026-04-01 | elprisetjustnu.se ersätter Tibber | Tibber kräver aktiv prenumeration. elprisetjustnu.se är gratis, ingen API-nyckel, täcker SE3/SE4. |
| 2026-04-01 | Tvåzonsmodell (Floor + Radiator) i V14.0 | Shuntfysiken gör att golvvärme och radiatorer reagerar olika på offset-ändringar. Ettzon-modellen underskattade Dexter-zonens uppvärmning systematiskt. |
| 2026-04-01 | Kalibrering via EMA i calibration_history | K_LEAK och K_GAIN varierar med årstid och husanvändning. EMA med nattlig uppdatering ger stabil anpassning utan oscillation. |
| 2025-12-01 | Raspberry Pi 4 som produktionsenhet | Låg energiförbrukning (2W), nära värmepumpen, stabilt Linux. Engångsinvestering ~500 SEK. |
| 2025-12-01 | SQLite med WAL-mode | Enkel att underhålla, inga databasservrar. WAL-mode löser concurrent read/write (data_logger + gm_controller). |
| 2025-12-01 | systemd Restart=always för alla tjänster | Garanterar återstart vid krasch utan manuell intervention. Watchdog (120s) för gm_controller ger extra skydd. |

---

*DNA.md är ett levande dokument. Uppdatera det. Låt det inte drifta från verkligheten.*
