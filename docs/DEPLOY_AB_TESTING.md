# 🧪 Deploy A/B Testing Feature

## Vad är nytt?

### #2: Innan/Efter A/B-testning ✅
- **Automatisk utvärdering** av alla parameterändringar
- **48h före/efter jämförelse** med vetenskaplig metod
- **Success score 0-100** för varje ändring
- **Kostnadsbesparing i kr** - Se exakt vad du sparar!
- **Automatisk rekommendation** - Behåll, Justera eller Återställ

### Hur det fungerar:
1. Du ändrar en parameter (t.ex. värmekurva)
2. Systemet lagrar metrics 48h före ändringen
3. Efter 48h jämförs automatiskt metrics före/efter
4. Du får en rapport med:
   - COP-förändring
   - Delta T-förändring
   - Innetemperaturpåverkan
   - Kostnadsbesparing i kr/år
   - Success score och rekommendation

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

### Steg 3: Migrera databas (Lägg till nya tabeller)
```bash
./venv/bin/python src/migrate_db.py
```

Du ska se:
```
Starting database migration...
✓ Migration complete!
✓ Tables: systems, devices, parameters, parameter_readings, parameter_changes, ab_test_results, recommendations, recommendation_results
```

### Steg 4: Restart mobile app
```bash
sudo systemctl restart nibe-mobile.service
sudo systemctl status nibe-mobile.service
```

### Steg 5: Testa!
Öppna i webbläsaren:
```
http://192.168.86.34:8502/ab-testing
```

## 🎯 Användning

### Se alla A/B-test resultat:
Gå till **🧪 A/B Test** i bottom navigation.

### Varje test visar:
- **Parameter som ändrades** (t.ex. Värmekurva 6.0 → 5.5)
- **Success Score** (0-100, färgkodad)
- **COP före/efter** med % förändring
- **Delta T före/efter**
- **Kostnadsbesparing** i kr/dag och kr/år
- **Rekommendation**:
  - ✅ BEHÅLL - Bra resultat!
  - 🤔 NEUTRAL - Marginell effekt
  - ⚠️ JUSTERA - Temperaturen påverkad
  - ❌ ÅTERSTÄLL - Försämring

### Exempel på resultat:
```
📊 Värmekurva: 6.0 → 5.5
🏆 Success Score: 78/100

COP: 3.2 → 3.6 (+12.5%)
Delta T: 5.2°C → 6.1°C (+17.3%)
Inne: 21.5°C → 21.2°C (-0.3°C)

💰 Sparar 6 kr/dag = 2,190 kr/år

✅ BEHÅLL - Mycket bra resultat!
```

## 🔄 Automatisk utvärdering

Ett cron-job kan köras för att automatiskt utvärdera ändringar:

```bash
# Lägg till i crontab
crontab -e

# Kör varje dag kl 03:00
0 3 * * * cd /home/peccz/nibe_autotuner && ./venv/bin/python -c "from ab_tester import ABTester; from analyzer import HeatPumpAnalyzer; ab = ABTester(HeatPumpAnalyzer('data/nibe_autotuner.db')); ab.evaluate_all_pending()"
```

## 📊 API Endpoints

### GET /api/ab-tests
Hämta alla A/B-test resultat
```json
{
  "success": true,
  "data": [{
    "id": 1,
    "parameter_name": "Värmekurva",
    "old_value": 6.0,
    "new_value": 5.5,
    "cop_change_percent": 12.5,
    "cost_savings_per_year": 2190,
    "success_score": 78,
    "recommendation": "✅ BEHÅLL - Mycket bra resultat!"
  }]
}
```

### GET /api/ab-test/<change_id>
Hämta detaljerad info för en specifik ändring

### POST /api/evaluate-pending
Trigga manuell utvärdering av väntande ändringar

## 🐛 Felsökning

### Databasen uppdaterades inte
```bash
# Verifiera att tabellen finns
sqlite3 data/nibe_autotuner.db ".tables"
# Du ska se: ab_test_results
```

### Inga resultat visas
- Det tar 48h efter en ändring innan resultat kan genereras
- Kolla att ändringar loggas i `/changes`

### Mobile app startar inte
```bash
# Kolla loggen
sudo journalctl -u nibe-mobile.service -n 50

# Testa starta manuellt
cd /home/peccz/nibe_autotuner
./venv/bin/python src/mobile_app.py
```

## 🎉 Success!

Nu har du vetenskaplig A/B-testning av alla dina optimeringar!

Varje ändring du gör utvärderas automatiskt och du får konkreta siffror på om den fungerade eller inte.

**No more guessing - only data! 📊**
