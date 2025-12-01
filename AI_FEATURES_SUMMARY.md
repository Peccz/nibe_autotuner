# 🤖 AI-Funktioner Sammanfattning - För GUI

## Översikt

Detta dokument sammanfattar alla AI-drivna funktioner i Nibe Autotuner som ska presenteras i den mobila GUI:n.

---

## 🎯 Auto-Optimizer (Automatisk Optimering)

### Vad den gör
Analyserar din värmepumps prestanda varje natt och justerar inställningar automatiskt för optimal drift.

### Hur den fungerar
1. **Analys** (varje natt kl 03:00)
   - Läser senaste 72 timmars data
   - Beräknar COP, Delta T, komfort, cykler
   - Identifierar förbättringsmöjligheter

2. **Bedömning**
   - Jämför nuvarande prestanda mot optimalt
   - Beräknar confidence (0-100%)
   - Uppskattar besparingar (kr/år)
   - Prioriterar åtgärder (CRITICAL → LOW)

3. **Ändring** (om villkor uppfylls)
   - Max 1 ändring per 48 timmar
   - Endast ändringar med >70% confidence
   - Respekterar säkerhetsgränser
   - Loggar allt för transparency

### Vad den optimerar
- **Värmekurva** (3-10): Huvudinställning för uppvärmning
- **Kurvjustering** (-5 till +5): Finjustering av temperatur
- **Rumstemperatur** (19-23°C): Direkt temperaturinställning
- **Start kompressor** (-400 till -100 DM): När kompressorn startar

### Säkerhet
- ✅ Max 1 ändring per 48h (A/B-test behöver tid)
- ✅ Max 3 ändringar per vecka (förhindrar "jakt")
- ✅ Hårdkodade min/max-värden
- ✅ Confidence-tröskel 70%
- ✅ Komfort prioriteras alltid (aldrig för kallt!)

### GUI-Presentation

**Status Card**:
```
🤖 Auto-Optimizer
Status: ✅ Aktiv
Senaste körning: 2025-12-01 03:00
Nästa körning: 2025-12-02 03:00

Senaste ändring:
• Kurvjustering: 0 → -1
• Anledning: För varmt inne (22.3°C)
• Förväntat: 260 kr/år besparing
• Confidence: 85%

Statistik (30 dagar):
• Ändringar gjorda: 4
• Genomsnittlig besparing: 320 kr/år
• Success rate: 75%
```

**Knapp**: "Se Historik"

---

## 🌬️ Ventilationsoptimering (Intelligent Luftväxling)

### Vad den gör
Justerar ventilationen automatiskt baserat på utomhustemperatur för att hålla luften fuktig och minska drag utan att offra luftkvalitet.

### Hur den fungerar
1. **Analys** (varje morgon kl 06:00)
   - Läser aktuell utomhustemperatur
   - Beräknar luftfuktighets-påverkan
   - Säkerställer luftkvalitet för 5 personer

2. **Strategi-val** (4 nivåer)
   - **VARM** (>10°C): Maximal ventilation (uteluften har fukt)
   - **MILD** (0-10°C): Balanserad ventilation
   - **KALLT** (<0°C): Reducerad ventilation (bevara fukt)
   - **EXTREMT KALLT** (<-10°C): Minimal säker ventilation

3. **Justering**
   - Ökad ventilation: PÅ/AV
   - Start temp frånluft: 22-26°C
   - Min diff ute-frånluft: 5-12°C

### Varför detta hjälper
**Problem**: Kall luft blir extremt torr när den värms inomhus
- Vid -10°C: 80% RH ute → 15% RH inne (mycket torrt!)
- Vid 0°C: 80% RH ute → 30% RH inne (torrt)
- Vid 10°C: 80% RH ute → 55% RH inne (bra!)

**Lösning**: Minska ventilation vid kyla = bevara fukt + minska drag

**Säkerhet**: Alltid minimum 35-50 L/s för 5 personer (Boverket BBR)

