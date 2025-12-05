# 🚀 Deploy Smart Optimizer Features

## Vad är nytt?

### #4: Prestanda-score 0-100 ✅
- **Övergripande score** som graderar systemet A+ till F
- **4 komponenter**: COP (40%), Delta T (20%), Komfort (20%), Effektivitet (20%)
- **Färgkodad cirkel** med gradient på dashboard
- **Emoji-betyg** för snabb översikt

### #9: Kostnadssparning i SEK ✅
- **Daglig/Månatlig/Årlig** kostnad i SEK
- **Automatisk jämförelse** mot ooptimerat system (COP 2.5)
- **Sparar X kr/år** visas tydligt
- Baserat på 2 kr/kWh och 1.5 kW kompressor

### #1: AI-optimeringsassistent ✅
- **Top 3 rekommendationer** baserat på nuvarande metrics
- **Prioritet** (HÖG/MEDEL/LÅG) och confidence
- **Förväntad COP-förbättring** och besparing i kr/år
- **Intelligent logik**:
  - COP lågt → Sänk värmekurvan
  - Delta T för högt → Öka pumphastighet (mer flöde)
  - Delta T för lågt → Sänk pumphastighet (mindre flöde)
  - För många cykler → Justera flöde eller kurva
  - Innetemperatur fel → Justera offset

### #10: Quick Actions snabbknappar ✅
- **🥶 Kallt inne** → Höjer offset +1
- **🥵 Varmt inne** → Sänker offset -1
- **⚡ Max COP** → Optimerar för effektivitet
- **🏠 Max komfort** → Justerar för 21°C
- **Direkt kontroll** via myUplink API
- **Automatisk loggning** av alla ändringar för A/B-testning

### Förbättringar i A/B-testning
- **Pump och shunt** kan nu optimeras indirekt genom:
  - Delta T-mätningar (flödesoptimering)
  - Cykel-antal (kort-cykling)
  - COP-förbättring (värmeöverföring)
- **Intelligenta förslag** för cirkulationspump GP1

## 📦 Deployment till RPi

### Steg 1: SSH till RPi
```bash
ssh nibe-rpi
cd /home/peccz/nibe_autotuner
```

### Steg 2: Pull senaste ändringar
```bash
git pull origin main
```

### Steg 3: Ladda tokens (för Quick Actions API)
```bash
# Auth-tokens måste finnas för att Quick Actions ska fungera
ls -lh tokens.json
# Om filen saknas, kör:
# ./venv/bin/python src/auth.py
```

### Steg 4: Restart mobile app
```bash
sudo systemctl restart nibe-mobile.service
sudo systemctl status nibe-mobile.service
```

Du ska se:
```
● nibe-mobile.service - Nibe Autotuner Mobile PWA
   Loaded: loaded
   Active: active (running)
```

### Steg 5: Testa!
Öppna i webbläsaren:
```
http://192.168.86.34:8502/
```

## 🎯 Användning

### Performance Score
- **Visas högst upp** på dashboard med stor färgkodad cirkel
- **Score 0-100** med betyg A+ till F
- **Emoji** för snabb översikt: 🏆 A+, ⭐ A, ✨ B, 👍 C, 😐 D, ⚠️ F

### Kostnadsanalys
- **3 kort**: Per dag, Per månad, Per år
- **Grön spartext** om du sparar jämfört med COP 2.5

### AI-rekommendationer
- **Upp till 3 förslag** baserat på senaste 72h
- **Prioritet**, **Confidence**, **Förväntad vinst**
- **Förklaring** av varför förslaget ges

### Quick Actions
- **4 snabbknappar** för vanliga justeringar
- **Confirmation dialog** innan ändring
- **Visar resultat** (gamla → nya värdet)
- **Loggas automatiskt** för A/B-testning efter 48h

## 📊 API Endpoints

### GET /api/performance-score?hours=72
Hämta prestanda-score
```json
{
  "success": true,
  "data": {
    "total_score": 78,
    "cop_score": 35,
    "delta_t_score": 15,
    "comfort_score": 15,
    "efficiency_score": 13,
    "grade": "B",
    "emoji": "✨"
  }
}
```

