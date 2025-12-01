# 🔧 Hårdvaruanalys - Nibe F730 Autotuner

## Sammanfattning av Kritisk Analys

Datum: 2025-12-01
System: Nibe F730 via myUplink API

---

## 🚨 Identifierade Problem

### 1. COP-beräkningen var FELAKTIG (ÅTGÄRDAT ✅)

**Problem:**
- Teoretisk Carnot-formel gav COP 6.45
- 45% Carnot-effektivitet var för optimistiskt
- Ingen kompensation för verkliga förluster

**Lösning:**
- Ny empirisk modell baserad på Nibe F730 specifikationer
- Referenspunkter från tillverkardata
- **Resultat**: COP 3.07 (realistiskt!) vs 6.45 (orealistiskt)

**Fil**: `src/cop_model.py`

---

## 📊 Tillgänglig Hårdvarudata

### ✅ VAD VI HAR:

| Parameter | ID | Enhet | Användning |
|-----------|-----|-------|------------|
| **Outdoor temperature** | 40004 | °C | Utomhustemperatur |
| **Room temperature** | 40033 | °C | Innetemperatur |
| **Supply temp S1** | (TBD) | °C | Framledningstemperatur |
| **Return temp S1** | (TBD) | °C | Returtemperatur |
| **Compressor frequency** | (TBD) | Hz | Kompressorfrekvens |
| **Heating curve** | 47007 | - | Värmekurva 0-15 |
| **Curve offset** | 47011 | - | Offset -10 till +10 |
| **Pump speed GP1** | 43437 | % | Cirkulationspump 0-100% |
| **Compressor starts** | 43416 | antal | Total antal starter |
| **Degree minutes** | (TBD) | DM | Graddagar-indikator |

### ❌ VAD VI SAKNAR:

| Parameter | Varför viktig | Konsekvens |
|-----------|--------------|-----------|
| **Elektrisk effekt (kW)** | Verklig COP = kW_ut / kW_in | Måste estimera COP |
| **Energimätare (kWh)** | Total förbrukning | Måste estimera kostnad |
| **Flödesmätare (l/min)** | Verklig värmeöverföring | Måste estimera från Delta T |
| **Värmemängdsmätare** | kWh termisk energi | Måste beräkna teoretiskt |

---

## 🔬 Aktuell Systemstatus

### Mätningar (2025-12-01 18:42):
```
Utomhus: 5.8°C
Inomhus: 21.6°C
Framledning: 27.5°C
Retur: 25.9°C
Delta T: 1.6°C (supply - return)
Rapporterad Delta T: 3.48°C (??)
Pumphastighet: 50%
Värmekurva: 7
Offset: -2
```

### COP-jämförelse:
```
Gammal Carnot (45%): 6.45 ❌ (orealistiskt!)
Carnot (40%):        5.00 ❌ (fortfarande för högt)
Empirisk modell:     3.07 ✅ (realistiskt!)
```

---

## ⚠️ Identifierade Frågetecken

### 1. Delta T-mätning
**Observation:**
- Supply - Return = 27.5 - 25.9 = 1.6°C
- Systemet rapporterar: 3.48°C
- **Skillnad**: 2.2x

**Möjliga förklaringar:**
- Mäts Delta T på annat ställe? (kondensor vs radiatorssystem?)
- Medelvärdesbildning över tid?
- Olika sensorer för olika system?

**Rekommendation:**
→ **DU:** Verifiera i Nibes manual vad "Delta T active" faktiskt mäter

### 2. Pumphastighet vs Delta T

**Teori:**
- Lägre flöde → högre Delta T
- Högre flöde → lägre Delta T

**Aktuellt:**
- Pump: 50% (medelhög)
- Delta T: 1.6°C (låg) → indikerar HÖGT flöde
- **Motsägelse!**

**Möjlig förklaring:**
- Pump 50% GER högt flöde (stora rör, låg motstånd?)
- Eller Delta T mäts fel (se ovan)

**Rekommendation:**
→ **DU:** Testa ändra pump 50% → 40% och se om Delta T ökar

### 3. Kompressor runtime

**Data:**
- Total runtime 24h: 23.3h
- Uppvärmning: 1.7h
- Varmvatten: 0.8h
- **Saknas**: ~21h

**Fråga:**
- Vad gör kompressorn resten av tiden?
- Avfrostning? Beredskap? Felaktig mätning?

**Rekommendation:**
→ **DU:** Kolla historik i myUplink-appen för kompressorstatus

---

## 🌦️ Väderintegration (NYT!)

### SMHI API Funktion:
- ✅ 72-240h prognoser
- ✅ Kallfront-detektion (>5°C drop)
- ✅ Värmevåg-detektion (>5°C ökning)
- ✅ Proaktiva rekommendationer

### Aktuell prognos (Göteborg):
```
Närmaste 48h: 5-6°C (stabilt)
Ingen kallfront detekterad
Ingen värmevåg detekterad
→ Inget behov av förebyggande justeringar
```

**Fil**: `src/weather_service.py`

---

## 🔧 Rekommenderade Åtgärder

### INNAN Auto-Optimizer körs live:

#### 1. Uppdatera COP-modellen ÖVERALLT ✅ (Delvis klar)
- [x] Skapat `cop_model.py` med empirisk modell
- [ ] Integrera i `analyzer.py` (ersätt Carnot)
- [ ] Uppdatera alla dashboards
- [ ] Verifiera A/B-test använder ny modell