### Fördelar
- ✅ Mindre torr luft på vintern (30-40% RH istället för 15-20%)
- ✅ Mindre drag från ventilationsspalter
- ✅ 200-400 kr/år besparing (mindre värmeförlust)
- ✅ Bättre COP (3-6% förbättring vid kyla)
- ✅ Ingen kompromiss på luftkvalitet

### GUI-Presentation

**Status Card**:
```
🌬️ Ventilationsoptimering
Status: ✅ Aktiv
Senaste körning: 2025-12-01 06:00
Nästa körning: 2025-12-02 06:00

Aktuell strategi: MILD
• Utomhus: 4.9°C
• Ökad ventilation: AV
• Start temp frånluft: 24°C
• Min diff: 7°C

Anledning:
"Milt ute (4.9°C): Balanserad ventilation.
Utomhusluften har fortfarande viss fuktighet."

Effekt:
• Uppskattad RH-påverkan: ~8% (OK)
• Fläkthastighet: 50%
• Luftkvalitet: ✅ (>35 L/s)
```

**Knapp**: "Manuell Justering"

---

## 📊 A/B-Testing (Automatisk Utvärdering)

### Vad den gör
Utvärderar ALLA parameterändringar automatiskt efter 48 timmar genom att jämföra prestanda före och efter.

### Hur den fungerar
1. **FÖRE-Mätning**
   - 48 timmar före ändring
   - Sparar: COP, Delta T, Temp, Cykler, Kostnad

2. **EFTER-Mätning** (efter 48h)
   - 48 timmar efter ändring
   - Mäter samma metrics

3. **Normalisering**
   - **Väder-korrektion**: Flaggar om >3°C skillnad
   - **Graddagar-normalisering**: Justerar COP för värmebehov
     * Om kallare efter: COP hade varit sämre ändå
     * Om varmare efter: COP hade varit bättre ändå
     * Normaliserar till samma förhållanden

4. **Bedömning**
   - Success Score (0-100)
   - Viktning:
     * COP: 40%
     * Delta T: 20%
     * Komfort: 20%
     * Cykler: 10%
     * Kostnad: 10%

5. **Rekommendation**
   - **BEHÅLL** (>70 poäng): Ändringen var bra
   - **JUSTERA** (40-70 poäng): Kan förbättras
   - **ÅTERSTÄLL** (<40 poäng): Ändringen var dålig

### Varför detta är viktigt
Utan A/B-testing vet du aldrig om en ändring verkligen hjälpte eller om det bara var bättre väder!

### GUI-Presentation

**Senaste A/B-Test Card**:
```
📊 Senaste A/B-Test
Ändring: Kurvjustering 0 → -1
Datum: 2025-11-28 15:30
Status: ✅ Utvärderad

FÖRE (48h):
• COP: 3.05
• Delta T: 5.2°C
• Inne: 22.3°C
• Ute: 5.2°C
• Kostnad: 18.40 kr/dag

EFTER (48h):
• COP: 3.12 (+2.3%)
• Delta T: 5.4°C (+3.8%)
• Inne: 21.8°C (-0.5°C)
• Ute: 5.8°C (+0.6°C)
• Kostnad: 17.90 kr/dag

Graddagar-normalisering: ✅ Tillämpas
• Värmebehov: -8% (varmare väder)
• Normaliserad COP: 3.08 (+1.0%)
• Reell förbättring: +1.0% (inte +2.3%)

Success Score: 78/100
Rekommendation: ✅ BEHÅLL
Besparing: 183 kr/år
```

**Knapp**: "Se Alla Tester"

---

## 📈 COP-Beräkning (Realistisk Effektivitet)

### Vad den gör
Beräknar värmepumpens verkliga effektivitet (COP) baserat på Nibe F730:s specifikationer istället för teoretiska formler.

### Gamla vs Nya Metoden

**Gamla** (Carnot-formel):
- Teoretisk maxeffektivitet
- 45% Carnot-effektivitet
- **Resultat**: COP 6.45 (OMÖJLIGT!)
- Problem: Alla beslut baserade på felaktiga värden

