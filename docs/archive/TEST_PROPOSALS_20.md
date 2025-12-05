# 20 Optimeringsförslag för A/B-testning

**Genererad:** 2025-12-03 20:35 CET
**Baserad på systemdata:** Senaste 72h

---

## 📊 NUVARANDE SYSTEMSTATUS

### Prestanda (72h medel)
- **COP:** 3.03 (Bra, men kan förbättras)
- **Degree Minutes:** +81 (Något för varmt)
- **Delta T (aktiv):** 4.9°C (Under optimum 5-8°C)
- **Inomhustemp:** 21.5°C (Något över måltemperatur 21°C)
- **Utomhustemp:** 4.5°C (Milt väder)
- **Framledning:** 32.6°C
- **Returledning:** 28.4°C
- **Kompressor:** 30 Hz (Låg frekvens)

### Aktuella parametrar
- **Heating Curve (47007):** 7.0
- **Offset (47011):** -3.0 ⚠️ (Mycket låg!)
- **Room Temp Setpoint (47015):** 20.0°C
- **Min Supply Temp (47020):** 15.0°C
- **Start Compressor DM (47206):** -200
- **Start Temp Exhaust (47538):** 24.0°C
- **Increased Ventilation (50005):** 0 (Normal)

### Analys
- ✅ **COP är bra** (3.03) men kan optimeras ytterligare
- ⚠️ **Offset är mycket låg (-3)** - kan vara orsaken till låg Delta T
- ⚠️ **Delta T under optimum** (4.9 vs 5-8°C) - indikerar ineffektiv värmeöverföring
- ⚠️ **Degree Minutes positiva** (+81) - systemet är något för varmt
- ⚠️ **Inomhustemp över mål** (21.5 vs 21.0°C) - energislöseri
- ✅ **Mild vinterperiod** (4.5°C) - bra förutsättningar för tester

---

## 🎯 20 OPTIMERINGSFÖRSLAG

### Kategori 1: Kurvjusteringar (högsta prioritet)

#### Test #1: Öka Offset från -3 till -2
- **Parameter:** Offset (47011): -3 → -2
- **Hypotes:** Nuvarande offset är extremt låg. Genom att öka med 1 steg kan vi förbättra Delta T och effektivitet utan att göra det för varmt
- **Förväntat resultat:** Delta T ökar till 5.5-6.0°C, COP förbättras till 3.15-3.20
- **Kostnadsbesparing:** 50-70 kr/månad
- **Konfidens:** 85%
- **Risk:** Låg (offset är redan mycket låg)
- **Tidsram:** 48h test
- **Säsong:** Bra nu (milt väder)

#### Test #2: Öka Offset från -3 till -1
- **Parameter:** Offset (47011): -3 → -1
- **Hypotes:** Mer aggressiv ökning för snabbare resultat, men högre risk
- **Förväntat resultat:** Delta T ökar till 6.0-6.5°C, COP förbättras till 3.20-3.25
- **Kostnadsbesparing:** 80-100 kr/månad
- **Konfidens:** 70%
- **Risk:** Medel (större hopp, kan göra för varmt)
- **Tidsram:** 48h test
- **Säsong:** Bra nu

#### Test #3: Sänk Heating Curve från 7.0 till 6.5
- **Parameter:** Heating Curve (47007): 7.0 → 6.5
- **Hypotes:** I milt väder (4.5°C) behövs inte lika brant kurva
- **Förväntat resultat:** COP förbättras 5-8%, inomhustemp sjunker till 21.0-21.2°C
- **Kostnadsbesparing:** 80-120 kr/månad
- **Konfidens:** 75%
- **Risk:** Medel (kan göra något kallare)
- **Tidsram:** 96h test (längre för att säkerställa stabilitet)
- **Säsong:** Perfekt för milt väder >3°C

#### Test #4: Sänk Heating Curve från 7.0 till 6.0
- **Parameter:** Heating Curve (47007): 7.0 → 6.0
- **Hypotes:** Mer aggressiv sänkning för maximalt COP-lyft
- **Förväntat resultat:** COP +10-12%, inomhustemp sjunker till 20.5-21.0°C
- **Kostnadsbesparing:** 120-160 kr/månad
- **Konfidens:** 60%
- **Risk:** Hög (stor förändring, kan bli för kallt i kallare väder)
- **Tidsram:** 96h test
- **Säsong:** Endast vid väder >5°C