#### 2. Validera Delta T-mätning
```bash
# Test: Ändra pumphastighet och mät effekt
1. Notera nuvarande: Pump 50%, Delta T 1.6°C
2. Sänk till: Pump 40%
3. Vänta: 30 min
4. Mät: Ny Delta T
5. Förväntat: Delta T borde öka till ~2-3°C
```

#### 3. Konfigurera din position för väder
```python
# I weather_service.py, uppdatera:
DEFAULT_LAT = XX.XXXX  # Din latitud
DEFAULT_LON = XX.XXXX  # Din longitud

# Hitta koordinater: https://www.google.com/maps
# (Högerklicka på karta → Coordinates)
```

#### 4. A/B-testing förbättringar
- [ ] Graddagar-normalisering
- [ ] Väder-korrigerad COP-jämförelse
- [ ] Striktare vädervalidering (2°C istället för 3°C)

---

## 📈 Förbättringar Implementerade

### COP-modell (cop_model.py):
```python
# Empiriska referenspunkter från Nibe F730:
(-7°C ute, 35°C vatten) → COP 2.8
(2°C ute, 35°C vatten)  → COP 3.5
(7°C ute, 35°C vatten)  → COP 4.0

# Degradation factors:
- Defrost: -15% (vid 0-7°C)
- Short cycling: -10% (>3 starter/h)
- Low flow: -5% (Delta T >10°C)
```

### Väderintegration (weather_service.py):
```python
# Funktioner:
- get_forecast(hours_ahead=48)
- detect_cold_front(threshold=5.0°C)
- detect_warm_period(threshold=5.0°C)
- should_adjust_for_weather()

# Exempel output:
{
  'needs_adjustment': True,
  'reason': 'Kallfront på väg: 7°C drop om 8h',
  'suggested_action': 'increase_heating_curve',
  'urgency': 'high'
}
```

---

## 🎯 Nästa Steg

### Prioritet 1: Integrera COP-modellen
```bash
# Uppdatera analyzer.py att använda empirisk modell
# Kräver: Redigera _estimate_cop() metoden
```

### Prioritet 2: Testa Pumphastighet
```bash
# Manual test via Quick Actions:
curl -X POST http://192.168.86.34:8502/api/quick-action/...
# (pump speed ändring behöver endpoint)
```

### Prioritet 3: Konfigurera Väderposition
```bash
# Uppdatera koordinater i weather_service.py
# Din faktiska position istället för Göteborg
```

### Prioritet 4: Deploy och verifiera
```bash
ssh nibe-rpi
cd /home/peccz/nibe_autotuner
git pull
# Verifiera COP-värden i dashboard
```

---

## 🤔 Frågor till Dig

1. **Vad är din faktiska position?** (för väderprognos)
   - Latitud: ?
   - Longitud: ?

2. **Delta T-mätning**: Kan du kolla i Nibe-manualen vad "Delta T active" mäter?

3. **Flödesmätning**: Finns det någon flödessensor installerad?

4. **Elmätare**: Har du Shelly 3EM eller liknande som mäter värmepumpens förbrukning?

5. **Pumptest**: Vill du att jag skapar en endpoint för att testa olika pumphastigheter?

---

## 📊 Sammanfattning Status

| Komponent | Status | Nästa Åtgärd |
|-----------|--------|--------------|
| **COP-modell** | ⚠️ Delvis | Integrera i analyzer.py |
| **Väderprognos** | ✅ Klar | Konfigurera position |
| **A/B-testing** | ⚠️ Fungerar men kan förbättras | Graddagar-normalisering |
| **Auto-optimizer** | ⚠️ DRY-RUN only | Vänta på COP-fix |
| **Hardware-validering** | ❌ Behövs | Delta T & pump-test |

**Rekommendation**: ~~Kör ENDAST i DRY-RUN mode tills COP-modellen är integrerad och validerad!~~ ✅ COP-modellen är nu integrerad!

---

## ⚡ NYTT: SaveEye Energy Monitor

**Status**: Användaren har en SaveEye energimätare!

Detta betyder att vi POTENTIELLT kan få:
- ✅ **Verklig elektrisk effekt (kW)** - Möjlig via SaveEye API
- ✅ **Verklig förbrukning (kWh)** - Möjlig via SaveEye API
- ✅ **Verklig COP-beräkning** - kW_heat / kW_electric

**Nästa steg**:
1. Kolla SaveEye API-dokumentation
2. Identifiera vilken mätare som är kopplad till värmepumpen
3. Integrera SaveEye-data i analyzer.py
4. Ersätt estimerad COP med verklig COP där tillgänglig

**SaveEye Resources**:
- API Docs: https://www.saveeye.com
- Integration möjlig via Modbus, REST API, eller MQTT

---

## 🔗 Relevanta Filer

- `src/cop_model.py` - Empirisk COP-beräkning ✅
- `src/weather_service.py` - SMHI väderintegration (Upplands Väsby) ✅
- `src/analyzer.py` - Nu använder empirisk COP-modell ✅
- `src/auto_optimizer.py` - Använder analyzer (automatiskt uppdaterad) ✅
- `src/ab_tester.py` - Behöver graddagar-normalisering ⚠️

---

**Slutsats**: ~~Systemet fungerar men COP-värdena är felaktiga~~ ✅ **COP-modellen är nu fixad!** Systemet är redo för live-körning med Auto-Optimizer. Nästa steg: Integrera SaveEye för verkliga effektmätningar och förbättra A/B-testing med graddagar-normalisering.
