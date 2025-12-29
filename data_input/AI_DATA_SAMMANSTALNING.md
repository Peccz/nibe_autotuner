# Värmepump Data Sammanställning
## AI-optimerad dokumentation - Skapad 2025-12-18

---

## ÖVERSIKT

Detta dataset innehåller historisk driftdata från en bergvärmepump med ventilationsaggregat (NIBE eller liknande system) under perioden **november 2024 - december 2025**.

**Antal datafiler:** 33 CSV-filer
**Totalt antal parametrar:** 33 unika mätvärden
**Datumintervall:** 2025-11-17 till 2025-12-18
**Tidsupplösning:** Varierar per parameter (från minuter till timmar)
**Dataformat:** CSV med semikolonavgränsare (;)

---

## PARAMETRAR OCH SENSORER

### TEMPERATURMÄTNINGAR

#### Värmepumpsystem
1. **Calculated supply climate system 1** (`history-export.csv`, `history-export(9).csv`, `history-export(10).csv`)
   - Enhet: °C
   - ID: Varierar
   - Beskrivning: Beräknad framledningstemperatur för värmesystem 1

2. **Current temperature system 1** (`history-export(5).csv`, `history-export(6).csv`, `history-export(12).csv`)
   - Enhet: °C
   - Beskrivning: Aktuell temperatur i värmesystem 1

3. **Supply line (BT2)** (`history-export(30).csv`)
   - Enhet: °C
   - ID: 40008
   - Beskrivning: Tillförselstemperatur från värmepumpen

4. **Return line (BT3)** (`history-export(27).csv`)
   - Enhet: °C
   - ID: 40012
   - Beskrivning: Returtemperatur till värmepumpen

5. **Discharge (BT14)** (`history-export(8).csv`, `history-export(14).csv`)
   - Enhet: °C
   - ID: 40019
   - Beskrivning: Kompressorns uteblåsningstemperatur

6. **Evaporator (BT16)** (`history-export(15).csv`)
   - Enhet: °C
   - ID: 40020
   - Beskrivning: Förångarens temperatur

7. **Liquid line (BT15)** (`history-export(22).csv`)
   - Enhet: °C
   - ID: 40019
   - Beskrivning: Vätskeledningstemperatur

#### Varmvatten
8. **Hot water charging (BT6)** (`history-export(20).csv`)
   - Enhet: °C
   - ID: 40014
   - Beskrivning: Varmvattentemperatur vid laddning

9. **Hot water top (BT7)** (`history-export(21).csv`)
   - Enhet: °C
   - ID: 40013
   - Beskrivning: Varmvattentemperatur i toppen av tanken

#### Ventilationssystem
10. **Exhaust air (AZ30-BT20)** (`history-export(16).csv`)
    - Enhet: °C
    - Beskrivning: Frånluftstemperatur från ventilationssystemet

11. **Extract air (AZ30-BT21)** (`history-export(17).csv`)
    - Enhet: °C
    - ID: 40026
    - Beskrivning: Tilluft/utomhusluft temperatur för ventilationen

#### Miljödata
12. **Outdoor temperature** (`history-export(26).csv`)
    - Enhet: °C
    - ID: 40004
    - Beskrivning: Utomhustemperatur

13. **Room temperature (BT50)** (`history-export(28).csv`, `history-export(29).csv`)
    - Enhet: °C
    - ID: 40033
    - Beskrivning: Rumstemperatur

---

### ELEKTRISKA MÄTNINGAR

14. **Current (BE1)** (`history-export(1).csv`)
    - Enhet: Ampere (A)
    - Beskrivning: Strömförbrukning fas 1

15. **Current (BE2)** (`history-export(2).csv`)
    - Enhet: Ampere (A)
    - Beskrivning: Strömförbrukning fas 2

16. **Current (BE3)** (`history-export(3).csv`)
    - Enhet: Ampere (A)
    - Beskrivning: Strömförbrukning fas 3

17. **Current compressor frequency** (`history-export(11).csv`)
    - Enhet: Hz
    - Beskrivning: Kompressorns driftsfrekvens

---

### SYSTEMSTATUS OCH STYRNING

18. **Degree minutes** (`history-export(7).csv`, `history-export(13).csv`)
    - Enhet: Gradminuter
    - Beskrivning: Ackumulerad temperaturavvikelse (används för styrning)

19. **Fan speed exhaust air** (`history-export(18).csv`)
    - Enhet: %
    - ID: 50221
    - Beskrivning: Fläkthastighet för frånluft i procent