#### Test #5: Kombinera Offset +1 och Curve -0.5
- **Parameter:** Offset (47011): -3 → -2, Curve (47007): 7.0 → 6.5
- **Hypotes:** Dubbel optimering för maximal effekt
- **Förväntat resultat:** COP +8-10%, optimalt Delta T
- **Kostnadsbesparing:** 100-140 kr/månad
- **Konfidens:** 70%
- **Risk:** Medel (två ändringar samtidigt)
- **Tidsram:** 96h test
- **Säsong:** Bra nu

---

### Kategori 2: Temperaturinställningar

#### Test #6: Höj Room Temp Setpoint från 20 till 20.5°C
- **Parameter:** Room Temp Setpoint (47015): 20.0 → 20.5°C
- **Hypotes:** Nuvarande setpoint (20°C) är lägre än faktisk temp (21.5°C), indikerar obalans
- **Förväntat resultat:** Bättre matchning mellan setpoint och faktisk temp
- **Kostnadsbesparing:** Ingen direkt, men förbättrad reglering
- **Konfidens:** 65%
- **Risk:** Låg
- **Tidsram:** 48h test
- **Säsong:** Året runt

#### Test #7: Sänk Room Temp Setpoint från 20 till 19.5°C
- **Parameter:** Room Temp Setpoint (47015): 20.0 → 19.5°C
- **Hypotes:** Kompensera för att faktisk temp är högre än setpoint
- **Förväntat resultat:** Faktisk temp sjunker till 21.0°C, energibesparing
- **Kostnadsbesparing:** 60-80 kr/månad
- **Konfidens:** 70%
- **Risk:** Låg
- **Tidsram:** 48h test
- **Säsong:** Året runt

#### Test #8: Öka Min Supply Temp från 15 till 18°C
- **Parameter:** Min Supply Temp (47020): 15 → 18°C
- **Hypotes:** Högre minimum kan förbättra Delta T vid låg drift
- **Förväntat resultat:** Delta T förbättras vid låglast
- **Kostnadsbesparing:** 30-50 kr/månad
- **Konfidens:** 60%
- **Risk:** Låg
- **Tidsram:** 48h test
- **Säsong:** Bättre vår/höst

#### Test #9: Sänk Min Supply Temp från 15 till 12°C
- **Parameter:** Min Supply Temp (47020): 15 → 12°C
- **Hypotes:** Lägre minimum tillåter mer effektiv drift i milt väder
- **Förväntat resultat:** COP +2-3% i milt väder
- **Kostnadsbesparing:** 40-60 kr/månad
- **Konfidens:** 65%
- **Risk:** Medel (kan ge sämre komfort)
- **Tidsram:** 72h test
- **Säsong:** Endast milt väder >5°C

---

### Kategori 3: Kompressor-optimering

#### Test #10: Sänk Start Compressor från -200 till -250 DM
- **Parameter:** Start Compressor (47206): -200 → -250
- **Hypotes:** Låt byggnaden svalna mer innan kompressor startar = längre cykler = bättre COP
- **Förväntat resultat:** Färre starter, högre COP per cykel, +3-5% total COP
- **Kostnadsbesparing:** 50-80 kr/månad
- **Konfidens:** 75%
- **Risk:** Medel (kan ge sämre komfort)
- **Tidsram:** 96h test
- **Säsong:** Bra nu

#### Test #11: Höj Start Compressor från -200 till -150 DM
- **Parameter:** Start Compressor (47206): -200 → -150
- **Hypotes:** Tidigare start = jämnare temperatur = bättre komfort
- **Förväntat resultat:** Förbättrad komfort, eventuellt något sämre COP (-2%)
- **Kostnadsbesparing:** -30 kr/månad (kostnad för komfort)
- **Konfidens:** 70%
- **Risk:** Låg
- **Tidsram:** 72h test
- **Säsong:** Året runt

#### Test #12: Extremtest: Start Compressor -300 DM
- **Parameter:** Start Compressor (47206): -200 → -300
- **Hypotes:** Maximera cykellängd för maximal effektivitet
- **Förväntat resultat:** COP +5-8%, men risk för komfortproblem
- **Kostnadsbesparing:** 80-120 kr/månad
- **Konfidens:** 50%
- **Risk:** Hög (kan bli för kallt)
- **Tidsram:** 96h test
- **Säsong:** Endast milt väder >6°C

---

### Kategori 4: Ventilationsoptimering

