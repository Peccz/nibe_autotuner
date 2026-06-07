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

## 5b. Available Codex Skills In This Workspace
- `workspace-governance`: Workspace-level DNA, project registry, and governance handoff workflow.
- `nibe-autotuner`: Project-specific Nibe F730 optimization, GM safety, DB, dashboard, and deploy workflow.
- `security-best-practices`: Security review support for credentials, env files, deploy, and live-control boundaries.
- `security-threat-model`: Threat-modeling support for control-loop, stale telemetry, and trust-boundary changes.

### Skill Usage Rule
- Use `workspace-governance` for cross-project or `MASTER_DNA.md` work.
- Use `nibe-autotuner` for all project-local optimizer, GM controller, data logger, DB, dashboard, deploy, and documentation tasks.
- Use `security-best-practices` when touching credentials, env files, deploy flow, service config, or live write boundaries.
- Use `security-threat-model` before broadening automation authority, safety limits, or trust assumptions.

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
last_updated: 2026-06-07
last_agent: Codex GPT-5
status: v16_active_deployed
current_task: V16 robust styrlogik riktat deployad och aktiverad på RPi
recent_change: |
  - 2026-06-07 V16 robust styrlogik riktat deployad och aktiverad på RPi utan `deploy_v4.sh` på grund av kraftigt smutsiga lokal/RPi-arbetskataloger; endast V16-relaterade styr-/test-/backtestfiler och DNA synkades
  - RPi-backup före deploy finns i `/tmp/nibe_v16_deploy_20260607/`: `code_before.tgz`, `nibe_before.db` och `env_before`; rollback är att återställa filerna, kopiera tillbaka `env_before` eller sätta `PLANNER_ENGINE=v15_active`, köra smart planner manuellt och restarta `nibe-gm-controller`
  - RPi-verifiering före aktivering: DB `quick_check=ok`, journal_mode WAL, huvudtjänster active och `systemctl --failed` 0 units; RPi `py_compile` passerade och riktade pytest passerade (34 passed)
  - `.env` ändrad från `PLANNER_ENGINE=v15_active` till `PLANNER_ENGINE=v16_active`; `nibe-smart-planner.service` kördes manuellt och skrev V16-plan med 9 REST, 14 RUN och 1 BOOST, min simulerad Dexter ca 20.0°C
  - Planner-journal verifierad: `v16_candidate`, `PLANNER_ENGINE=v16_active — writing V16 robust plan`, `planned_actions=... engine=v16`; sensorläge är fallback och huset är över max, så V16/GM går konservativt
  - `nibe-gm-controller.service` restartades 2026-06-07 15:14 CEST; första GM-ticks efter restart verifierade REST via `WARM_OVERRIDE_DOWNSTAIRS`, GM-write 100, bank 200 och ingen negativ skuldackumulering
  - Efter deploy är `nibe-gm-controller`, `nibe-smart-planner.timer`, `nibe-autotuner`, `nibe-api` och `nibe-mobile` active och `systemctl --failed` visar 0 units; ingen DB-migration, inga nya beroenden och inga safety limits ändrades
  - 2026-06-06 V16 robust styrlogik implementerad lokalt: `plan_v16_robust` återanvänder V15:s sol/vind/tröghet/shunt-/radiatorfysik men prioriterar komfort/safety, övervärme-shedding och därefter pris; pumpens 13°C/8h-spärr används inte som styrvillkor
  - `smart_planner` kan nu köra `PLANNER_ENGINE=v16_active`, loggar `v16_candidate` med actionfördelning, min/max simulerade zoner, sensor_mode, fallback-pristimmar och skäl; V14/V15 finns kvar som fallback/jämförelse
  - V16 blockerar positiv offset/BOOST utanför morgonfönstret, vid aktuell övervärme, vid vädringscap och när prisdata faller tillbaka till 1.0; övervarmt hus får REST/negativ offset även om elpriset är lågt
  - Read-only backtestscriptet `scripts/backtest_v15_shadow.py` rapporterar nu V14, V15 och V16 sida vid sida inklusive REST/BOOST, under-/överkomfort, undvikbar övervärme och viktat pris
  - Regressionstester tillagda för V16 övervärmeshedding, fallback-prisblockerad morgonBOOST, morgonBOOST endast vid verkligt golvrisk, varm sensorfallback samt GM-controller som tvingar överhettad BOOST-plan till REST
  - Lokal verifiering 2026-06-06: riktade styrtester passerar, full `pytest -q` 61 passed och `py_compile` passerar för V16/planner/GM/config/backtest; endast Python/SQLAlchemy deprecation-varningar
  - Read-only RPi-backtest via SQLite-backup till `/tmp` över jämförbara fönster 2026-06-04 till 2026-06-05: V16 blev identisk med V15 i REST/BOOST/komfort/pris eftersom seed-planens positiva offset inte kunde blockeras utan simulerad golvrisk; V16 är därmed säkerhetsmässigt konservativ men inte ännu bättre än V15 på dessa få fönster
  - Ingen deploy, service restart, DB-migration, live configändring eller manuell/live GM-skrivning gjordes i denna session; RPi-utrullning kräver kontrollerad deploy och första GM-ticks-verifiering
  - 2026-06-06 driftutvärdering read-only: `PLANNER_ENGINE=v15_active`, DB `quick_check=ok`, `nibe-gm-controller`, `nibe-smart-planner.timer`, `nibe-autotuner`, `nibe-api` och `nibe-mobile` är active, `systemctl --failed` visar 0 units
  - Sedan V15 active 2026-05-19 21:27 till 2026-06-06 08:05 CEST: downstairs 20.40/23.10/25.95°C min/avg/max, Dexter 20.95/23.26/26.84°C, BT50 19.7/23.24/26.2°C; mycket låg undershoot men kraftig övervärme
  - Senaste 7 dygn: downstairs över 21.8°C i 93.9% av samples, Dexter över 21.3°C i 100%, BT50 över 21.8°C i 95.3%; senaste 24h alla zonmått över övre bandet
  - GM-regulatorn är säker men safety-dominerad: sedan V15 active 19 618 GM-ticks med 11 681 warmoverride och 7 647 BASTU_VAKT; inga GM<=-300 och bank hålls inom -239..200, senaste 7 dygn GM=100 hela tiden
  - V15-planeraren är aktiv och stabil i tillgänglig journal: 39 analyserade körningar sedan 2026-05-20, alla `engine=v15`, 0 errors, viktat V15-pris lägre än V14 i 38/39 körningar; loggad min Dexter hålls vid 20.00°C efter hard-floor-fixen
  - Planner-journalen visar återkommande `sensor_mode=fallback`; HA/IKEA-zonsensorerna är stale igen från 2026-06-05 19:03 UTC medan BT50/myUplink fortsätter uppdateras
  - Nuvarande aktiva plan 2026-06-06 har 6 REST, 14 RUN och 4 BOOST kommande 24h; simulerat min Dexter 20.02°C men planen innehåller nattliga BOOST-timmar när kommande prisdata verkar vara fallback 1.0
  - Slutsats: V15 fungerar tekniskt och prisoptimeringen ser bättre ut än V14, men komfortmålet missas åt varma hållet. Nästa styrfix bör fokusera på sommar-/övervärmeläge: stoppa natt-BOOST vid övervärme/fallbackpriser, minska morgonrecovery när huset redan är varmt, och göra HA-sensorstale till tydligare konservativ REST snarare än recovery
  - 2026-05-19 21:27 CEST: `PLANNER_ENGINE=v15_active` satt i RPi `.env` efter backup till `/tmp/nibe_env_before_v15_active_20260519_2127`; settings verifierade `v15_active`
  - `nibe-smart-planner.service` kördes manuellt i active-läge 2026-05-19 21:27 CEST och skrev V15-plan till `planned_heating_schedule`: actions 8 REST, 12 RUN, 4 BOOST, `engine=v15`, min simulated floor 21.21°C, min simulated Dexter 20.07°C
  - Första GM-ticks efter V15-plan verifierade REST/GM=100 med `WARM_OVERRIDE_DOWNSTAIRS`, bank 200 och fortsatt undertryckt negativ skuld; flera tickar fram till 21:35 CEST var stabila utan failed units
  - Produktions-DB `quick_check=ok`; `nibe-gm-controller`, `nibe-smart-planner.timer`, `nibe-autotuner`, `nibe-api` och `nibe-mobile` är active; `systemctl --failed` visar 0 units
  - Rollback för V15 active: återställ `.env` från `/tmp/nibe_env_before_v15_active_20260519_2127` eller sätt `PLANNER_ENGINE=v15_shadow`, kör `nibe-smart-planner.service` manuellt för V14-planwrite och verifiera nästa GM-tick
  - 2026-05-19 21:20 CEST: V15 justerad så Dexter-golvet klampas till `settings.DEXTER_MIN_TEMP` (20.0°C) före vädringsmjukning; aktiv vädring kan fortfarande temporärt sänka lokalt golv
  - V15:s övervärme-/prisreduktion får inte längre acceptera små komfortundershoots via 0.08-0.12°C marginal; floor/Dexter måste hålla aktiva golv strikt i kandidatplanen
  - Regressionstest tillagt för 2026-05-19-liknande övervärmeläge: V15 utan vädring måste hålla Dexter minst 20.0°C
  - Verifiering: lokal riktad svit 28 passed, lokal full svit 56 passed, RPi riktad svit 28 passed och `py_compile` OK
  - Manuell smart_planner-körning i fortsatt `v15_shadow` 2026-05-19 21:20 CEST gav `v15_shadow actions={'REST': 8, 'RUN': 11, 'BOOST': 5}`, `min_floor=21.22C`, `min_dexter=20.04C`, `weighted_price=1.688 vs_v14=1.729`; aktiv plan skrivs fortsatt av V14 (`engine=v14`)
  - 2026-05-19 21:13 CEST: V15-shadow utvärderad read-only efter deploy. Inga planner-/GM-fel hittades, inga vädringshändelser detekterades och huvudtjänsterna fortsätter stabilt
  - Senaste 24h är huset fortfarande för varmt: downstairs 22.21/22.59/23.50°C och Dexter 21.72/22.43/24.11°C min/avg/max; båda zonerna låg över övre komfortbandet i 100% av samples
  - Sedan vädringsdeployen är GM helt warmoverride-dominerad: 33 REST-ticks med `WARM_OVERRIDE_DOWNSTAIRS`, GM=100 och bank=200; negativ skuld byggs inte
  - Aktiv V14-plan efter manuell körning har 3 REST + 21 RUN kommande 24h och simulerar Dexter ned till ca 20.44°C; V15-shadow för samma körning ville ha 8 REST + 12 RUN + 4 BOOST, lägre viktat pris 1.646 vs 1.711 men simulerade min_dexter=19.84°C
  - Slutsats: V15 har bättre pris-/REST-beteende men får inte aktiveras live innan Dexter-golvet i shadow/backtest är säkert över accepterad morgon-/nattkomfort eller explicit nattgolv beslutas
  - 2026-05-19 20:30 CEST: vädringsskyddet och `PLANNER_ENGINE`-vägen är riktat deployade till RPi utan `deploy_v4.sh`; bara berörda `src/`, `tests/` och `DNA.md` synkades eftersom både lokal och RPi-arbetskatalog är dirty
  - RPi-verifiering före restart: tempkopian i `/tmp/nibe_v15_guard_probe` passerade riktade tester (27 passed) och `py_compile`; live-katalogen passerade därefter `py_compile` och riktade tester (27 passed)
  - `nibe-gm-controller.service` restartades 2026-05-19 20:30 CEST och första tick verifierades: warmoverride höll GM=100, bank=200 och negativ skuld undertrycktes
  - `nibe-smart-planner.service` kördes manuellt 2026-05-19 20:30 CEST i default `PLANNER_ENGINE=v15_shadow`; loggen visar `engine=v14`, `v15_shadow actions={'REST': 8, 'RUN': 12, 'BOOST': 4}`, `ventilation_floor_hours=0`, `ventilation_dexter_hours=0`
  - Live-planen skrivs fortfarande av V14; V15 active är inte aktiverad och kräver explicit konfigändring till `PLANNER_ENGINE=v15_active`
  - Produktions-DB `quick_check=ok`, `nibe-gm-controller`, `nibe-smart-planner.timer` och `nibe-autotuner` är active efter deploy; ingen DB-migration, inga nya beroenden och inga safety limits ändrades
  - Implementerat lokalt vädringsskydd i `services/ventilation_guard.py`: snabb lokal temperaturdipp i floor/Dexter mot stabil annan zon/BT50 klassas som `ventilation_event` i 2h utan DB-schemaändring
  - V15 tar nu emot vädringshändelser, mjukar temporärt komfortgolvet för drabbad zon och cappar recovery-offset till mild värme under aktiv vädring; kritiskt låg zon under 18.5°C behandlas inte som aktiv vädring
  - `smart_planner` detekterar vädring från befintlig `parameter_readings`-historik, loggar `ventilation_event`, skickar signalen till V15 och har ny `PLANNER_ENGINE=v14|v15_shadow|v15_active` där default fortsatt är `v15_shadow`
  - `gm_controller` detekterar samma lokala vädringsmönster, blockerar aktuell/nästa BOOST vid aktiv vädring och låter Dexter REST→RUN-skyddet vila under vädring i stället för att värma hela huset aggressivt
  - V15 kan nu skriva plan endast om `PLANNER_ENGINE=v15_active` sätts; live default är oförändrad skuggdrift och ingen RPi-config/deploy gjordes i denna session
  - Testtäckning tillagd för Dexter-/nedervåningsvädring, helhuskyla som inte ska klassas som vädring, kritiskt kall zon, V15 recovery-cap och GM-controller BOOST/Dexter-override-blockering vid vädring
  - Lokal verifiering 2026-05-16: riktade tester passerar (27 passed), full `pytest -q` passerar (55 passed) och `py_compile` passerar för ventilation_guard, V15, smart_planner, gm_controller och config
  - Ingen DB-migration, inga nya beroenden, inga safety limits ändrade, ingen deploy/restart och inga manuella/live GM-skrivningar gjordes
  - 2026-05-15 18:15 CEST riktad deploy genomförd till RPi utan `deploy_v4.sh` eftersom både lokal och RPi-arbetskatalog är smutsiga; endast berörda styr-/testfiler synkades med rsync
  - RPi-backup före deploy: `/tmp/nibe_v15_deploy_20260515_1814/` innehåller `code_before.tgz` och SQLite-backup `nibe_before.db`
  - RPi-verifiering före restart: `py_compile` för comfort_profile/gm_controller/optimizer/smart_planner/v15_mpc/backtest passerade och riktade pytest på RPi passerade (37 passed)
  - `nibe-smart-planner.service` kördes manuellt 2026-05-15 18:15 CEST med ny kod: `room_heat_surplus=1.65C`, `profile=evening_preshed`, `v15_shadow` loggades med 6 REST, 14 RUN, 4 BOOST, min_floor 20.44C, min_dexter 20.46C och weighted_price 1.804 vs V14 1.847
  - Live-planen skrivs fortfarande av V14, inte V15: efter manuell planner blev närmaste plan RUN -2.0 följt av RUN/0; V15 är skuggdiagnostik och backtestunderlag
  - `nibe-gm-controller.service` restartades 2026-05-15 18:15 CEST; första tre tickarna verifierade ny `room_heat_surplus`-logg, warmoverride Dexter, GM-write 100 och bank 200 utan negativ skuld
  - Efter deploy är DB `quick_check=ok` och huvudtjänsterna active; `logrotate.service` är fortsatt failed men inte värmestyrningskritiskt
  - Drift utvärderad read-only 2026-05-15 18:02 CEST: RPi-tjänsterna `nibe-autotuner`, `nibe-gm-controller`, `nibe-api`, `nibe-mobile` och `nibe-smart-planner.timer` är active; DB `quick_check=ok`, journal_mode=wal
  - Dataflödet är aktuellt: senaste `parameter_readings` och `gm_transactions` ligger inom ca 4 minuter; HA-zonsensorerna är friska igen (`sensor_mode=normal` i planner)
  - Senaste 24h: downstairs min/avg/max 20.33/21.79/22.85°C och Dexter 21.15/21.95/23.10°C; Dexter låg över 21.3°C i 254 av 287 femminuterssamples och downstairs över 21.8°C i 159 av 287 samples
  - GM-controller kör huvudsakligen REST via warmoverride: 1153 REST-ticks mot 80 RUN-ticks senaste 24h; WARM_OVERRIDE_DOWNSTAIRS 755 ticks och WARM_OVERRIDE_DEXTER 398 ticks; hotfixen fungerar genom att bank hålls 100-200 och negativ warmoverride-skuld undertrycks
  - Det fanns 2 `GM=-350` RUN-ticks senaste 24h, men de inträffade utan safety_override och bank minimum var ca -512, inte den tidigare nästan -2000-skuldproblematiken
  - Planner kör varje timme och genererar V14-planer, men produktion saknar lokala V15-/`room_heat_surplus`-ändringar: journalen saknar `v15_shadow`, och RPi-koden matchar inte senaste lokala arbetsläge
  - Slutsats: systemet är driftmässigt stabilt men komfortregleringen är fortfarande reaktiv och varm; warmoverride är skyddet som styr ner huset, medan planner fortfarande inte är tillräckligt proaktiv för Dexter-/kvällsövervärme
  - Ej deployat, restartat, migrerat eller skrivit GM manuellt under utvärderingen
  - Implementerat `scripts/backtest_v15_shadow.py`: read-only V14-vs-V15-backtest som använder historiska `planned_heating_schedule`-rader som V14-bas och räknar V15 offline från samma starttemp/pris/väder
  - Backtest-rapporten jämför REST/BOOST, min floor/Dexter, timmar under golv, timmar över övre band, undvikbar övervärme och lastviktat elpris; ingen DB-write sker
  - Lokal backtest mot `/tmp/nibe_cold_morning_20260513.db` 2026-05-11 04:00 till 2026-05-13 03:00 gav 48 jämförbara 24h-fönster: V15 tog bort simulerad undershoot (under floor 18.00h -> 0.00h), sänkte undvikbar övervärme marginellt (1.81h -> 1.65h), men hade fler över-upper timmar totalt (2.25h -> 5.54h) eftersom Dexter ofta låg nära golvet medan nedervåning var varm
  - Slutsats från backtest: V15-kandidaten är säkrare för morgon/Dexter än V14 i detta urval, men nästa förbättring ska rikta zonkonflikten - mer radiatorvärme/Dexter-prioritet utan onödig golvvärme - innan V15 får live-planwrite
  - Testtäckning tillagd i `tests/test_v15_backtest.py`; lokal verifiering 2026-05-14: riktade V15/backtest-tester 7 passed, full pytest 47 passed och py_compile passerar för backtest/V15/smart_planner
  - Implementerat lokal V15-skuggplanner i `src/services/v15_mpc.py` som samlar zonmodell, shunt/radiatorrespons, hydronisk restvärme, rumsmassa, vindförlust och konservativ solinstrålning i en reproducerbar kandidatmodell
  - `smart_planner` kör nu V15 i skugga efter V14-optimeringen och loggar `v15_shadow` med actionfördelning, min floor/Dexter, viktat pris, skäl och första offsets; V15 skriver inte planrader och påverkar inte GM
  - Weather alignment i `smart_planner` använder nu forecastens `wind_speed` i planraderna och skickar både vind och `cloud_cover` till V15-shadow
  - V15-reglerna håller kvar lärdomarna från senaste drift: `heat_in_flight` får inte maskera morgonundershoot, billig sömnperiod får inte opportunistiskt BOOST:a före morgonfönster, kvällsövervärme ger explicit REST, och radiator/Dexter-underskott får högre framledningsrespons
  - Testtäckning tillagd i `tests/test_v15_mpc.py` för kall morgon 2026-05-13, ingen billig nattboost före morgon, kvälls-REST vid övervärme, Dexter-kallt/radiatorrespons samt sol/vindpåverkan
  - Lokal verifiering 2026-05-14: `PYTHONPATH=/home/peccz/AI/nibe_autotuner/src venv/bin/python -m pytest -q` passerar (46 passed); `py_compile` passerar för V15, smart_planner, optimizer, gm_controller och comfort_profile
  - Ingen deploy, ingen service restart, ingen DB-migration, inga nya beroenden, inga GM-skrivningar och inga safety limits ändrade
  - Morgonincident 2026-05-13 analyserad: huset upplevdes kallt; live-data visade nedervåning ca 21.16-21.18°C runt 05:00 mot morgongolv 21.2°C och BT50 21.0°C, medan planen låg på RUN 0 utan morgon-BOOST
  - Rotorsak: `heat_in_flight` räknades som rumstemperaturkredit i Pass 1 och kunde därmed låta morgonkomfortgolvet anses uppfyllt trots att lagrad plan/faktisk rumstemperatur låg under/nära golvet
  - Lokal fix: optimizer Pass 1 använder nu rå temperaturprognos utan residual `heat_in_flight` för komfortgolv; restvärme får fortsatt användas för övervärme-/BOOST-blockering men inte för att maskera morgonundershoot
  - Regressionstest tillagt för 2026-05-13-liknande morgonfall: `heat_in_flight=0.4` får inte blockera BOOST när floor recovery behövs
  - Lokal verifiering efter fix: `venv/bin/python -m pytest -q` passerar (40 passed); `py_compile` passerar för ändrade styrmoduler
  - Implementerat lokal styrförbättring för sov-/morgonprofil: `evening_preshed` från 17:00, sömnfönster 22:00-06:00, striktare BOOST-fönster från 05:00 och planeringsmax som använder nattens övre band inför kvällen
  - Planner/optimizer har nu `room_heat_surplus` separat från hydronisk `heat_in_flight`; rumsöverskott decayar över ca 8h och ger tidigare negativ offset/REST när huset redan är varmt
  - GM-controller blockerar BOOST även när rummen bär värmeöverskott trots `heat_in_flight=0`, och cappar aggressiv RUN-återhämtning till GM-bank -250 när zonerna ligger vid/över komfortgolv
  - Ingen DB-migration, inga nya beroenden och inga safety limits ändrade
  - Lokal verifiering: `venv/bin/python -m pytest -q` passerar (40 passed); `py_compile` passerar för comfort_profile, smart_planner, optimizer och gm_controller
  - Ej deployad/restartad i denna session; kräver RPi-test och kontrollerad deploy innan produktionsdrift
  - Implementerat fördröjningskompensation i optimizer/planner/GM-controller: `heat_in_flight`, lead-shedding inför kväll/natt, BOOST-blockering vid restvärme och current-hour correction mot nästa planrad
  - Ingen DB-migration och inga safety limits ändrade; ny diagnostik går till logg (`lag_state`, `lag_adjustment`, `heat_in_flight`)
  - Lokal verifiering: full pytest-svit passerar (34 passed)
  - RPi-verifiering före restart: riktade tester passerar (24 passed), DB quick_check=ok och huvudtjänster active
  - Smart planner kördes manuellt 2026-05-11 13:32 CEST: `lag_state heat_in_flight=0.02C`, plan med REST 1h, RUN 22h och BOOST 1h
  - `nibe-gm-controller` restartades 2026-05-11 13:33 CEST; första 3 ticks loggade lag_state, höll REST/WARM_OVERRIDE_DOWNSTAIRS, bank kvar 200 och inga failed systemd-units
  - RPi-backup före deploy: `/tmp/nibe_delay_deploy_20260511`
  - Added `workspace-governance`, `nibe-autotuner`, `security-best-practices`, and `security-threat-model` to Available Codex Skills
  - Created `/home/peccz/.codex/skills/nibe-autotuner/SKILL.md` for reusable Nibe F730 optimizer, GM safety, DB, dashboard, and deploy workflow guidance
  - Added `agents/openai.yaml` metadata for the `nibe-autotuner` skill
  - Driftkontroll 2026-05-07: DB på RPi är frisk (journal_mode=wal, quick_check=ok) och huvudtjänsterna är active
  - RPi kör senare commits än lokal HEAD (bl.a. fysik-/konfigkalibrering) och har mycket smutsig arbetskatalog; livebeteende analyserades därför primärt via DB och journal
  - HA/IKEA-zonsensorerna är unavailable i Home Assistant sedan ca 2026-05-07 00:54 UTC; data_logger får därför inga nya HA_TEMP_DOWNSTAIRS/HA_TEMP_DEXTER-värden
  - Senaste zonvärden i DB vid kontroll var ca 141 min gamla, medan myUplink/BT50/BT1/väder fortfarande uppdaterades
  - Smart_planner genererar nästan bara RUN/offset 0-positivt; de senaste planerna saknar REST eftersom Pass 2 kräver att hela horisonten håller target_indoor_temp_max=22.0 och target_radiator_temp=21.0, inte bara komfortgolvet
  - VV pre-heat blockerar dessutom ofta 8-11 timmar per 24h från reduktion, eftersom hot_water_usage har många timmar med >=2 historiska observationer
  - Kritisk regulatorbugg hittad: WARM_OVERRIDE tvingade REST/GM=100 men GM-banken fortsatte bygga negativ skuld mot target_supply; när HA-zonerna blev stale släppte warmoverride och regulatorn skrev -350 från en skuld nära -2000
  - Lokal fix implementerad i gm_controller: vid WARM_OVERRIDE ackumuleras ingen negativ GM-skuld och bank lyfts minst till 100; regressionstest tillagt
  - Lokal verifiering: pytest 16 passed; inga produktionsfiler deployade och ingen service restartad i denna felsökningsrunda
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
  - Följ upp V16 active efter 12-24h: övervärmetid, REST/BOOST-fördelning, morgonkomfort, warmoverride/BASTU-ticks och om HA fallback fortsätter dominera
  - HA/IKEA-zonsensorerna är fortfarande huvudrisk; V16 kör konservativt på BT50/gap-fallback men primär zonfeedback bör repareras
  - Huset är fortfarande för varmt trots V15 active: åtgärda övervärmeläge och natt-BOOST innan ytterligare prisoptimering prioriteras
  - HA/IKEA-zonsensorerna är stale igen från 2026-06-05 19:03 UTC; primär zonfeedback behöver repareras eller fallback-logiken göras striktare
  - Current V15-plan kan BOOST:a nattetid när framtida priser saknas/faller tillbaka till 1.0; blockera sådan BOOST när aktuell/fallbackad zon ligger över övre komfortband
  - Följ upp V15 active efter första natten: Dexter-min, nedervåningsmin, övervärmetid, REST/BOOST-fördelning, warmoverride-ticks och om morgonkomforten håller
  - Vädringsskyddet är deployat och körs i GM-controller; följ upp 12-24h att det inte ger falska vädringshändelser och att riktig lokal vädring blockerar BOOST/recovery
  - V15 active path är deployad men inte aktiverad; `PLANNER_ENGINE=v15_active` får först sättas efter shadow-loggar/backtest visar bättre komfort, mindre övervärme och rimlig prisstyrning än V14
  - Backtest bör inkludera Dexter-fönsterhändelsen 2026-05-15 22:00 till 2026-05-16 09:00 och minst ett syntetiskt nedervåningsvädringsfall innan aktiv V15-planwrite
  - Följ upp efter 12-24h om deployen minskar warmoverride-ticks, Dexter-övertemperatur och kvälls-/nattövervärme utan morgonundershoot
  - Live-planen skrivs fortfarande av V14; V15 är endast skuggmodell/backtest tills zonkonflikten är bättre hanterad
  - `logrotate.service` är failed på RPi och bör felsökas separat
  - Dexter-övertemperatur är aktuell huvudrisk för komfort: senaste dygnets avg 21.95°C och max 23.10°C trots REST/warmoverride
  - V15 backtest visar kvarvarande zonkonflikt: över-upper tid kommer ofta av varm nedervåning samtidigt som Dexter ligger nära golv; detta måste hanteras innan V15 aktiveras live
  - V15 är endast skuggmodell tills loggar/backtest visar att den slår V14 på morgonkomfort, kvällssänkning, REST-andel och prisviktning utan att öka undershoot
  - Nästa steg är historisk backtest av V14 vs V15 över minst 2026-04-14 till 2026-05-07 och därefter beslut om V15 ska få skriva `planned_heating_schedule`
  - Om V15 aktiveras live ska rollout ske som produktions-/säkerhetsändring med RPi-riktade tester, manuell smart_planner-körning och första GM-ticks-verifiering
  - Deploya 2026-05-13-fixen innan nästa natt om morgonkomfort ska förbättras; kräver RPi-riktade tester, smart_planner manuell körning och första GM-ticks-verifiering
  - Deploya och verifiera den lokalt implementerade pris-/stegsvarsmedvetna sovstyrningen på RPi efter riktade RPi-tester; följ första planner-run och första 3 GM-ticks
  - Följ upp efter 24h om BOOST före 05:00 försvinner, negativ offset flyttas till dyra kvällstimmar, nattövertemperatur minskar och morgongolv hålls
  - Följ upp 2026-05-12 om fördröjningskompensationen minskar nattlig övertemperatur, morgonundershoot, warmoverride-ticks och BOOST efter hög framledning
  - HA/IKEA-sensorerna har varit återkommande svaga/unavailable; systemet har fallback men primär zonfeedback behöver fortsatt bevakas
  - VV pre-heat kan fortfarande blockera REST vid enstaka timmar; följ upp om mönstret behöver ytterligare recency-filter
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
| 2026-06-06 | V16 robust styrlogik implementerad lokalt: strikt komfort/övervärme/pris-prioritet, `PLANNER_ENGINE=v16_active`, V16 i backtestrapporten och full pytest 61 passed; ej deployad |
| 2026-06-06 | V15 active drift utvärderad: tekniskt stabilt och billigare än V14 i journal, men kraftig övervärme kvarstår; senaste 7d Dexter över max 100%, GM helt safety/warmoverride/BASTU-dominerad, HA-zoner stale igen |
| 2026-05-19 | V15 active aktiverad på RPi: `.env` backupad, `PLANNER_ENGINE=v15_active`, manuell planner skrev V15-plan 8 REST/12 RUN/4 BOOST med min_dexter 20.07°C; första GM-ticks stabila REST/GM=100/bank=200 och 0 failed units |
| 2026-05-19 | V15 Dexter hard-floor fix deployad i shadow: Dexter-min klampas till 20.0°C utan vädring, lokal full pytest 56 passed, RPi riktade tester 28 passed, ny shadow-körning min_dexter=20.04°C och weighted_price 1.688 vs V14 1.729 |
| 2026-05-19 | V15-shadow utvärderad efter deploy: inga fel/vädringshändelser, GM warmoverride stabilt GM=100/bank=200, V15 lägre viktat pris än V14 men simulerar Dexter-min 19.84°C och hålls därför inaktiv |
| 2026-05-19 | Vädringsskydd och `PLANNER_ENGINE` deployade riktat till RPi i `v15_shadow`; RPi temp/live tester 27 passed, py_compile OK, smart_planner manuell körning `engine=v14`, gm_controller restartad och första tick GM=100/bank=200 |
| 2026-05-16 | Lokalt vädringsskydd och V15-aktiveringsflagga implementerade: temperaturbaserad `ventilation_event` för floor/Dexter, V15 recovery-cap, GM BOOST/Dexter-override-dämpning och `PLANNER_ENGINE`; full pytest 55 passed, ej deployad |
| 2026-05-15 | Riktad RPi-deploy genomförd av sleep/morning/room_heat_surplus/V15-shadow/backtest-filer; RPi py_compile + riktade tester 37 passed; smart_planner manuell körning loggade v15_shadow; gm_controller restartad och första tre ticks stabila med GM=100/bank=200 |
| 2026-05-15 | Live-drift utvärderad read-only: tjänster active, DB ok, HA-zoner friska, men produktion kör äldre V14 utan lokala V15-/room_heat_surplus-ändringar; senaste 24h är warmoverride-dominerat och Dexter för varm |
| 2026-05-14 | Read-only V14-vs-V15-backtest tillagt: 48 fönster på senaste lokala RPi-kopian visar V15 tar bort simulerad undershoot men kvar har zonkonflikt där Dexter nära golv driver värme trots varm nedervåning; pytest 47 passed |
| 2026-05-14 | V15-skuggplanner implementerad lokalt: samlad zon-/tröghetsmodell med vind, sol, shunt/radiatorrespons och skugglogg från smart_planner; V15 skriver inte DB-plan/GM; pytest 46 passed och py_compile passerar |
| 2026-05-13 | Kall morgon analyserad: `heat_in_flight` fick maskera morgongolv i optimizer Pass 1; lokal fix gör komfortgolvskontroll utan residual heat credit, regressionstest tillagt, lokal pytest 40 passed, ej deployad |
| 2026-05-12 | Lokal pris-/stegsvarsmedveten sovstyrning implementerad: evening_preshed, room_heat_surplus, striktare natt-BOOST, GM BOOST-blockering vid rumsöverskott och recovery-cap; lokal pytest 40 passed, ej deployad |
| 2026-05-11 | Fördröjningskompenserad styrning implementerad och deployad: heat_in_flight, lead-shedding, BOOST-blockering vid restvärme och GM current-hour correction; lokal pytest 34 passed, RPi riktade tester 24 passed, första 3 live-ticks stabila |
| 2026-05-07 | Felsökning av upplevt trasig optimering: HA-zonsensorer unavailable, planner genererar nästan bara RUN, VV pre-heat blockerar många timmar och WARM_OVERRIDE byggde negativ GM-skuld; lokal gm_controller-fix + test skapad, pytest 16 passed, ej deployad |
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
| 2026-06-06 | V16 ska vara en separat robust live-styrväg (`PLANNER_ENGINE=v16_active`) där komfort/safety prioriteras före övervärme-shedding och prisoptimering sist; pumpens 13°C/8h-värmespärr används inte som styrvillkor | V15 var tekniskt stabil och billigare än V14 men missade komfortmålet åt varma hållet. Robustheten kräver en tydlig huvudpolicy som inte låter lågt pris eller recovery skapa BOOST/RUN när huset redan är varmt. Pumpens egen spärr ska vara backup och höjas i pumpen om den stör styrningen. |
| 2026-05-19 | Riktad RPi-sync används för vädringsskyddet i stället för `deploy_v4.sh` | Lokal och RPi-arbetskatalog är smutsiga med många orelaterade ändringar. Ett brett deployflöde riskerar att blanda in oavsiktliga filer; därför synkades endast berörda styr-/testfiler och V15 ligger fortsatt i `v15_shadow`. |
| 2026-05-16 | Lokal snabb zon-dipp ska behandlas som vädringsstörning i 2h innan den får driva aggressiv recovery | Dexter-fönsterhändelsen 2026-05-15 visade att en lokal vädring kan få plannern att BOOST:a hela huset i timmar och skapa övervärme. Eftersom det saknas fönsterkontaktsensorer används temperaturförlopp relativt andra zoner/BT50; kritiskt låg temperatur bypassar skyddet. |
| 2026-05-16 | V15 får aktiveras med explicit `PLANNER_ENGINE=v15_active`, men default ska vara `v15_shadow` | V15 behöver en kontrollerad rollout där V14 kan fortsätta vara fallback. Aktiv planwrite är produktions-/säkerhetsbeteende och ska kräva explicit konfigändring, RPi-test och verifiering av första GM-ticks. |
| 2026-05-14 | V15-backtest ska rapportera undvikbar övervärme separat från zonkonflikt | Total tid över övre band kan vara missvisande när nedervåningen är varm men Dexter ligger nära komfortgolvet. Då är problemet inte bara "sänk mer", utan att få mer radiator/Dexter-effekt utan att ladda golvzonen. |
| 2026-05-14 | En komplett V15-styrlogik ska först köras som skuggmodell innan den får ersätta V14-planen | Tidigare logik blev krånglig eftersom hotfixar för pris, warmoverride, fördröjning och komfort lades i flera lager. V15 samlar modellen, men eftersom projektet styr verklig värme ska den först jämföras mot V14 i logg/backtest utan DB-planwrite eller GM-effekt. |
| 2026-05-13 | `heat_in_flight` får inte räknas som komfortgolvskredit i optimizer Pass 1 | Morgonen 2026-05-13 blev kall trots planerad RUN 0 eftersom residual värme i systemet fick plannern att tro att morgongolvet skulle hållas. Restvärme är användbar för att blockera onödig BOOST och modellera övervärmerisk, men ska inte maskera faktisk rumstemperatur vid minimumkomfort. |
| 2026-05-12 | Prisoptimering ska vara underordnad sömnprofil och husets stegsvar: billig nattvärme före 05:00 är normalt förbjuden, och kvällsövervärme ska börja shedas från 17:00 via `room_heat_surplus` | Driftanalys visade att optimizer träffade billiga priser delvis men skapade BOOST mitt i sovfönstret och behövde ibland dyr morgonåterhämtning. Husets praktiska stegsvar är 8-12h, så styrningen måste flytta kyl-/värmebeslut tidigare än timpriset ensamt indikerar. |
| 2026-05-11 | Planner och GM-controller ska kompensera explicit för värmetröghet via loggbaserad `heat_in_flight` och planålders-/nästa-timme-korrigering | Driftanalys visade att timplanner, Nibes framledningsrespons och husets termiska massa gav 1-3 timmars styrfördröjning. Utan lagkompensation blev warmoverride praktisk huvudregulator och morgonboost gav eftervärme in på dagen. |
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
| 2026-05-10 | Added project-specific Codex skill `nibe-autotuner` | Repeated optimizer, GM controller, DB, dashboard, deploy, and safety workflows should be reusable scaffolding instead of re-explained in prompts |

---

*DNA.md är ett levande dokument. Uppdatera det. Låt det inte drifta från verkligheten.*
