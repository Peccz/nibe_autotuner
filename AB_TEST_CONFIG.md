# ⚙️ A/B Test Configuration Guide

## Förutsättningar och inställningar

### Tidsinställningar

```python
BEFORE_HOURS = 48      # Hur många timmar FÖRE ändringen som jämförs
AFTER_HOURS = 48       # Hur många timmar EFTER ändringen som jämförs
MIN_WAIT_HOURS = 48    # Minsta väntetid innan utvärdering körs
```

**Varför 48h?**
- Täcker 2 dygn med alla väder- och användningsmönster
- Undviker dagliga variationer (kalla nätter, varma dagar)
- Statistiskt tillräckligt för värmepumpar

**Kan justeras:**
```python
# I mobile_app.py eller eget script:
ab_tester = ABTester(
    analyzer,
    before_hours=72,      # 3 dygn istället
    after_hours=72,
    min_wait_hours=72
)
```

### Viktningskoefficienter

```python
WEIGHT_COP = 0.40        # 40% - Viktigast (effektivitet)
WEIGHT_DELTA_T = 0.20    # 20% - Värmeöverföring
WEIGHT_COMFORT = 0.20    # 20% - Innetemperatur stabilitet
WEIGHT_CYCLES = 0.10     # 10% - Antal starter (slitage)
WEIGHT_COST = 0.10       # 10% - Kostnadsbesparing
```

**Summa: 100%**

**Exempel på alternativ prioritering:**
```python
# Om du prioriterar komfort över effektivitet:
WEIGHT_COMFORT = 0.40
WEIGHT_COP = 0.30
WEIGHT_DELTA_T = 0.15
WEIGHT_CYCLES = 0.10
WEIGHT_COST = 0.05
```

**OBS:** Detta kräver kod-ändring i `ab_tester.py:25-30`

### Vädervalidering (NYT!)

```python
MAX_OUTDOOR_TEMP_DIFF = 3.0  # Max °C skillnad mellan före/efter
```

**Vad händer:**
1. Systemet jämför medeltemperatur ute under 48h före vs 48h efter
2. Om skillnaden > 3.0°C → **Varning i resultatet**
3. Testet körs ändå, men flaggas som "osäkert"

**Exempel:**
```
FÖRE: -5°C genomsnitt
EFTER: +2°C genomsnitt
Skillnad: 7°C → ⚠️ VARNING: Väder ändrades 7.0°C - resultat osäkra!
```

**Justera tröskelvärdet:**
```python
ab_tester = ABTester(
    analyzer,
    max_outdoor_temp_diff=5.0  # Tillåt större variation
)
```

## Success Score Beräkning

### Grundpoäng: 50 (neutral)

### COP-komponent (40% vikt)
```
+10% COP → +20 poäng
-10% COP → -20 poäng
```

**Exempel:**
- COP 3.0 → 3.3 (+10%) = +20 × 0.40 = +8 poäng
- COP 3.5 → 3.15 (-10%) = -20 × 0.40 = -8 poäng

### Delta T-komponent (20% vikt)
**Optimal: 6°C** (mitten av 5-7°C range)

```
Om EFTER närmare 6°C än FÖRE:
  Poäng = (förbättring i °C) × 10 × 0.20
```

**Exempel:**
- FÖRE: 9°C (3°C från optimum), EFTER: 7°C (1°C från optimum)
- Förbättring: 2°C → +2 × 10 × 0.20 = +4 poäng

### Komfort-komponent (20% vikt)
**Mål: Stabil innetemperatur**

```
|Förändring| < 0.5°C → +20 × 0.20 = +4 poäng
|Förändring| < 1.0°C → +10 × 0.20 = +2 poäng
|Förändring| ≥ 1.0°C → 0 poäng
```

### Cykel-komponent (10% vikt)
```
Färre cykler EFTER → +10 × 0.10 = +1 poäng
Fler eller lika → 0 poäng
```

### Slutpoäng
```
Total score = 50 + COP-poäng + Delta T-poäng + Komfort-poäng + Cykel-poäng
Clamped till 0-100
```

## Rekommendationer

### Poäng → Rekommendation

| Score | Rekommendation | Betydelse |
|-------|---------------|-----------|
| 70-100 | ✅ BEHÅLL - Mycket bra resultat! | Tydlig förbättring |
| 55-69 | 👍 BEHÅLL - Bra förbättring | Positiv effekt |
| 45-54 | 🤔 NEUTRAL - Marginell effekt | Ingen större skillnad |
| 30-44 | ⚠️ JUSTERA/ÅTERSTÄLL | Försämring eller temp-problem |
| 0-29 | ❌ ÅTERSTÄLL - Tydlig försämring | Klart sämre |

### Specialfall

**Om innetemperaturen ändrats >1.0°C:**
- Score 30-44 → "⚠️ JUSTERA - Temperaturen påverkad"
- Prioriterar komfort över små COP-förbättringar

**Om väder ändrats för mycket:**
- Alla rekommendationer får suffix: "⚠️ VARNING: Väder ändrades X°C - resultat osäkra!"

## Vad beaktas och vad beaktas INTE