**Nya** (Empirisk modell):
- Tillverkarspecifikationer
- Verkliga referenspunkter
- Degraderingsfaktorer
- **Resultat**: COP 3.07 (REALISTISKT!)

### Referenspunkter (från Nibe F730 manual)
- -7°C ute, 35°C vatten → COP 2.8
- 2°C ute, 35°C vatten → COP 3.5
- 7°C ute, 35°C vatten → COP 4.0

### Degraderingsfaktorer
- **Avfrostning**: -15% (vid 0-7°C)
- **Kort-cykling**: -10% (>3 starter/timme)
- **Lågt flöde**: -5% (Delta T >10°C)

### GUI-Presentation

**COP Card**:
```
📈 Aktuell COP
Värde: 3.07
Rating: ⭐ VERY GOOD

Förhållanden:
• Utomhus: 5.8°C
• Framledning: 27.5°C
• Retur: 25.9°C
• Delta T: 1.6°C

Beräkning:
• Bas-COP: 3.50 (interpolerad)
• Avfrostning: -0.43 (-15%)
• Resultat: 3.07

Jämförelse:
• Teoretisk (gammal): 6.45 ❌
• Empirisk (ny): 3.07 ✅
• Förväntad (F730): 3.0-3.5 ✓

Prestanda:
• Elektrisk effekt: ~1.5 kW (estimerad)
• Värmeeffekt: ~4.6 kW
• Kostnad: ~3 kr/h
```

**Knapp**: "Se COP-Historik"

---

## 🌦️ Väderintegration (SMHI Prognos)

### Vad den gör
Hämtar väderprognos för Upplands Väsby och använder den för att planera optimeringar proaktivt.

### Funktioner
1. **Prognoser** (72-240h framåt)
   - Temperatur
   - Nederbörd
   - Vind
   - Luftfuktighet

2. **Kallfront-detektion**
   - >5°C temperaturfall
   - Varnar 8-24h i förväg
   - Rekommenderar: "Öka värmekurvan"

3. **Värmevåg-detektion**
   - >5°C temperaturökning
   - Rekommenderar: "Sänk värmekurvan"

4. **Proaktiva Åtgärder**
   - Justerar INNAN väder ändras
   - Förhindrar obehag
   - Bättre energianvändning

### GUI-Presentation

**Väder Card**:
```
🌦️ Väderprognos
Plats: Upplands Väsby

Nu: 4.9°C, Molnigt
Nästa 24h: 5-6°C (stabilt)
Nästa 48h: 6-8°C (uppvärmning)

Prognoser:
• Idag: 4-6°C
• Imorgon: 6-8°C
• Övermorgon: 7-9°C

Varningar: Inga

Rekommendationer:
• Stabilt väder
• Inga justeringar behövs
• Värmekurva OK
```

**Om kallfront upptäcks**:
```
⚠️ KALLFRONT PÅ VÄG!
• Temperaturfall: 7°C
• Ankomst: Om 12 timmar
• Action: Öka värmekurva
• Urgency: HIGH
```

---

## 💡 Quick Actions (Snabbjusteringar)

### Vad den gör
AI-assisterade snabbjusteringar med förklaring och förväntad effekt.

### Tillgängliga Actions

**1. Öka/Minska Innetemperatur**
```
Aktuell: 21.6°C
Justering: +0.5°C eller -0.5°C
Metod: Justerar kurvjustering ±1
Effekt:
• COP-påverkan: ±0.1
• Kostnad: ±2 kr/dag
• Tid till effekt: 2-4 timmar
```

**2. Öka/Minska Värmekurva**
```
Aktuell: 7
Justering: +0.5 eller -0.5
Effekt:
• Större temperaturändring (±1-2°C)
• COP-påverkan: ±0.2-0.3
• Kostnad: ±5-10 kr/dag
• För aggressiv justering
```

