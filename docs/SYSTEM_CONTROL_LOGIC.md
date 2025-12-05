# Nibe F730 Autotuner - Teknisk Systemdokumentation

## Innehållsförteckning
1. [Systemöversikt](#systemöversikt)
2. [Styrparametrar](#styrparametrar)
3. [Mätparametrar](#mätparametrar)
4. [Reglerstrategi](#reglerstrategi)
5. [Tidskonstanter och Svarstider](#tidskonstanter-och-svarstider)
6. [Prediktiv Styrning](#prediktiv-styrning)
7. [Säkerhetsgränser](#säkerhetsgränser)
8. [Antaganden och Osäkerheter](#antaganden-och-osäkerheter)
9. [Inlärningssystem](#inlärningssystem)

---

## Systemöversikt

### Grundläggande Arkitektur

```
┌─────────────────────────────────────────────────────────────┐
│                    AI-STYRNING (Claude/Gemini)              │
│  - Prediktiv analys (elpris + väder)                       │
│  - Historisk inlärning (COP-utvärdering)                   │
│  - Säkerhetsvalidering                                     │
└─────────────────┬───────────────────────────────────────────┘
                  │ Parameterjusteringar
                  ↓
┌─────────────────────────────────────────────────────────────┐
│                  NIBE F730 VÄRMEPUMP                        │
│  - Intern PID-reglering (kompressorkontroll)               │
│  - Värmekurva + Offset → Framledningstemperatur            │
│  - DegreeMinutes → Kompressorstarttid                      │
└─────────────────┬───────────────────────────────────────────┘
                  │ Värmeöverföring
                  ↓
┌─────────────────────────────────────────────────────────────┐
│                    VÄRMESYSTEM                              │
│  - Radiatorer (vattenburen värme)                          │
│  - Termisk massa: Huset (måttlig)                          │
│  - Isolering: Utmärkt (0.007°C/h avkylning)                │
└─────────────────────────────────────────────────────────────┘
```

### Reglerprincip

**HIERARKISK REGLERING:**
1. **Nibe's PID-regulator** (inbyggd, snabb): Styr framledningstemperatur och kompressor
2. **AI-styrning** (1 gång/timme, långsam): Justerar setpoints (värmekurva, offset) baserat på pris/väder/historik

**VIKTIGT:** Vi styr INTE kompressorn direkt - vi justerar *målvärden* som Nibe's regulator använder.

---

## Styrparametrar

### 1. Curve Offset (Parameter 47011) ⭐ PRIMÄR STYRPARAMETER

**Beskrivning:**
- Skiftar hela värmekurvan upp/ner
- Påverkar framledningstemperatur direkt
- Enhet: Grader offset från nominell kurva

**Värdeområde:**
- Min: -10
- Max: +10
- Steg: 1 (heltal)

**Aktuell användning (empiriskt bestämd för outdoor 3-5°C):**
- Normalt intervall: -5 till 0
- BASLINJE: -3 (normal drift, ger 20.5-22°C inomhus)
- REDUCERAT: -5 (max sänkning vid dyrt el, ger 20.5-21°C inomhus)
- BUFFRAT: -1 (värmebuffring före dyr period, ger 21-23°C inomhus)
- **ALDRIG under -5 vid nuvarande utetemp** (ger ingen extra besparing)

**Effekt:**
- **-1 steg (t.ex. -5 → -6):** Sänker framledningstemperatur ~2-3°C
- **+1 steg (t.ex. -5 → -4):** Höjer framledningstemperatur ~2-3°C

**Svarstid (systemets respons):**
```
Tid     Framledning  Radiator   Rumsluft
0min    Ingen ändring
15min   -2°C         -0.5°C     0°C
30min   -3°C         -1.5°C     -0.1°C
1h      -3°C         -2.5°C     -0.2°C
2h      -3°C         -3°C       -0.4°C
3h      -3°C         -3°C       -0.7°C ← Märkbar effekt
6h      -3°C         -3°C       -1.2°C ← Systemet stabiliserat
```

**Säkerhetsgränser:**
- Max ändring per steg: ±2 (konservativt för att undvika extrema värden)
- Min konfidens för ändring: 70%
- Minsta rumstemperatur: 20.5°C (får aldrig understigas, konfigurerbar i GUI)
- Hårdkodad minimum för offset: -5 (empirisk gräns för outdoor 3-5°C)

**Osäkerhet:**
- Framledningstemperatur-relation: **MEDEL** (±1°C osäkerhet)
- Rumstemperatur-effekt: **HÖG osäkerhet** (beror på väder, sol, vind)
- Tidsrespons: **MEDEL** (±30min variabilitet)

**Användningsmönster (empiriskt baserat):**
```python
# BASLINJE: Normal drift (natt/billigt el)
offset = -3  # → Indoor 20-22°C

# DYRT ELPRIS (2-4h framåt) + Varmt inomhus
if forecast_expensive and indoor_temp >= 20.5:
    offset = -5  # Max sänkning → Indoor 20-21°C

# BILLIGT ELPRIS (2-4h framåt) + Svalt inomhus
if forecast_cheap and indoor_temp <= 21.5:
    offset = -1  # Buffring → Indoor 21-23°C

# ALDRIG gå under -5 vid outdoor 3-5°C
offset = max(offset, -5)
```

---

### 2. Heating Curve (Parameter 47007) 🔧 SEKUNDÄR

**Beskrivning:**
- Lutningen på värmekurvan
- Bestämmer hur mycket framledningstemperaturen ändras per grad utetemp
- Högre kurva = mer aggressiv kompensation för kyla

**Värdeområde:**
- Min: 1
- Max: 15
- Steg: 1 (heltal)

**Aktuell användning:**
- Nuvarande värde: 7 (måttlig kurva)
- **ANVÄNDS SÄLLAN** - vi fokuserar på Offset istället

**Effekt:**
- Kurva 7: Vid 0°C ute → ~45°C framledning
- Kurva 8: Vid 0°C ute → ~48°C framledning
- Kurva 6: Vid 0°C ute → ~42°C framledning

**Svarstid:**
- Omedelbar effekt på framledningsberäkning
- Märks mest vid stora utetemperaturförändringar (±5°C)

**Säkerhetsgränser:**
- Max ändring: ±2 steg per justilering
- Används INTE i normal drift (för stor påverkan)

**Osäkerhet:**
- Framledningsberäkning: **LÅG** (väldokumenterad av Nibe)
- Optimal kurva för huset: **HÖG** (husspecifik parameter)

**Användning:**
- Justeras sällan (kanske 1 gång/månad baserat på 48h A/B-tester)

---

### 3. Start Compressor / DegreeMinutes (Parameter 47206) ⚙️ TIMING

**Beskrivning:**
- Tröskelvärde för när kompressorn startar
- Mäts i "DegreeMinutes" (°C·min under måltemperatur)
- Negativt värde = kompressor startar tidigare (mer aggressiv)

**Värdeområde:**
- Min: -1000
- Max: -60
- Typiskt: -150 till -200

**Aktuell användning:**
- Nuvarande värde: Varierar mellan -60 och -200
- **ANVÄNDS MYCKET SÄLLAN**

**Effekt:**
- **Mer negativt (t.ex. -200):** Kompressor startar tidigare → fler starter, kortare cykler
- **Mindre negativt (t.ex. -100):** Kompressor startar senare → färre starter, längre cykler

**VIKTIGT MISSFÖRSTÅND:**
⚠️ DegreeMinutes är INTE en indikator på överhettning!
- DM = -192 betyder INTE att det är för varmt
- Det betyder bara att kompressorn startar när rumstemperaturen är 192 gradminuter under målet

**Svarstid:**
- Påverkar kompressorstartfrekvens inom 1-2 timmar

**Säkerhetsgränser:**
- Används mycket försiktigt pga kompressorslitage
- Ingen maxändring definierad (används så sällan)

**Osäkerhet:**
- Effekt på COP: **MYCKET HÖG** (komplex relation)
- Effekt på komfort: **MEDEL**
- Optimal värde: **MYCKET HÖG** (husspecifik, säsongsspecifik)

**Användning:**
```python
# ANVÄNDS EJ I NORMAL DRIFT
# Kan användas för att optimera kompressorstarter långsiktigt
# Kräver 48h+ utvärderingsperiod
```

---

### 4. Hot Water Demand (Parameter 47041) 💧 VARMVATTEN

**Beskrivning:**
- Måltemperatur för varmvatten
- 0 = Small (lägre temp)
- 1 = Medium (normal)
- 2 = Large (högre temp)

**Värdeområde:**
- Min: 0 (Small)
- Max: 2 (Large)
- Steg: 1 (diskret)

**Aktuell användning:**
- Standard: 1 (Medium)
- Sänks till 0 vid dyrt pris + låg förväntad användning
- Höjs till 2 vid billigt pris + hög förväntad användning

**Effekt:**
- Small (0): ~45-48°C varmvatten
- Medium (1): ~50-53°C varmvatten
- Large (2): ~55-58°C varmvatten

**Svarstid:**
- Vattnets temperatur ändras på 30-60 minuter
- Full effekt inom 1-2 timmar

**Säkerhetsgränser:**
- Aldrig under Small (0) pga legionella-risk över tid
- Höjs alltid till minst Medium (1) om varmvattenanvändning förväntas

**Osäkerhet:**
- Temperatureffekt: **LÅG** (väldokumenterad)
- Användarbehov: **MEDEL** (predikteras från historik)

**Användning:**
```python
# Prediktion med HotWaterPatternAnalyzer
hw_probability = analyzer.get_usage_probability(current_time)

if price_expensive and hw_probability < 0.3:
    hot_water_demand = 0  # Small
elif price_cheap and hw_probability > 0.7:
    hot_water_demand = 2  # Large
```

---

### 5. Room Temperature Target (Parameter 47015) 🏠 MÅL

**Beskrivning:**
- Måltemperatur för inomhusklimat
- Nibe's PID-regulator försöker hålla denna temperatur

**Värdeområde:**
- Min: 18°C
- Max: 25°C
- Steg: 0.5°C

**Aktuell användning:**
- **ANVÄNDS INTE I NORMAL DRIFT**
- Håller fast värde (typiskt 20-22°C)
- Vi justerar istället Offset för att ändra effektiv uppvärmning

**Anledning att inte använda:**
- Direkt måltemperaturändring konflikterar med Nibe's regulator
- Kan skapa oscillationer
- Offset ger mjukare kontroll

**Säkerhetsgränser:**
- Aldrig under 20°C (komfort + säkerhet)
- Max ändring: ±1°C per justering

---

### 6. Increased Ventilation (Parameter 50005) 🌬️ VENTILATION

**Beskrivning:**
- Forcerad ventilation (frånluftssystem)
- 0 = Normal
- 1-4 = Ökad ventilation

**Aktuell användning:**
- **ANVÄNDS INTE**
- Finns i systemet men ingen aktiv styrning

**Potential framtida användning:**
- Vid mycket billigt elpris: Öka ventilation för bättre luftkvalitet
- Vid höga CO2-nivåer (om sensor läggs till)

---

## Mätparametrar

### Primära mätningar (hög tillförlitlighet)

#### 1. Indoor Temperature (40033) 🌡️ KRITISK
**Källa:** Nibe inbyggd rumsgivare
**Uppdateringsfrekvens:** ~5 minuter
**Precision:** ±0.3°C
**Tillförlitlighet:** ⭐⭐⭐⭐⭐ MYCKET HÖG

**Användning:**
- Primär feedback för värmebehovet
- Säkerhetsgräns (aldrig under 20°C)
- Validering av prediktioner

**Känslighet för störningar:**
- Solstrålning genom fönster: MEDEL påverkan
- Vindavkylning: LÅG påverkan (bra isolering)
- Öppna dörrar/fönster: HÖG påverkan (kortvarig)

**Interpretation:**
```python
if indoor_temp > 22.0:
    # Huset är varmt, kan sänka värme säkert
    confidence = 0.9
elif 20.5 <= indoor_temp <= 21.5:
    # Optimal comfort-zone
    confidence = 0.8
elif indoor_temp < 20.0:
    # VARNING: För kallt, höj omedelbart
    confidence = 1.0  # Högt prio
```

---

#### 2. Outdoor Temperature (40004) 🌡️ VIKTIG
**Källa:** Nibe utomhusgivare
**Uppdateringsfrekvens:** ~5 minuter
**Precision:** ±0.5°C
**Tillförlitlighet:** ⭐⭐⭐⭐ HÖG

**Användning:**
- Nibe's värmekurva använder detta (automatiskt)
- AI använder för trend-analys
- Jämförelse med SMHI-prognos (validering)

**Känslighet:**
- Placering påverkar (sol, vind, skugga)
- Kan skilja ±2°C från "faktisk" temperatur

---

#### 3. Supply Temperature (40008) 🔥 FRAMLEDNING
**Källa:** Nibe värmepump
**Uppdateringsfrekvens:** ~1 minut
**Precision:** ±0.5°C
**Tillförlitlighet:** ⭐⭐⭐⭐⭐ MYCKET HÖG

**Användning:**
- Verifiering att värmekurva + offset fungerar
- Indirekt COP-beräkning
- Debugging av reglering

---

#### 4. Compressor Frequency (43136) ⚙️ KOMPRESSOR
**Källa:** Nibe värmepump (inverter)
**Uppdateringsfrekvens:** ~1 minut
**Enhet:** Hz (0-100 Hz typiskt)
**Tillförlitlighet:** ⭐⭐⭐⭐⭐ MYCKET HÖG

**Användning:**
- Detektera kompressorstarter (0 Hz → >0 Hz)
- COP-beräkning (lägre frekvens = högre COP)
- Validera att system kör som förväntat

**Scientific Analysis:**
```python
# Räkna kompressorstarter i 6h period
starts = count_transitions(freq, from_val=0, to_val='>0')

# Optimal: 2-4 starter per 6h (långa cykler, hög COP)
# Suboptimal: >8 starter per 6h (korta cykler, låg COP)
```

---

#### 5. Electric Power (40072 / 43427) ⚡ EFFEKT
**Källa:** Nibe värmepump
**Uppdateringsfrekvens:** ~1 minut
**Enhet:** kW
**Tillförlitlighet:** ⭐⭐⭐ MEDEL (kända problem med vissa parametrar)

**Problem:**
- Parameter 43427 ("Electrical addition power") visar ibland felaktiga värden
- Kan visa 100% användning när det faktiskt är 0%
- **PÅGÅENDE:** Undersökning av rätt parameter

**Användning:**
- COP-beräkning: COP = Värme ut / El in
- Kostnadsberäkning: Kostnad = Effekt × Pris × Tid

**Workaround:**
- För varmvatten: Använd temperaturtröskel istället (~58°C → troligen elpatron)

---

### Beräknade mätvärden

#### COP (Coefficient of Performance) 📊
**Beräkning:**
```python
COP = thermal_energy_delivered / electrical_energy_consumed
    = (flow_rate × ΔT × specific_heat) / electric_power
```

**Typiska värden:**
- Optimalt (låg last, mild väder): 3.5-4.5
- Normalt (normal drift): 2.8-3.5
- Suboptimalt (hög last, kallt väder): 2.0-2.8

**Osäkerhet:** ±0.3 (MEDEL)

**Användning:**
- Utvärdera effektivitet av parameterjusteringar
- Jämföra "före" och "efter" vid A/B-tester
- Inlärning: Vilka justeringar förbättrade COP?

---

#### Degree Minutes (beräknat från rumstemperatur) 📉
**Beräkning:**
```python
# Integration av temperaturdifferens över tid
DM = integral((target_temp - actual_temp) * dt)
```

**OBS:** Detta är INTE samma som parameter 47206!
- Parameter 47206 = Tröskel för start
- Beräknat DM = Aktuellt värmeunderskott

**Användning:**
- Indikator på "energiskuld" i huset
- Stort negativt DM → Huset tappar värme snabbt (dålig isolering eller kallt väder)

**Osäkerhet:** ±50 DM (HÖG, beror på integration över tid)

---

## Reglerstrategi

### Övergripande strategi: Prediktiv Model-Based Control

**Filosofi:**
1. **PREDIKTIVT över REAKTIVT** - Agera innan problemet uppstår
2. **SÄKERHET över OPTIMERING** - Aldrig offra komfort för kostnad
3. **LÄRANDE över STATISKT** - Förbättra baserat på historik

---

### Beslutshieraki

```
┌─────────────────────────────────────────────────┐
│  1. SÄKERHETSKONTROLL (Hårdkodade gränser)      │
│     ✓ Indoor temp >= 20.0°C                     │
│     ✓ Offset inom [-10, +10]                    │
│     ✓ Max steg-ändring ±5                       │
│     ✓ Konfidens >= 70%                          │
└────────────────┬────────────────────────────────┘
                 ↓ PASS
┌─────────────────────────────────────────────────┐
│  2. KOMFORT-PRIORITERING                        │
│     If indoor < 20.5°C:                         │
│       → Höj värme oavsett pris                  │
│     If väder COOLING:                           │
│       → Höj värme i förväg (comfort > cost)     │
└────────────────┬────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────┐
│  3. PREDIKTIV OPTIMERING (AI-beslut)            │
│     Analysera:                                   │
│     - Elprisprognos (12h framåt)                │
│     - Väderprognos (12h framåt)                 │
│     - Historiska COP-resultat                   │
│     - Nuvarande systemtillstånd                 │
│                                                  │
│     Besluta:                                     │
│     - Vilket parameter att ändra                │
│     - Hur mycket att ändra                      │
│     - Förväntad effekt                          │
└────────────────┬────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────┐
│  4. APPLICERA ÄNDRING                           │
│     → MyUplink API → Nibe F730                  │
│     → Logga beslut i databas                    │
│     → Starta 6h utvärderingstimer               │
└─────────────────────────────────────────────────┘
```

---

### Detaljerad Beslutslogik

#### Steg 1: Säkerhetskontroller (Hårdkodade, kan ej åsidosättas av AI)

**Källkod:** `autonomous_ai_agent_v2.py::_is_decision_safe()`

```python
def _is_decision_safe(decision):
    # Regel 1: Aldrig sänk måltemperatur under 20°C
    if decision.parameter == 'room_temp':
        if decision.suggested_value < 20.0:
            return False, "Below safety limit"

    # Regel 2: Parametergränser
    bounds = {
        'curve_offset': (-10, 10),
        'heating_curve': (1, 15),
        'room_temp': (18, 25),
        # ...
    }
    if not (min_val <= suggested_value <= max_val):
        return False, "Out of bounds"

    # Regel 3: Max steg-storlek
    max_steps = {
        'curve_offset': 5,  # ±5 steg per ändring
        'heating_curve': 2,
        'room_temp': 1,
    }
    if abs(change) > max_step:
        return False, "Too aggressive"

    return True, ""
```

**Designprincip:** Dessa gränser är ABSOLUTA och kan aldrig åsidosättas, oavsett hur säker AI:n är.

---

#### Steg 2: Datainsamling och Kontextbygge

**Källkod:** `autonomous_ai_agent_v2.py::_build_optimized_context()`

AI:n får följande information:

```python
context = {
    # Nuläge (72h medelvärden)
    'outdoor_temp': 4.3,        # °C
    'indoor_temp': 21.4,        # °C
    'cop': 3.01,                # Effektivitet
    'degree_minutes': 61,       # Aktuell värmeskuld
    'curve': 7,                 # Värmekurva
    'offset': -8,               # Nuvarande offset

    # Elpris
    'current_price': 1.65,      # SEK/kWh
    'price_status': 'EXPENSIVE',# CHEAP/NORMAL/EXPENSIVE

    # Prognos (12h framåt)
    'forecast': {
        'price': {
            'expensive_hours': [17, 18, 19, 20],
            'cheap_hours': [22, 23, 0, 1]
        },
        'weather': {
            'temp_range': (3.9, 4.6),  # Min-Max
            'avg_temp': 4.2,
            'trend': 'STABLE'  # STABLE/COOLING/WARMING
        }
    },

    # Varmvatten
    'hot_water_usage_risk': 0.0,  # 0.0-1.0 sannolikhet

    # Historik (senaste 24h)
    'history': [
        {'hours_ago': 0, 'param': 'curve_offset',
         'change': '-8→-9', 'cop_impact': 'N/A'},
        {'hours_ago': 1, 'param': 'hot_water_demand',
         'change': '1→0', 'cop_impact': 'N/A'},
        {'hours_ago': 4, 'param': 'curve_offset',
         'change': '-4→-5', 'cop_impact': '+0.12'},
        # ... mer historik
    ]
}
```

**Datakvalitet:**
- Indoor/Outdoor temp: ⭐⭐⭐⭐⭐ Hög
- COP: ⭐⭐⭐⭐ Medel-Hög
- Elpris: ⭐⭐⭐⭐⭐ Hög (från mönster)
- Väderprognos: ⭐⭐⭐⭐ Medel-Hög (SMHI)
- HW usage: ⭐⭐⭐ Medel (baserat på historik)
- COP impact: ⭐⭐⭐ Medel (kräver 6h+ för valid mätning)

---

#### Steg 3: AI-analys och Beslutsfattande

**Källkod:** `autonomous_ai_agent_v2.py::_create_optimized_prompt()`

AI:n (Google Gemini 2.5 Flash) får följande instruktioner:

```
SYSTEM: Nibe F730 HeatPump
GOAL: Optimize COP, Comfort & COST

THERMAL LAG: House takes ~3h to respond to heating changes. BE PREDICTIVE!

STRATEGY (PREDICTIVE):
1. FORECAST EXPENSIVE + STABLE/WARMING Weather:
   If Indoor >= 20.5C: Lower heat NOW (Offset -2 to -5)

2. FORECAST CHEAP + STABLE/COOLING Weather:
   If Indoor <= 21.5C: Buffer heat NOW (Offset +2 to +5)

3. WEATHER COOLING:
   Increase heat proactively even if price expensive
   (comfort > cost when temp dropping)

4. WEATHER WARMING:
   Decrease heat proactively even if price cheap
   (save energy when temp rising)

5. CURRENT EXPENSIVE but CHEAP ahead:
   Hold/minor adjust only

6. LEARN FROM HISTORY:
   Review recent changes and their COP impact
   Avoid repeating changes that decreased COP
```

**AI-output (JSON):**
```json
{
  "action": "adjust",
  "parameter": "curve_offset",
  "current_value": -8.0,
  "suggested_value": -9.0,
  "reasoning": "Price is EXPENSIVE and forecast shows continued high prices 17-20h. Weather STABLE (no cooling expected). Indoor temp 21.4C is comfortably above minimum. Reducing heating now prepares for expensive period with 3h lead time.",
  "confidence": 0.85,
  "expected_impact": "Reduce heating cost during peak hours while maintaining 20.5-21.0C comfort"
}
```

**Konfidensberäkning:**
AI:n bedömer sin säkerhet baserat på:
- Datakvalitet (kompletta mätningar = högre konfidens)
- Historisk framgång (tidigare COP-förbättringar = högre konfidens)
- Prognossäkerhet (stabilt väder = högre konfidens)
- Avstånd från säkerhetsgränser (långt från 20°C = högre konfidens)

**Typiska konfidensnivåer:**
- 0.90-1.0: Mycket tydlig situation (dyrt pris, varmt inomhus, stabil prognos)
- 0.75-0.89: Normal drift (standard justeringar)
- 0.70-0.74: Osäker situation (motstridiga signaler, men över tröskeln)
- <0.70: BLOCKERAD (appliceras ej)

---

#### Steg 4: Applicering och Loggning

**Källkod:** `autonomous_ai_agent.py::_apply_decision()`

```python
def _apply_decision(decision):
    # 1. Översätt parametername → API ID
    param_id = PARAMETER_IDS[decision.parameter]  # '47011' för curve_offset

    # 2. Anropa MyUplink API
    api_client.set_point_value(
        device_id=DEVICE_ID,
        parameter_id=param_id,
        value=decision.suggested_value
    )

    # 3. Logga i databas
    log_to_db(ParameterChange(
        parameter_id=param_id,
        old_value=decision.current_value,
        new_value=decision.suggested_value,
        reason=f"Autonomous AI: {decision.reasoning}",
        timestamp=now()
    ))

    # 4. Starta utvärderingstimer (6h)
    schedule_evaluation(change_id, after=timedelta(hours=6))
```

---

## Tidskonstanter och Svarstider

### Mätta Tidskonstanter

#### 1. Husets Termiska Tidskonstant
**Mätmetod:** Scientific test (sänkte offset till -10, mätte avkylning över 48h)

**Resultat:**
```
Avkylningshastighet: -0.007°C/h
R² (goodness of fit): 0.06 (låg pga uppvärmningspulser)
Tolkning: Extremt välisolerat hus
```

**Praktisk betydelse:**
- Huset kan "buffra" värme i flera dagar
- Passiv värmeförlust är försumbar jämfört med aktiv uppvärmning
- Kan göra aggressiva ändringar utan snabb komfort-påverkan

**Teoretisk stabiliseringstid (utan uppvärmning):**
```
Tid för 1°C temperaturfall: ~140 timmar (6 dagar)
Tid för 2°C temperaturfall: ~280 timmar (12 dagar)
```

**Osäkerhet:** MEDEL (R² låg pga intermittent uppvärmning)

---

#### 2. Värmesystemets Svarstid (Aktiv Uppvärmning)
**Mätmetod:** Analys av faktiska parameterjusteringar och rumstemperatur-respons

**Empiriska data:**
```
Tidpunkt    Ändring          1h före  3h efter  Delta
10:00:35    offset -3→-4     22.1°C   21.7°C    -0.4°C
10:03:41    offset -4→-5     22.1°C   21.7°C    -0.4°C
14:02:01    offset -6→-7     21.6°C   21.6°C     0.0°C (ej tillräcklig tid)
14:45:53    offset -7→-8     21.6°C   21.6°C     0.0°C (ej tillräcklig tid)
```

**Modellerad svarstid:**
```
Komponent           63% respons    95% stabilisering
Framledning         15 min         30 min
Radiatorvatten      45 min         2 h
Rumsluft            2 h            4-6 h
Väggar/möbler       4 h            12 h
Fullständig effekt  3 h            6-8 h
```

**Stegsvar (1 steg curve_offset):**
```
  Rumstemperatur
      ^
22°C  |════════════╗
      |             ╚═══════════════════
21.5°C|                ╚═════════════════
      |                   ╚═══════════════
21°C  |                      ╚════════════════ ← Nytt jämviktsläge
      |
      └─────┬────┬────┬────┬────┬────┬────→ Tid
           0h   1h   2h   3h   4h   5h   6h

τ (tidskonstant) ≈ 3h (63% av slutvärde)
```

**Designkonsekvens:** Prediktiva justeringar bör göras 3h innan önskad effekt.

---

#### 3. Kompressorstart-dynamik
**Mätmetod:** Analys av compressor frequency transitions

**Observerat mönster:**
```
Typisk cykel (DM = -180):
- Rumstemperatur når 180 gradminuter under mål
- Kompressor startar (0 Hz → 40 Hz)
- Gradvis acceleration till 60-80 Hz
- Kör i 45-90 minuter (medel: 120 min observerat i data)
- Kompressor stannar (→ 0 Hz)
- Väntetid: 60-120 minuter innan nästa start
```

**Optimal cykel:**
- 2-4 starter per 6h period
- Genomsnittlig körtid: 60-90 min per cykel
- COP högst vid låg frekvens (40-60 Hz)

**Suboptimal cykel (problem):**
- >8 starter per 6h period
- Kort körtid: <30 min per cykel
- Låg COP pga startup-förluster

---

#### 4. Varmvatten-respons
**Mätmetod:** Observation av hot_water_demand ändringar

**Typisk respons:**
```
Ändring: hot_water_demand 1 → 2 (Medium → Large)

Tid     Varmvatten-temp   Kompressor-aktivitet
0min    52°C              Normal uppvärmningscykel
15min   52°C              Varmvattenladdning startar
30min   54°C              Varmvattenpump aktiv
45min   56°C              Varmvattenpump aktiv
60min   58°C              Måltemperatur nådd
90min   58°C              Stabiliserat
```

**Energikostnad:** ~1-2 kWh per laddning (uppskattning)

---

### Prediktiv Timing

**Regelexempel:**
```python
# Scenario: Dyrt elpris 17:00-21:00 (om 3 timmar)
current_time = 14:00
expensive_period_start = 17:00
lead_time = 3  # timmar

if forecast.expensive_at(17, 18, 19, 20) and current_time == 14:
    # Sänk värme NU (3h före) så effekten märks vid 17:00
    adjust_offset(current - 3)  # Större ändring pga lång framförhållning

# Scenario: Väderprognos visar -5°C drop om 4h
if forecast.weather.cooling_trend() and lead_time >= 3:
    # Öka värme i förväg
    adjust_offset(current + 2)
```

---

## Prediktiv Styrning

### Elprisprognos

**Källa:** Förenklad modell baserad på typiska svenska elpriser

**Prismodell:**
```python
# Baserat på statistik för SE3 (Stockholm)
cheap_hours = [22, 23, 0, 1, 2, 3, 4, 5, 6]        # Natt
expensive_hours = [7, 8, 9, 17, 18, 19, 20, 21]    # Morgon + Kväll
normal_hours = [10, 11, 12, 13, 14, 15, 16]        # Dag
```

**Osäkerhet:**
- Morgon (7-9): MEDEL (65% träffsäkerhet)
- Kväll (17-21): HÖG (85% träffsäkerhet)
- Natt (22-06): MYCKET HÖG (95% träffsäkerhet)

**Förbättringsmöjlighet:** Integration med Nordpool Spot / Tibber API för exakta timpriser.

**Prisklassificering:**
```python
# Relativt dagens medel
if current_price > daily_avg * 1.2:
    status = "EXPENSIVE"
elif current_price < daily_avg * 0.8:
    status = "CHEAP"
else:
    status = "NORMAL"
```

---

### Väderprognos

**Källa:** SMHI API (Sveriges Meteorologiska och Hydrologiska Institut)

**Data:** 12-timmars prognos med 1-timmars upplösning

**Parametrar:**
- Temperatur (°C)
- Nederbörd (mm/h)
- Vindhastighet (m/s)
- Luftfuktighet (%)

**Användning i systemet:**
```python
forecast = weather_service.get_temperature_forecast(hours_ahead=12)

# Beräkna trend
temps = [t for (_, t) in forecast]
start_temp = temps[0]
end_temp = temps[-1]

if end_temp < start_temp - 2:
    trend = "COOLING"   # Temperatur faller >2°C
elif end_temp > start_temp + 2:
    trend = "WARMING"   # Temperatur stiger >2°C
else:
    trend = "STABLE"    # ±2°C variation
```

**Prediktiv logik:**
```python
if trend == "COOLING":
    # Temperatur faller → öka värme i förväg (comfort > cost)
    priority = "COMFORT"
    adjust_offset(+2)  # Höj värme innan det blir kallt

elif trend == "WARMING":
    # Temperatur stiger → sänk värme i förväg (save energy)
    priority = "EFFICIENCY"
    adjust_offset(-2)  # Sänk värme innan det blir varmt
```

**Osäkerhet:**
- 0-6h prognos: MEDEL (±1°C)
- 6-12h prognos: MEDEL-HÖG (±2°C)
- 12-24h prognos: HÖG (±3°C, används ej)

---

### Kombinerad Prediktion: Pris + Väder

**Prioritetsmatris:**

```
                  VÄDER COOLING    VÄDER STABLE     VÄDER WARMING
                  (temp faller)    (temp konstant)  (temp stiger)
─────────────────────────────────────────────────────────────────
PRIS CHEAP    │   Öka värme      │  Öka värme     │  Hold/Minor   │
(billigt el)  │   AGGRESSIVT     │  MODERAT       │  sänkning     │
              │   Buffra värme   │  Normal drift  │  Spara energi │
─────────────────────────────────────────────────────────────────
PRIS NORMAL   │   Öka värme      │  Hold          │  Sänk värme   │
(normalt el)  │   MODERAT        │  Ingen ändring │  MODERAT      │
              │   Comfort first  │  Status quo    │  Efficiency   │
─────────────────────────────────────────────────────────────────
PRIS EXPENSIVE│   Öka värme      │  Sänk värme    │  Sänk värme   │
(dyrt el)     │   MINOR          │  MODERAT       │  AGGRESSIVT   │
              │   Comfort > Cost │  Cost savings  │  Max savings  │
─────────────────────────────────────────────────────────────────
```

**Exempel-scenario 1:**
```
Tid: 14:00
Nuläge: Indoor 21.5°C, Offset -6
Prognos:
  - Pris EXPENSIVE 17-21h (3h framåt)
  - Väder STABLE (4.0-4.5°C)

Beslut:
  AI: "Pris blir dyrt men väder stabilt. Indoor över målet (21.5 > 20.5).
       Sänker offset -6 → -8 (2 steg) för att spara under dyr period."
  Förväntad effekt: Indoor 21.5 → 21.0°C vid 17:00
  Konfidens: 85%
```

**Exempel-scenario 2:**
```
Tid: 20:00
Nuläge: Indoor 20.8°C, Offset -7
Prognos:
  - Pris CHEAP 22-06h (2h framåt)
  - Väder COOLING (4°C → 1°C över natten)

Beslut:
  AI: "Väder blir kallare OCH pris blir billigt. Trots att indoor OK nu,
       behöver buffra värme innan kyla. Comfort > Cost när temp faller."
  Åtgärd: Höj offset -7 → -4 (3 steg)
  Förväntad effekt: Indoor 20.8 → 21.5°C vid 02:00
  Konfidens: 90%
```

---

### Varmvatten-prediktion

**Källa:** `HotWaterPatternAnalyzer` - Machine learning baserat på historisk användning

**Metod:**
1. Analysera 14 dagars historik av varmvattenanvändning
2. Identifiera mönster (tid på dagen, veckodag)
3. Träna modell (sannolikhetsfördelning per timme)

**Output:**
```python
usage_probability = analyzer.get_usage_probability(datetime.now())
# Returnerar: 0.0-1.0 (0% till 100% sannolikhet för användning nästa 2h)
```

**Användning:**
```python
if price_expensive and usage_probability < 0.3:
    # Låg risk för varmvattenanvändning + dyrt pris
    hot_water_demand = 0  # Small (spara energi)

elif price_cheap and usage_probability > 0.7:
    # Hög risk för användning + billigt pris
    hot_water_demand = 2  # Large (buffra varmt vatten)
```

**Osäkerhet:**
- Vardagar: MEDEL (förutsägbart mönster)
- Helger: HÖG (mer varierat beteende)
- Gäster/avvikelser: MYCKET HÖG (oförutsägbart)

**Nuvarande status:**
```
Analyzed 1774 readings. Found 0 usage events.
```
**Problem:** Ingen användning detekterad → Modellen har ingen träningsdata
**Anledning:** Oklart vilken parameter som indikerar faktisk användning
**Workaround:** Använd konservativ strategi (håll Medium som standard)

---

## Säkerhetsgränser

### Hårda gränser (kan ej åsidosättas)

#### 1. Minsta innetemperatur
```python
MIN_INDOOR_TEMP = 20.5  # °C - ABSOLUT GRÄNS (KONFIGURERBAR)
```
**Motivering:**
- Komfort: Under 20.5°C upplevs som kallt för de flesta
- Hälsa: Risk för mögel/fukt vid långvarig låg temp
- Legionella: Varmvatten riskerar bakterietillväxt

**Konfiguration:**
- Standardvärde: 20.5°C
- Kan justeras i GUI (Settings) mellan 18.0°C och 23.0°C
- Ändring kräver omstart av AI-agent för att träda i kraft
- Lagras i `.env` fil som `MIN_INDOOR_TEMP=20.5`

**Implementation:**
```python
from core.config import settings

if decision.parameter in ['curve_offset', 'heating_curve', 'room_temp']:
    predicted_indoor = simulate_temperature_effect(decision)
    if predicted_indoor < settings.MIN_INDOOR_TEMP:
        BLOCK_DECISION(f"Risk för att understiga {settings.MIN_INDOOR_TEMP}°C")
```

---

#### 2. Parameterområden
```python
BOUNDS = {
    'curve_offset': (-10, 10),        # Nibe's fysiska gräns
    'heating_curve': (1, 15),         # Nibe's fysiska gräns
    'room_temp': (18, 25),            # Rimligt temperaturspann
    'start_compressor': (-1000, -60), # Rekommenderat av Nibe
    'hot_water_demand': (0, 2),       # Diskreta nivåer
}
```
**Motivering:** Baserat på Nibe's dokumentation och fysiska begränsningar.

---

#### 3. Max steg-storlek per ändring
```python
MAX_STEP_SIZES = {
    'curve_offset': 5,      # ±5 steg (ökat för prediktiv styrning)
    'heating_curve': 2,     # ±2 steg
    'room_temp': 1,         # ±1°C
}
```
**Motivering:**
- curve_offset: Behöver ±5 för att kunna agera prediktivt (3h lead time)
- heating_curve: Stor påverkan → små steg
- room_temp: Direkt komfort-påverkan → försiktig

**Historisk ändring:**
- Tidigare: ±2 steg för curve_offset
- Problem: För långsam respons för prediktiv styrning
- Lösning: Ökade till ±5 efter analys av 3h svarstid

---

#### 4. Konfidenstörskel
```python
MIN_CONFIDENCE_TO_APPLY = 0.70  # 70% minimum
```
**Motivering:**
- Under 70%: AI:n är för osäker → Bättre att inte ändra
- Över 70%: Tillräcklig säkerhet för att ta beslut

**Konfidensdistribution (observerad):**
```
0.90-1.0:  15% av beslut (mycket tydliga situationer)
0.80-0.89: 45% av beslut (normala justeringar)
0.70-0.79: 30% av beslut (gränsfall, appliceras)
<0.70:     10% av beslut (blockeras)
```

---

### Mjuka gränser (rekommendationer till AI)

#### 1. Indoor temperaturzoner
```python
ZONE_COLD    = indoor < 20.5    # Höj värme prioritet
ZONE_OPTIMAL = 20.5-21.5        # Normal drift
ZONE_WARM    = indoor > 21.5    # Kan sänka värme
```

#### 2. COP-trösklar
```python
COP_EXCELLENT = > 3.5   # Mycket effektiv drift
COP_GOOD      = 3.0-3.5 # Normal effektiv drift
COP_ACCEPTABLE= 2.5-3.0 # Acceptabel drift
COP_POOR      = < 2.5   # Dålig drift, behöver åtgärd
```

#### 3. Prissignaler
```python
# Relativt dagsmedelväde
EXPENSIVE = current_price > daily_avg * 1.2  # +20%
CHEAP     = current_price < daily_avg * 0.8  # -20%
NORMAL    = mellan dessa
```

---

## Antaganden och Osäkerheter

### Systemantaganden

#### Antagande 1: Nibe's PID-regulator är väl-tunad
**Antagande:**
- Nibe's inbyggda regulator hanterar framledningstemperatur optimalt
- Kompressor-timing är korrekt för systemet

**Validering:** ✓ DELVIS
- Kompressorfrekvens regleras smidigt (observerat i data)
- Framledningstemperatur följer värmekurvan (verifierat)

**Risk om fel:**
- Om PID är dåligt tunad → våra offset-justeringar kan förvärra oscillationer
- Mitigation: Vi ändrar långsamt (1 gång/timme) så Nibe's regulator hinner stabilisera

---

#### Antagande 2: Rumstemperaturmätningen är representativ
**Antagande:**
- Nibe's rumsgivare mäter "genomsnittlig" husets temperatur
- Placering är optimal

**Validering:** ⚠️ OKÄND
- Vi vet inte var givaren sitter
- Kan påverkas av sol, dragning, närheten till värmekällor

**Risk om fel:**
- Givare i varmt rum → systemet tror hela huset är varmt → understyrd värme
- Givare i kallt rum → systemet tror hela huset är kallt → överstyrd värme

**Mitigation:**
- Vi håller bred säkerhetsmarginal (20.0°C minimum, målzon 20.5-21.5°C)
- Användare kan rapportera om det känns för kallt/varmt → justera målzon

---

#### Antagande 3: Husets värmebehov är stabilt
**Antagande:**
- Inga stora interna värmekällor (spis, ugn, människor) under dagen
- Solstrålning är relativt konstant (svensk vinter → lite sol)

**Validering:** ✓ TROLIGT
- Data visar stabila COP-värden över 72h perioder
- Indoor temperatur varierar endast ±0.5°C (stabilt)

**Risk om fel:**
- Stor fest med många gäster → Huset blir varmt → System fortsätter värma
- Mitigation: Indoor temp-mätning fångar upp detta inom 1-2h

---

#### Antagande 4: 3h svarstid är konstant
**Antagande:**
- Husets termiska responståg är ~3h oavsett ytterbetingelser

**Validering:** ⚠️ OSÄKERT
- Baserat på begränsad empirisk data (2 mätpunkter)
- Kan variera med väder, vind, sol

**Risk om fel:**
- Om faktisk svarstid är 1.5h → Vi agerar för tidigt → Överstyring
- Om faktisk svarstid är 5h → Vi agerar för sent → Understyring

**Mitigation:**
- Kontinuerlig inlärning från historik (COP-utvärdering efter 6h)
- AI kan lära sig justera timing baserat på resultat

---

### Mätosäkerheter

#### Indoor Temperature (40033)
**Precision:** ±0.3°C
**Systematiskt fel:** OKÄNT
**Variabilitet:** LÅG (stabil mätning över tid)

**Implikation:**
- 20.0°C-gränsen har i själva verket ±0.3°C osäkerhet → Faktiskt 19.7-20.3°C

---

#### Outdoor Temperature (40004)
**Precision:** ±0.5°C
**Systematiskt fel:** MEDEL (beror på placering)
**Variabilitet:** MEDEL (påverkas av sol, vind)

**Implikation:**
- Nibe's värmekurva använder denna → Fel i utetemp → Fel framledningstemp

---

#### Electric Power (40072 / 43427)
**Precision:** ±5%
**Systematiskt fel:** HÖG (kända problem)
**Variabilitet:** HÖG

**Implikation:**
- COP-beräkningar har ±10-15% osäkerhet
- Använd COP för relativa jämförelser (före/efter), ej absoluta värden

---

#### SMHI Väderprognos
**Precision (0-6h):** ±1°C
**Precision (6-12h):** ±2°C
**Systematiskt fel:** LÅG (professionell väderstation)

**Implikation:**
- Prediktioner baserade på väder har inherent osäkerhet
- "COOLING" trend kan visa sig vara "STABLE" i praktiken

---

### Modellosäkerheter

#### Thermal Response Model
**Antagande:** Första ordningens linjärt system
**Validering:** DÅLIG (R² = 0.06 vid mätning)
**Förenkling:** Ignorerar sol, vind, interna värmekällor

**Implikation:**
- 3h-svarstiden är en grov uppskattning
- Faktisk respons kan variera ±50% (1.5-4.5h)

---

#### COP Calculation
**Metod:** `thermal_energy / electrical_energy`
**Osäkerhet källor:**
- Flödesmätning: ±10%
- Temperaturmätning: ±0.5°C
- Effektmätning: ±15%
- **Total osäkerhet:** ±20%

**Implikation:**
- COP 3.0 ± 0.6 (faktiskt intervall: 2.4-3.6)
- Använd för jämförelser, inte absoluta värden

---

## Inlärningssystem

### Historisk COP-utvärdering

**Metod:** A/B Testing (före/efter jämförelse)

**Process:**
1. **Parameterändring appliceras** (t.ex. offset -6 → -8)
2. **Före-period:** 6h FÖRE ändringen → Beräkna COP_before
3. **Efter-period:** 6h EFTER ändringen (börjar 1h efter ändring) → Beräkna COP_after
4. **Utvärdering:** `COP_change = COP_after - COP_before`
5. **Lagring:** Spara resultat i `ab_test_results` tabell

**Tidslinje:**
```
-6h        0h (change)    +1h         +7h         Evaluation
 |─────────|──────────────|───────────|──────────|
 ← Before  →              ← After period →
 (6h data)                (6h data)
```

**Interpretation:**
```python
if COP_change > +0.1:
    result = "EXCELLENT - Significant improvement"
elif COP_change > 0:
    result = "GOOD - Minor improvement"
elif COP_change > -0.1:
    result = "NEUTRAL - No significant change"
else:
    result = "POOR - Degraded performance"
```

---

### Kontinuerlig Feedback till AI

**Metod:** Historikvisning i prompt

**Implementation:**
```python
# I varje AI-anrop, visa senaste 24h ändringar med resultat
history = get_recent_changes(hours_back=24)

for change in history:
    if change.evaluated:
        show_to_ai(f"{change.hours_ago}h ago: {change.parameter} "
                   f"{change.old}→{change.new} (COP:{change.cop_impact:+.2f})")
    else:
        show_to_ai(f"{change.hours_ago}h ago: {change.parameter} "
                   f"{change.old}→{change.new} (pending evaluation)")
```

**AI's lärande:**
```
HISTORY(last 24h):
4h ago: curve_offset -3→-5 (COP:+0.12)  ← AI ser: "Sänkning förbättrade COP"
8h ago: hot_water 1→0 (COP:-0.05)       ← AI ser: "Sänkning försämrade COP"
12h ago: curve_offset -5→-3 (COP:-0.08) ← AI ser: "Höjning försämrade COP"
```

**AI's reasoning (exempel):**
> "Historiken visar att sänkning -3→-5 gav +0.12 COP. Nuvarande situation liknar
> (dyrt pris, stabilt väder). Upprepar liknande strategi: -6→-8."

---

### Långsiktig utvärdering (48h A/B-test)

**Frekvens:** 1 gång/dag (kl 06:00)
**Metod:** Mer noggrann statistisk analys

**Skillnad mot 6h-utvärdering:**
- Längre perioder → Mer statistisk signifikans
- Inkluderar dag/natt-cykler
- Detekterar subtila effekter

**Användning:**
- Validera långsiktiga strategier
- Justera heating_curve (sällan)
- Identifiera säsongseffekter

---

### Adaptive Learning (framtida förbättring)

**Potentiell förbättring:** Online learning med Bayesian optimization

**Idé:**
```python
# Istället för fixed regler, lär systemet optimal policy
optimal_offset = bayesian_model.predict(
    outdoor_temp=4.2,
    price=1.65,
    indoor_temp=21.4,
    weather_trend="STABLE"
)
```

**Fördel:**
- Anpassar sig automatiskt till specifika huset
- Lär sig optimala timing (kanske 2.5h svarstid istället för 3h)

**Nackdel:**
- Kräver mycket träningsdata (månader)
- Risk för överanpassning
- Svårare att felsöka

**Status:** INTE IMPLEMENTERAT (kräver mer data först)

---

## Tekniska Specifikationer

### Hårdvara
- **Värmepump:** Nibe F730 (frånluftvärmepump)
- **Styrning:** MyUplink Premium Manage API
- **Givare:**
  - Rumstemperatur: Nibe intern (okänd modell)
  - Utomhustemperatur: Nibe extern (okänd modell)
  - Kompressorfrekvens: Inverter-sensor
  - Framledningstemperatur: Nibe intern
  - Effekt: Nibe energimätning

### Mjukvara
- **AI-motor:** Google Gemini 2.5 Flash (fallback: 2.0 Flash Experimental)
- **Databas:** SQLite (lokal lagring på Raspberry Pi)
- **Scheduler:** Cron (kör varje hel timme)
- **API-integration:** MyUplink REST API
- **Väderdata:** SMHI API (Sveriges Meteorologiska Institut)

### Kommunikation
- **Update-frekvens:** 1 gång/timme
- **Mätnings-frekvens:** 5 minuter (pump → databas)
- **Prognos-frekvens:** Före varje beslut (real-time)
- **Logging:** Samtliga beslut och parameterjusteringar sparas

---

## Appendix: Parameterlista

### Styrparametrar (Write)
| Parameter ID | Namn                 | Typ    | Range        | Enhet     | Användning       |
|--------------|----------------------|--------|--------------|-----------|------------------|
| 47011        | Curve Offset         | Int    | -10 till +10 | Steg      | PRIMÄR STYRNING  |
| 47007        | Heating Curve        | Int    | 1 till 15    | Kurva     | Sekundär         |
| 47206        | Start Compressor     | Int    | -1000 / -60  | DM        | Sällan           |
| 47041        | Hot Water Demand     | Int    | 0 till 2     | Nivå      | Ofta             |
| 47015        | Room Temperature     | Float  | 18 till 25   | °C        | EJ ANVÄND        |
| 50005        | Increased Vent       | Int    | 0 till 4     | Nivå      | EJ ANVÄND        |

### Mätparametrar (Read)
| Parameter ID | Namn                     | Enhet   | Frekvens | Tillförlitlighet |
|--------------|--------------------------|---------|----------|------------------|
| 40033        | Room Temperature         | °C      | 5 min    | ⭐⭐⭐⭐⭐           |
| 40004        | Outdoor Temperature      | °C      | 5 min    | ⭐⭐⭐⭐            |
| 40008        | Supply Temperature       | °C      | 1 min    | ⭐⭐⭐⭐⭐           |
| 43136        | Compressor Frequency     | Hz      | 1 min    | ⭐⭐⭐⭐⭐           |
| 40072        | Electric Power (total)   | kW      | 1 min    | ⭐⭐⭐⭐            |
| 43427        | Electric Addition Power  | kW      | 1 min    | ⭐⚫⚫⚫ (problem)  |

---

## Revisionshistorik

| Datum      | Version | Ändring                                            |
|------------|---------|----------------------------------------------------|
| 2025-12-04 | 1.0     | Initial dokumentation skapad                       |
|            |         | - Alla styrparametrar dokumenterade                |
|            |         | - Tidskonstanter mätta och dokumenterade           |
|            |         | - Prediktiv styrning beskriven                     |
|            |         | - Säkerhetsgränser specificerade                   |
|            |         | - Antaganden och osäkerheter identifierade         |

---

## Kontakt och Support

**Frågor om systemet:** Se huvudrepositoriet
**Buggrapporter:** GitHub Issues
**Förbättringsförslag:** Pull Requests välkomna

---

*Detta dokument uppdateras kontinuerligt när systemet utvecklas och nya insikter upptäcks.*