20. **Heating medium pump speed (GP1)** (`history-export(19).csv`)
    - Enhet: %
    - ID: 43437
    - Beskrivning: Värmemediumpumpens hastighet i procent

---

### DRIFTTID OCH STATISTIK

21. **Number of compressor starts** (`history-export(23).csv`)
    - Enhet: Antal
    - ID: 43416
    - Beskrivning: Totalt antal kompressorstarter
    - Värde: 5959 (2025-11-17) → 6184 (2025-12-18)
    - Ökning: 225 starter under perioden

22. **Operating time (Oper. time)** (`history-export(24).csv`)
    - Enhet: Timmar
    - ID: 43420
    - Beskrivning: Total drifttid för värmepumpen
    - Värde: 11825 h (2025-11-17) → 12410 h (2025-12-18)
    - Ökning: 585 timmar under mätperioden

23. **Operating time hot water** (`history-export(25).csv`)
    - Enhet: Timmar
    - ID: 43424
    - Beskrivning: Drifttid för varmvattenproduktion
    - Värde: 2758 h (2025-11-18) → 2866 h (2025-12-18)
    - Ökning: 108 timmar under perioden

24. **Time factor add heat** (`history-export(31).csv`, `history-export(32).csv`)
    - Enhet: Dimensionslös
    - ID: 43081
    - Beskrivning: Tidsfaktor för tillskottsvärme

---

## FILSTRUKTUR

Varje CSV-fil följer samma struktur:

```csv
timestamp;[Parameter namn][Enhet][ID];
2025-12-18T09:00:00+00:00;värde;
```

**Format:**
- **Kolumn 1:** ISO 8601 tidsstämpel med tidszon (UTC+00:00)
- **Kolumn 2:** Mätvärde (numeriskt)
- **Kolumn 3:** Tom (avslutande semikolon)

**Header-format:**
```
timestamp;[Parameterbeskrivning][Enhet][Parameter-ID];
```

---

## DATAKVALITET OCH OBSERVATIONER

### Tidsupplösning
- **Högfrekvent data:** Vissa parametrar loggas var 1-15:e minut (t.ex. temperaturer)
- **Lågfrekvent data:** Vissa parametrar loggas varje timme eller vid statusändring (t.ex. drifttid)

### Felaktiga värden
- Vissa sensorer visar temporära värden som **-15.6°C** eller liknande onaturligt låga värden
- Detta indikerar troligen sensorfel eller ingen giltig avläsning
- Exempel: Evaporator (BT16) och Extract air (AZ30-BT21) visar sådana värden

### Tidsformat-variationer
- De flesta tidsstämplar: ISO 8601 format (`2025-12-18T09:00:00+00:00`)
- Några enstaka poster: JavaScript Date format (`Thu Dec 18 2025 09:01:01 GMT+0100`)

---

## SYSTEMANALYS

### Värmepumpens prestanda
Baserat på data kan följande beräknas:

**Mätperiod:** ca 1 månad (2025-11-17 till 2025-12-18)

**Kompressorstarter:**
- Total: 225 starter under perioden
- Genomsnitt: ca 7.5 starter per dag

**Drifttid:**
- Total värmepumpdrift: 585 timmar
- Varmvattendrift: 108 timmar (18.5% av total drifttid)
- Uppvärming: ca 477 timmar (81.5%)

**Drift per dag:**
- Genomsnittlig drifttid: ca 19.5 timmar/dag
- Indikerar hög värmebehov (vinterperiod)

### Temperaturdata
**Utomhustemperatur:**
- Min: ca -9.4°C
- Max: ca +9.0°C
- Indikerar vinterförhållanden med varierande väder

**Inomhustemperatur:**
- Varieringintervall: 20.1 - 22.6°C
- Måltemperatur verkar vara ca 21°C

---

## ANVÄNDNINGSOMRÅDEN

Detta dataset kan användas för:

1. **Energianalys**
   - Beräkna värmepumpens COP (Coefficient of Performance)
   - Analysera energiförbrukning vs utomhustemperatur
   - Identifiera optimeringsmöjligheter

2. **Prediktiv underhåll**
   - Förutsäga när service behövs baserat på drifttid
   - Identifiera onormala driftsmönster
   - Övervaka kompressorstarter

3. **Machine Learning**
   - Träna modeller för energiprediktion
   - Optimera styrstrategi baserat på väderdata
   - Anomalidetektion

4. **Systemoptimering**
   - Analysera pumphastigheters påverkan
   - Optimera varmvattenproduktion
   - Balansera ventilationssystemet