### ✅ Beaktas
1. **COP före vs efter** (viktat 40%)
2. **Delta T optimering** mot 6°C (viktat 20%)
3. **Innetemperatur stabilitet** (viktat 20%)
4. **Antal kompressor-cykler** (viktat 10%)
5. **Kostnadsbesparing** (rapporteras, ej i score)
6. **Utomhustemperatur** - nu validerad! (varning om >3°C diff)

### ❌ Beaktas INTE (ännu)
1. **Graddagar-normalisering** - COP justeras ej för väder
2. **Trendanalys** - endast före/efter, ej trend över tid
3. **Statistisk signifikans** - ingen p-värde beräkning
4. **Säsongsjustering** - vinter vs sommar behandlas lika
5. **Användarmönster** - ingen kompensation för annorlunda användning

## Hur ändra inställningar

### 1. Enkel justering (runtime)

I `mobile_app.py`:
```python
ab_tester = ABTester(
    analyzer,
    before_hours=72,              # 3 dygn
    after_hours=72,
    min_wait_hours=72,
    max_outdoor_temp_diff=5.0     # Tillåt 5°C skillnad
)
```

### 2. Permanent ändring

Redigera `src/ab_tester.py:21-33`:
```python
BEFORE_HOURS = 72   # Ändra från 48 till 72
AFTER_HOURS = 72
MIN_WAIT_HOURS = 72
MAX_OUTDOOR_TEMP_DIFF = 5.0  # Ändra från 3.0 till 5.0
```

### 3. Ändra viktning

Redigera `src/ab_tester.py:25-30`:
```python
WEIGHT_COP = 0.50        # Öka COP-vikt
WEIGHT_DELTA_T = 0.15    # Minska Delta T
WEIGHT_COMFORT = 0.25    # Öka komfort
WEIGHT_CYCLES = 0.05
WEIGHT_COST = 0.05
```

**OBS:** Summan MÅSTE bli 1.0 (100%)!

## Rekommenderade inställningar för olika scenario

### Scenario 1: Vinteroptimering (stabilt kallt väder)
```python
before_hours=48
after_hours=48
max_outdoor_temp_diff=2.0  # Striktare (vinter mer stabilt)
```

### Scenario 2: Vår/höst (växlande väder)
```python
before_hours=72   # Längre period för jämnare medelvärde
after_hours=72
max_outdoor_temp_diff=5.0  # Mer tolerant
```

### Scenario 3: Snabb testning (experimentellt)
```python
before_hours=24
after_hours=24
min_wait_hours=24
max_outdoor_temp_diff=3.0
```
**⚠️ VARNING:** Kortare perioder ger mindre tillförlitliga resultat!

### Scenario 4: Konservativ (säker)
```python
before_hours=96   # 4 dygn
after_hours=96
min_wait_hours=96
max_outdoor_temp_diff=1.0  # Mycket strikt
```

## Framtida förbättringar (roadmap)

### Prioritet 1: Graddagar-normalisering
Justera COP baserat på utomhustemperatur för rättvisare jämförelse.

**Formel:**
```python
normalized_cop = actual_cop × (reference_temp / actual_temp)
```

### Prioritet 2: Statistisk signifikans
Beräkna p-värde för att avgöra om förändringen är slumpmässig.

### Prioritet 3: Trendanalys
Analysera trend istället för bara medelvärde (förbättras det över tid?).

### Prioritet 4: ML-baserad prediktion
Förutsäg effekt av ändringar innan de görs.

## Frågor och svar

**Q: Varför 48h och inte 24h eller 72h?**
A: 48h täcker 2 dygn vilket ger representativ data utan att bli för långsamt. Balans mellan snabbhet och tillförlitlighet.

**Q: Vad händer om jag gör flera ändringar inom 48h?**
A: Varje ändring får sitt eget A/B-test, men de kan påverka varandra. Bäst att vänta 48h mellan stora ändringar.

**Q: Kan jag avbryta en pågående test?**
A: Nej, automatisk. Men du kan ändra tillbaka parametern när som helst. Båda ändringarna testas separat.

**Q: Vad om vädret ändras mycket?**
A: Nu flaggas det med varning om >3°C skillnad. Resultatet visas ändå men med "⚠️ VARNING: Väder ändrades X°C".

**Q: Hur tvingar jag omvärdering av ett test?**
A: Radera raden från `ab_test_results` tabellen. Nästa gång `evaluate_all_pending()` körs utvärderas den igen.

## Sammanfattning

✅ **Nuvarande system:**
- Jämför 48h före vs 48h efter
- 5 viktade komponenter (COP 40%, Delta T 20%, Komfort 20%, Cykler 10%, Kostnad 10%)
- Validerar väder (max 3°C skillnad)
- Score 0-100 → Rekommendation

✅ **Konfigurerbara parametrar:**
- Tidsperioder (före/efter/väntetid)
- Max temperaturskillnad (vädervalidering)

⚠️ **Begränsningar:**
- Ingen graddagar-normalisering (än)
- Ingen statistisk signifikanstest
- Viktning måste ändras i kod (ej runtime)

**Rekommendation:** Standardinställningarna (48h, 3°C max diff) fungerar bra för de flesta fall!