#### Test #13: Aktivera Increased Ventilation (0 → 1)
- **Parameter:** Increased Ventilation (50005): 0 → 1
- **Hypotes:** Ökad ventilation ger torrare inomhusluft men kallare frånluft = lägre COP
- **Förväntat resultat:** Bättre luftkvalitet, COP -5-10%
- **Kostnadsbesparing:** -80 till -120 kr/månad (kostnad)
- **Konfidens:** 80%
- **Risk:** Låg (lätt att reversera)
- **Tidsram:** 48h test
- **Säsong:** Vinter när fukt är problem

#### Test #14: Sänk Start Temp Exhaust från 24 till 20°C
- **Parameter:** Start Temp Exhaust (47538): 24 → 20°C
- **Hypotes:** Tidigare start av frånluftsvärmning = mer värmeutvinning
- **Förväntat resultat:** COP +3-5% genom bättre värmeutvinning
- **Kostnadsbesparing:** 50-80 kr/månad
- **Konfidens:** 70%
- **Risk:** Låg
- **Tidsram:** 72h test
- **Säsong:** Kallt väder <5°C

#### Test #15: Höj Start Temp Exhaust från 24 till 28°C
- **Parameter:** Start Temp Exhaust (47538): 24 → 28°C
- **Hypotes:** Vänta med frånluftsvärmning tills det verkligen behövs = energibesparing
- **Förväntat resultat:** COP +2-4% i milt väder
- **Kostnadsbesparing:** 30-60 kr/månad
- **Konfidens:** 65%
- **Risk:** Låg
- **Tidsram:** 72h test
- **Säsong:** Milt väder >3°C

---

### Kategori 5: Kombinationstester (avancerat)

#### Test #16: Optimering för Max COP (Multi-parameter)
- **Parametrar:**
  - Offset: -3 → -2
  - Curve: 7.0 → 6.5
  - Start Compressor: -200 → -250
  - Start Temp Exhaust: 24 → 20
- **Hypotes:** Kombinera de bästa enkeltesterna för maximal effekt
- **Förväntat resultat:** COP +12-15%, 150-200 kr/månad
- **Konfidens:** 55%
- **Risk:** Hög (många ändringar samtidigt, svårt att isolera effekter)
- **Tidsram:** 168h (1 vecka)
- **Säsong:** Milt väder

#### Test #17: Optimering för Max Komfort
- **Parametrar:**
  - Offset: -3 → -1
  - Room Temp: 20 → 20.5
  - Start Compressor: -200 → -150
- **Hypotes:** Prioritera jämn temperatur över effektivitet
- **Förväntat resultat:** Bättre komfort, COP -2-3%, kostnad +40 kr/månad
- **Konfidens:** 70%
- **Risk:** Låg
- **Tidsram:** 96h
- **Säsong:** Året runt

#### Test #18: Balansprofil (Komfort + Effektivitet)
- **Parametrar:**
  - Offset: -3 → -2
  - Curve: 7.0 → 6.5
  - Room Temp: 20 → 20.5
- **Hypotes:** Hitta perfekt balans mellan komfort och effektivitet
- **Förväntat resultat:** COP +5-7%, god komfort, 80-100 kr/månad
- **Konfidens:** 75%
- **Risk:** Medel
- **Tidsram:** 96h
- **Säsong:** Året runt

---

### Kategori 6: Extremtester (experimentella)

#### Test #19: Minimalistisk profil
- **Parametrar:**
  - Curve: 7.0 → 5.5
  - Offset: -3 → 0
  - Room Temp: 20 → 19
  - Min Supply: 15 → 12
- **Hypotes:** Drastisk sänkning för maximal effektivitet
- **Förväntat resultat:** COP +15-20%, men risk för dålig komfort
- **Konfidens:** 40%
- **Risk:** Mycket hög
- **Tidsram:** 96h (avbryt om <19.5°C inomhus)
- **Säsong:** Endast vår när >8°C ute

#### Test #20: Återställningstest (Baseline verification)
- **Parametrar:** Återställ ALLA till fabriksinställningar
  - Curve: 7.0 → 9.0 (standard)
  - Offset: -3 → 0 (standard)
  - Allt annat till default
- **Hypotes:** Verifiera att våra ändringar faktiskt förbättrat systemet
- **Förväntat resultat:** Sämre COP än nuvarande, bekräftar att optimeringar fungerat
- **Konfidens:** 90%
- **Risk:** Medel (tillfälligt sämre prestanda)
- **Tidsram:** 48h
- **Säsong:** Året runt
- **Syfte:** Etablera ny baseline för jämförelse

---

## 📈 RANGORDNINGSMETOD

### Viktning av faktorer

För att rangordna testerna används följande formel:

```
Priority Score = (Expected_COP_Gain × 0.30) +
                 (Cost_Savings × 0.25) +
                 (Confidence × 0.20) +
                 (Safety × 0.15) +
                 (Simplicity × 0.10)
```

Där:
- **Expected_COP_Gain:** 0-100 (% förbättring × 10)
- **Cost_Savings:** 0-100 (kr/månad / 2)
- **Confidence:** 0-100 (konfidens i %)
- **Safety:** 0-100 (100 - risk × 20)
- **Simplicity:** 0-100 (100 för single-parameter, 50 för 2-3, 0 för 4+)

### Riskbedömning

- **Låg risk:** Kan köras närsomhelst, lätt att reversera
- **Medel risk:** Kräver övervakning, kör vid mild väderlek
- **Hög risk:** Endast med användarövervakning, kan påverka komfort
- **Mycket hög risk:** Experimentell, kör endast vid gynnsamt väder

### Säsongsanpassning

- **Vinter (<3°C):** Endast lågrisk-tester, fokus på ventilation
- **Vår/Höst (3-10°C):** Bästa tiden för de flesta tester
- **Sommar (>10°C):** Begränsat värde, systemet kör minimalt

---

## 🎯 REKOMMENDERAD ORDNING

Baserat på rangordningsmetoden, här är den optimala testordningen:

### Fas 1: Grundoptimering (Vecka 1-2)
1. **Test #1:** Offset -3 → -2 (Högsta prioritet, låg risk)
2. **Test #7:** Room Temp 20 → 19.5°C
3. **Test #14:** Start Temp Exhaust 24 → 20°C

### Fas 2: Kurvjustering (Vecka 3-4)
4. **Test #3:** Heating Curve 7.0 → 6.5
5. **Test #10:** Start Compressor -200 → -250

### Fas 3: Finoptimering (Vecka 5-6)
6. **Test #5:** Kombinera Offset +1 och Curve -0.5
7. **Test #9:** Min Supply Temp 15 → 12°C
8. **Test #15:** Start Temp Exhaust 24 → 28°C

### Fas 4: Balanstest (Vecka 7-8)
9. **Test #18:** Balansprofil
10. **Test #11:** Start Compressor -200 → -150 (komfort)

### Fas 5: Avancerade tester (Vecka 9-12)
11. **Test #2:** Offset -3 → -1 (aggressiv)
12. **Test #4:** Heating Curve 7.0 → 6.0
13. **Test #16:** Max COP Multi-parameter

### Fas 6: Extremtester (Våren, >8°C)
14. **Test #12:** Start Compressor -300
15. **Test #19:** Minimalistisk profil

### Fas 7: Verifieringstester (Valfritt)
16. **Test #20:** Baseline verification
17. **Test #13:** Increased Ventilation (vinterfukt)
18. **Test #17:** Max Komfort profil

### Fas 8: Okategoriserade (Lägre prioritet)
19. **Test #6:** Room Temp 20 → 20.5°C
20. **Test #8:** Min Supply 15 → 18°C

---

## 📊 FÖRVÄNTADE RESULTAT

### Sammanlagd potential (om alla lyckade tester implementeras)

**Optimistiskt scenario:**
- COP-förbättring: +15-20%
- Årlig besparing: 2,000-2,500 kr
- Payback-tid för Premium Manage: <1 år

**Realistiskt scenario:**
- COP-förbättring: +8-12%
- Årlig besparing: 1,200-1,600 kr
- Payback-tid för Premium Manage: 1-1.5 år

**Konservativt scenario:**
- COP-förbättring: +5-8%
- Årlig besparing: 800-1,000 kr
- Payback-tid för Premium Manage: 1.5-2 år

---

## ⚠️ SÄKERHETSREGLER

### Automatiska avbrott
Systemet ska automatiskt avbryta ett test om:
- Inomhustemp < 19.5°C i >2h
- Inomhustemp > 23.0°C i >2h
- COP < 2.0 i >4h
- Degree Minutes < -500 i >4h
- Kompressor körs >90% av tiden i 24h

### Manuell övervakning
Användaren ska granska:
- Första 24h av varje test
- Daglig temperaturlogg
- COP-trend

### Vintervarningar
Vid utomhustemp < 0°C:
- Endast test #1, #7, #14 tillåtna
- Dubbla säkerhetsmarginaler
- Ingen automatisk start av högrisktester

---

**Nästa steg:** Implementera rangordningsalgoritmen och lägg till dessa tester i databasen!