---

## TEKNISKA DETALJER

**System:** Troligen NIBE bergvärmepump med ventilationsaggregat
**Sensorer:** Standardkonfiguration med BT-prefixade temperatursensorer
**Styrning:** Gradminutbaserad reglering
**Energimätning:** Trefas elektrisk mätning (BE1, BE2, BE3)

**Filer med dubbletter/varianter:**
- Calculated supply climate system 1 finns i 3 filer
- Current temperature system 1 finns i 3 filer
- Degree minutes finns i 2 filer
- Discharge (BT14) finns i 2 filer
- Room temperature (BT50) finns i 2 filer
- Time factor add heat finns i 2 filer

Detta kan indikera:
- Backup-exporter
- Olika exporttillfällen
- Separata loggningssystem för samma sensor

---

## SNABBFAKTA FÖR AI-ANALYS

| Egenskap | Värde |
|----------|-------|
| Antal datafiler | 33 |
| Antal unika parametrar | ~24 |
| Tidsperiod | 2025-11-17 till 2025-12-18 |
| Huvudsystem | Bergvärmepump + Ventilation |
| Datapunkter | >30,000 (uppskattning) |
| Dataformat | CSV (semikolonavgränsare) |
| Tidszon | UTC+00:00 (med enstaka GMT+0100) |
| Huvudsaklig användning | Uppvärmning + Varmvatten |

---

## DATAFILER MAPPNING

| Filnamn | Parameter | Enhet |
|---------|-----------|-------|
| history-export.csv | Calculated supply climate system 1 | °C |
| history-export(1).csv | Current (BE1) | A |
| history-export(2).csv | Current (BE2) | A |
| history-export(3).csv | Current (BE3) | A |
| history-export(4).csv | Current compressor frequency | Hz |
| history-export(5).csv | Current temperature system 1 | °C |
| history-export(6).csv | Current temperature system 1 | °C |
| history-export(7).csv | Degree minutes | gradmin |
| history-export(8).csv | Discharge (BT14) | °C |
| history-export(9).csv | Calculated supply climate system 1 | °C |
| history-export(10).csv | Calculated supply climate system 1 | °C |
| history-export(11).csv | Current compressor frequency | Hz |
| history-export(12).csv | Current temperature system 1 | °C |
| history-export(13).csv | Degree minutes | gradmin |
| history-export(14).csv | Discharge (BT14) | °C |
| history-export(15).csv | Evaporator (BT16) | °C |
| history-export(16).csv | Exhaust air (AZ30-BT20) | °C |
| history-export(17).csv | Extract air (AZ30-BT21) | °C |
| history-export(18).csv | Fan speed exhaust air | % |
| history-export(19).csv | Heating medium pump speed (GP1) | % |
| history-export(20).csv | Hot water charging (BT6) | °C |
| history-export(21).csv | Hot water top (BT7) | °C |
| history-export(22).csv | Liquid line (BT15) | °C |
| history-export(23).csv | Number of compressor starts | antal |
| history-export(24).csv | Operating time | timmar |
| history-export(25).csv | Operating time hot water | timmar |
| history-export(26).csv | Outdoor temperature | °C |
| history-export(27).csv | Return line (BT3) | °C |
| history-export(28).csv | Room temperature (BT50) | °C |
| history-export(29).csv | Room temperature (BT50) | °C |
| history-export(30).csv | Supply line (BT2) | °C |
| history-export(31).csv | Time factor add heat | - |
| history-export(32).csv | Time factor add heat | - |

---

## EXEMPEL PÅ DATAFORMAT

```csv
timestamp;[Outdoor temperature][°C][40004];
2025-11-18T00:13:09+00:00;-5.9;
2025-11-18T00:32:40+00:00;-6.4;
2025-11-18T00:57:17+00:00;-6.9;
```

```csv
timestamp;[Number of compressor starts][][43416];
2025-11-17T23:44:08+00:00;5959;
2025-11-18T01:07:50+00:00;5960;
2025-11-18T02:26:14+00:00;5961;
```

```csv
timestamp;[Fan speed exhaust air][%][50221];
2025-12-01T06:37:16+00:00;100;
2025-12-01T06:57:01+00:00;50;
2025-12-05T17:54:16+00:00;50;
```

---

**Skapad:** 2025-12-18
**Syfte:** AI-optimerad dokumentation för analys av värmepumpdata
**Format:** Markdown (lättläst för både människor och AI)