**3. Optimera Delta T**
```
Aktuell: 1.6°C (låg)
Problem: För högt flöde
Action: Minska pumphastighet 50% → 45%
Effekt:
• Delta T ökar till ~2-3°C
• COP förbättras +0.1
• Besparing: 100-200 kr/år
```

**4. Reducera Cykler**
```
Aktuella: 25 cykler/72h (för många)
Problem: Kort-cykling
Action: Sänk värmekurva eller öka DM-start
Effekt:
• Färre cykler (längre runtime)
• Mindre slitage
• COP +0.1-0.2
```

### GUI-Presentation

**Quick Actions Grid**:
```
[🌡️ Varmare] [🌡️ Kallare]
[⚡ Ekonomi] [💨 Komfort]
[🔧 Optimera] [📊 Status]
```

**Vid klick** (exempel: Varmare):
```
🌡️ Öka Innetemperatur

Aktuellt:
• Inne: 21.6°C
• Ute: 4.9°C
• Kurvjustering: -2

Förslag:
• Justera offset: -2 → -1
• Förväntad inne-temp: 22.1°C
• Tid till effekt: 2-4h

Effekt:
• COP: 3.07 → 3.05 (-0.6%)
• Kostnad: +1.80 kr/dag
• Besparing: -657 kr/år
• Komfort: ✅ Bättre

Confidence: 85%

[Applicera] [Avbryt]
```

---

## 📱 Dashboard Summary

### Huvudvy

**Header**:
```
🏠 Nibe Autotuner
Status: ✅ Alla system OK
Uppdaterad: 19:24
```

**Top Cards** (3 kolumner):
```
┌─ 📈 COP ────┐  ┌─ 🌡️ Temp ──┐  ┌─ 💰 Kostnad ┐
│ 3.07       │  │ Inne 21.6° │  │ 17.20 kr/d │
│ ⭐ VERY GOOD│  │ Ute 4.9°  │  │ 6,283 kr/å │
│ +2.3% idag │  │ ✅ Optimal │  │ 📉 -5%     │
└────────────┘  └────────────┘  └────────────┘
```

**AI Status** (Expandable):
```
🤖 AI-System
┌────────────────────────────────┐
│ Auto-Optimizer: ✅ Nästa 03:00 │
│ Ventilation: ✅ Nästa 06:00   │
│ A/B-Testing: ✅ 2 aktiva      │
│ Väderprognos: ✅ Uppdaterad   │
└────────────────────────────────┘
[Visa Detaljer]
```

**Quick Actions** (Grid):
```
┌─────────┬─────────┬─────────┐
│ Varmare │ Kallare │ Optimera│
├─────────┼─────────┼─────────┤
│ Ekonomi │ Komfort │ Status  │
└─────────┴─────────┴─────────┘
```

**Recent Activity** (Timeline):
```
Senaste händelser:
• 06:00 Ventilationsoptimering OK
• 03:00 Auto-Optimizer: Ingen ändring
• 00:15 A/B-Test: Kurvjustering ✅ BEHÅLL
• 2025-11-30 15:30 Ändring: Offset 0 → -1
```

---

## 🎓 Hur AI:n Lär Sig

### Feedback Loop

```
1. DATA COLLECTION
   ↓
2. ANALYSIS
   ↓
3. SUGGESTION
   ↓
4. APPLY CHANGE
   ↓
5. A/B TESTING (48h)
   ↓
6. EVALUATION
   ↓
7. LEARNING
   ↓
(repeat)
```

### Exempel: Lärande från Misslyckad Ändring

**Scenario**:
1. AI sänker kurvjustering från 0 → -2
2. Confidence: 75%
3. Förväntning: Besparing 400 kr/år

**A/B-Test Result** (efter 48h):
- COP: 3.05 → 2.98 (-2.3% ❌)
- Inne: 22.3°C → 21.0°C (-1.3°C ❌)
- Success Score: 35/100
- Rekommendation: ÅTERSTÄLL

**Learning**:
- "För stor offset-ändring ger dålig komfort"
- "Sänkning >1 steg kräver högre confidence"
- Nästa gång: Minska i mindre steg (-1 istället för -2)