### GET /api/cost-analysis?hours=72
Hämta kostnadsanalys
```json
{
  "success": true,
  "data": {
    "daily_cost_sek": 18.5,
    "monthly_cost_sek": 555,
    "yearly_cost_sek": 6753,
    "heating_cost_daily": 12.3,
    "hot_water_cost_daily": 6.2,
    "cop_avg": 3.6,
    "baseline_yearly_cost": 9728,
    "savings_yearly": 2975
  }
}
```

### GET /api/optimization-suggestions?hours=72
Hämta AI-rekommendationer
```json
{
  "success": true,
  "data": [
    {
      "priority": "high",
      "title": "Sänk värmekurvan för bättre COP",
      "description": "Din COP är 2.8 vilket är lågt. Vid -2°C ute kan du sänka värmekurvan.",
      "parameter_name": "Värmekurva",
      "parameter_id": "47007",
      "current_value": 6.0,
      "suggested_value": 5.0,
      "expected_cop_improvement": 0.3,
      "expected_savings_yearly": 1200,
      "confidence": 0.75,
      "reasoning": "Lägre framledningstemp → högre COP..."
    }
  ]
}
```

### POST /api/quick-action/adjust-offset
Justera kurvjustering
```json
Request: {"delta": 1}
Response: {
  "success": true,
  "message": "Kurvjustering ändrad från 0 till 1",
  "old_value": 0,
  "new_value": 1
}
```

### POST /api/quick-action/optimize-efficiency
Optimera för COP
```json
Response: {
  "success": true,
  "message": "Systemet optimerat för maximal COP",
  "changes": [{
    "parameter": "Värmekurva",
    "old_value": 6.0,
    "new_value": 5.5
  }]
}
```

### POST /api/quick-action/optimize-comfort
Optimera för komfort (21°C)
```json
Response: {
  "success": true,
  "message": "Systemet justerat för komfort. Nuvarande temp: 20.2°C, mål: 21°C",
  "changes": [{
    "parameter": "Kurvjustering",
    "old_value": -1,
    "new_value": 0
  }]
}
```

## 🧪 Hur Smart Optimizer integrerar med A/B-testning

All Quick Actions **loggas automatiskt** till `parameter_changes` tabellen:
1. Du trycker på "🥶 Kallt inne"
2. Offset höjs +1 och loggas
3. Efter 48h utvärderar A/B-testern automatiskt:
   - COP före vs efter
   - Delta T före vs efter
   - Innetemperatur före vs efter
   - Success score 0-100
   - Rekommendation: BEHÅLL/JUSTERA/ÅTERSTÄLL

Detta gäller **ÄVEN pump/shunt-ändringar**! Även om du inte kan läsa flödet direkt, så:
- **Ändrar du pumphastighet** → Delta T påverkas → A/B-testern ser förändringen
- **Kort-cykling uppstår** → Antal cykler ökar → A/B-testern flaggar problemet
- **COP förbättras** → Score går upp → A/B-testern rekommenderar BEHÅLL

## 🐛 Felsökning

### Performance score visas inte
```bash
# Testa API:t direkt
curl http://localhost:8502/api/performance-score?hours=72
```

### Quick Actions fungerar inte
```bash
# Kolla att tokens finns
ls -lh tokens.json

# Kolla loggen
sudo journalctl -u nibe-mobile.service -f

# Testa auth manuellt
./venv/bin/python src/auth.py
```

### AI ger inga förslag
- Normal! Om allt är optimalt (score >80) ges inga förslag
- Prova ändra analysperiod (längre eller kortare än 72h)

### CSS/JS ändras inte
```bash
# Force-refresh i webbläsaren: Ctrl+Shift+R
# Eller rensa service worker cache
```

## 🎉 Success!

Nu har du ett **intelligent optimeringssystem** med:
- ✅ Prestanda-score som visar hur bra systemet mår
- ✅ Kostnadsspårning i SEK
- ✅ AI-assistent som ger konkreta förbättringsförslag
- ✅ Snabbknappar för vanliga justeringar
- ✅ Automatisk A/B-testning av ALLA ändringar

**Nästa steg**: Låt systemet köra i några veckor och samla data. A/B-testerna kommer visa vilka optimeringar som faktiskt fungerar! 📊