### GUI-Presentation

**Learning Card** (i Inställningar):
```
🎓 AI-Inlärning

Statistik (90 dagar):
• Totalt ändringar: 12
• Lyckade (BEHÅLL): 9 (75%)
• Justerade: 2 (17%)
• Återställda: 1 (8%)

Lärdomar:
✅ Små justeringar fungerar bäst
✅ Väntid 48h är viktig
✅ Komfort prioriteras över kostnad
✅ Väderförändringar påverkar mycket

Aktuell Confidence:
• Värmekurva: 85%
• Kurvjustering: 90%
• Rumstemperatur: 80%
• Pumphastighet: 70%

[Visa Detaljerad Historik]
```

---

## 🔐 Privacy & Transparency

### Vad AI:n VET
- Alla temperaturer och sensorer
- Värmepumpsinställningar
- Elförbrukning (estimerad eller från SaveEye)
- Väderprognos (från SMHI)
- Historiska ändringar och resultat

### Vad AI:n INTE vet
- Ingen personlig information
- Ingen platsdata (förutom väderposition)
- Inga användarvanor
- Ingen data lämnar din RPi (förutom SMHI-väderförfrågningar)

### Transparens
- ALLA beräkningar loggas
- ALLA ändringar förklaras
- ALLA A/B-test-resultat visas
- Confidence alltid synligt
- Kan stängas av när som helst

### GUI-Presentation

**Settings → AI & Privacy**:
```
🔐 AI-Inställningar

Status:
• Auto-Optimizer: ✅ PÅ
• Ventilation: ✅ PÅ
• A/B-Testing: ✅ PÅ (krävs för AI)

Data:
✅ All data lagras lokalt på RPi
✅ Ingen cloud-sync (förutom myUplink API)
✅ Ingen personlig data samlas
✅ SMHI väderdata används (offentlig API)

Kontroll:
• Min confidence: 70% [slider]
• Max ändringar/vecka: 3 [slider]
• Komfort-prioritet: Hög [slider]

[Stäng Av AI]
[Återställ Till Default]
[Visa Logg]
```

---

## 📊 Sammanfattning för GUI

### Main Features att Implementera

1. **Dashboard Cards**:
   - Auto-Optimizer status
   - Ventilation status
   - Senaste A/B-test
   - COP-värde med rating
   - Väderprognos

2. **Quick Actions**:
   - 6 knappar med AI-assistans
   - Förklaring av effekt
   - Confidence-indikator

3. **History View**:
   - Timeline av alla ändringar
   - A/B-test resultat
   - Lärdomar

4. **Settings**:
   - AI on/off
   - Confidence threshold
   - Notifikationer
   - Privacy info

### Visual Guidelines

**Colors**:
- ✅ Green: OK/Success (COP >3.0, tests passed)
- ⚠️ Orange: Warning (COP 2.5-3.0, needs attention)
- ❌ Red: Critical (COP <2.5, test failed)
- 🔵 Blue: Info (weather, status)
- 🟣 Purple: AI action pending

**Icons**:
- 🤖 AI/Auto functions
- 📈 Performance/COP
- 🌡️ Temperature
- 🌬️ Ventilation
- 💰 Cost/Savings
- 📊 Statistics
- ⚙️ Settings
- 🔔 Notifications

**Animations**:
- Pulsing dot: Active AI processing
- Progress bar: A/B test countdown
- Slide in: New recommendations
- Fade: Historical data

---

## 🚀 Implementation Priority

### Phase 1: Core Display
1. COP card med empirisk modell
2. Auto-Optimizer status
3. Ventilation status
4. Quick Actions grid

### Phase 2: Intelligence
5. A/B-test results
6. Weather integration
7. Learning statistics
8. Confidence indicators

### Phase 3: Polish
9. Notifications
10. Detailed history
11. Settings & privacy
12. Graphs & trends

Total estimerad tid: 3-5 dagar development
