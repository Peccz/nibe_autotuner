# 🤖 Automatic Optimizer Guide

## Översikt

Auto Optimizer är en intelligent motor som **automatiskt** analyserar systemets prestanda och justerar parametrar för optimal drift. Den kombinerar AI-analys med säkra justeringar baserat på verklig data.

## Funktioner

### 1. Automatisk Analys
- Analyserar senaste 72h av data
- Identifierar förbättringsmöjligheter
- Beräknar confidence (0-100%)
- Uppskattar besparing i kr/år

### 2. Säkerhetsmekanismer
- **Tidsregler**: Max 1 ändring per 48h
- **Veckogräns**: Max 3 ändringar per vecka
- **Confidence-tröskel**: Min 70% för auto-apply
- **Safety limits**: Hårdkodade min/max-värden
- **Dry-run mode**: Test utan faktiska ändringar

### 3. Optimerbara Parametrar

| Parameter | ID | Range | Vad den gör |
|-----------|-----|-------|-------------|
| **Värmekurva** | 47007 | 3-10 | Huvudinställning för uppvärmning |
| **Kurvjustering (Offset)** | 47011 | -5 to +5 | Finjustering av innetemperatur |
| **Rumstemperatur** | 47015 | 19-23°C | Direkt temp-inställning |
| **Start kompressor** | 47206 | -400 to -100 DM | När kompressorn startar |

**Safety limits** förhindrar extremvärden!

## Optimeringslogik

### Scenario 1: Låg COP (< 3.0)
```
Nuvarande: COP = 2.8, Värmekurva = 7
Analys: COP för låg, kan sänka kurvan
Action: Värmekurva 7 → 6
Förväntat: COP +0.3, Besparing 1,200 kr/år
Confidence: 80%
Priority: HIGH
```

### Scenario 2: För varmt inne (> 22°C)
```
Nuvarande: Inne = 22.5°C, Offset = 0
Analys: Kan spara energi genom att sänka
Action: Offset 0 → -1
Förväntat: COP +0.1, Besparing 300 kr/år
Confidence: 85%
Priority: MEDIUM
```

### Scenario 3: För kallt inne (< 20°C)
```
Nuvarande: Inne = 19.5°C, Offset = -2
Analys: Komfort prioriteras!
Action: Offset -2 → 0
Förväntat: COP ±0, Besparing 0 kr/år
Confidence: 95%
Priority: CRITICAL
```

### Scenario 4: Högt Delta T (> 8°C)
```
Nuvarande: Delta T = 9.2°C
Analys: Möjligt flödesproblem
Action: Loggar varning (ingen auto-justering av pump än)
```

### Scenario 5: Många cykler (> 20)
```
Nuvarande: 25 cykler på 72h
Analys: Kort-cykling
Action: Loggar varning (ingen auto-justering än)
```

## Användning

### Via API

#### 1. Analysera (dry-run)
```bash
curl -X POST http://192.168.86.34:8502/api/auto-optimize/analyze \
  -H "Content-Type: application/json" \
  -d '{"hours": 72}'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "suggestions_available",
    "actions_suggested": 2,
    "actions_applied": 0,
    "actions": [
      {
        "parameter": "Kurvjustering",
        "current": 0,
        "suggested": -1,
        "reason": "För varmt inne (22.5°C), sänk för energibesparing",
        "confidence": 0.85,
        "priority": "medium",
        "expected_savings": 300
      }
    ]
  }
}
```

#### 2. Kör optimering (apply changes)
```bash
curl -X POST http://192.168.86.34:8502/api/auto-optimize/run \
  -H "Content-Type: application/json" \
  -d '{
    "hours": 72,
    "max_actions": 1,
    "confirm": true
  }'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "optimized",
    "actions_suggested": 2,
    "actions_applied": 1,
    "actions": [...]
  }
}
```

### Via kommandorad (på RPi)

#### Dry-run (endast förslag)
```bash
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --dry-run --hours 72
```

#### Live-körning (applicera ändringar)
```bash
PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --auto-apply --max-actions 1
```

**Parametrar:**
- `--dry-run`: Endast förslag, inga ändringar (default)
- `--auto-apply`: Applicera ändringar automatiskt
- `--hours N`: Analysera senaste N timmar (default: 72)
- `--max-actions N`: Max antal ändringar per körning (default: 1)

### Cron-job för automatisk optimering

**Varje dag kl 03:00:**
```bash
crontab -e
```

Lägg till:
```
0 3 * * * cd /home/peccz/nibe_autotuner && PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --auto-apply --max-actions 1 >> /var/log/nibe-auto-optimizer.log 2>&1
```

**Varje vecka (söndag 03:00):**
```
0 3 * * 0 cd /home/peccz/nibe_autotuner && PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --auto-apply --max-actions 2 >> /var/log/nibe-auto-optimizer.log 2>&1
```

## Säkerhetsinställningar

### Tidsbegränsningar
```python
MIN_HOURS_BETWEEN_CHANGES = 48  # 2 dygn mellan ändringar
MAX_CHANGES_PER_WEEK = 3        # Max 3 ändringar/vecka
```

**Varför?**
- A/B-testet behöver 48h för korrekt utvärdering
- Undviker att systemet "jagar" ett optimum
- Ger tid att observera effekter

### Confidence-tröskel
```python
MIN_CONFIDENCE = 0.70  # 70% minimum
```

**Endast ändringar med >70% confidence appliceras automatiskt**

### Safety Limits
```python
SAFE_LIMITS = {
    '47007': (3.0, 10.0),      # Värmekurva: 3-10
    '47011': (-5.0, 5.0),      # Offset: -5 till +5
    '47015': (190.0, 230.0),   # Rumstemp: 19-23°C
    '47206': (-400.0, -100.0), # Start komp: -400 till -100
}
```

**Även om AI föreslår extremvärden används aldrig värden utanför dessa gränser!**

## Prioriteringssystem

### Priority levels:
1. **CRITICAL** - Komfort (för kallt)
2. **HIGH** - Låg COP (<2.5) eller kritiska problem
3. **MEDIUM** - För varmt, måttligt låg COP (2.5-3.0)
4. **LOW** - Små justeringar

**Auto-optimizer hanterar CRITICAL och HIGH automatiskt (om confidence >70%)**

## Loggning

All ändringar loggas till:
- **Database**: `parameter_changes` tabell
- **Reason**: "Auto Optimizer: [beskrivning]"
- **A/B Testing**: Automatisk utvärdering efter 48h

### Se loggen
```sql
SELECT * FROM parameter_changes
WHERE reason LIKE 'Auto Optimizer:%'
ORDER BY timestamp DESC;
```

## Integration med A/B Testing

1. **Auto Optimizer** gör en ändring
2. Ändringen loggas till `parameter_changes`
3. **A/B Tester** utvärderar efter 48h:
   - Jämför COP, Delta T, Komfort, Kostnad
   - Genererar success score
   - Rekommenderar BEHÅLL/JUSTERA/ÅTERSTÄLL
4. Om **ÅTERSTÄLL** → Auto Optimizer lär sig (future: ML-feedback)

## Framtida förbättringar

### v2.0: Pump-optimering
```python
# Kommande: Automatisk pump-hastighet baserat på Delta T
if delta_t > 8.0:
    increase_pump_speed()  # Öka flöde
elif delta_t < 4.0:
    decrease_pump_speed()  # Minska flöde
```

### v2.1: Maskininlärning
```python
# Lära av A/B-test resultat
# Förbättra confidence-beräkning
# Prediktera resultat innan ändring
```

### v2.2: Väder-prediktion
```python
# Integrera väderprognos
# Proaktiva justeringar innan kyla
```

### v2.3: Smart Schedule
```python
# Olika optimering dag vs natt
# Helg vs vardag
```

## FAQ

**Q: Hur ofta körs Auto Optimizer?**
A: Du bestämmer! Rekommenderat: 1 gång/dag via cron-job.

**Q: Kan den förstöra inställningarna?**
A: Nej! Safety limits förhindrar extremvärden. Värsta scenariot är att du får lite för varmt/kallt, vilket A/B-testet flaggar.

**Q: Vad händer om jag inte gillar en ändring?**
A: Ändra tillbaka manuellt via Quick Actions eller myUplink-appen. A/B-testet utvärderar båda ändringarna.

**Q: Kan jag stänga av Auto Optimizer?**
A: Ja! Ta bara bort cron-jobbet. API:t är alltid tillgängligt men kör aldrig automatiskt.

**Q: Hur vet jag om det fungerar?**
A: Kolla loggen:
```bash
tail -f /var/log/nibe-auto-optimizer.log
```
Eller:
```bash
sqlite3 data/nibe_autotuner.db "SELECT * FROM parameter_changes WHERE reason LIKE 'Auto Optimizer:%'"
```

**Q: Vad om confidence är låg (<70%)?**
A: Ändringen loggas i resultat men appliceras INTE automatiskt. Du kan göra den manuellt via Quick Actions.

**Q: Kan jag justera inställningarna?**
A: Ja! Editera `src/auto_optimizer.py`:
- `MIN_HOURS_BETWEEN_CHANGES`
- `MAX_CHANGES_PER_WEEK`
- `MIN_CONFIDENCE`
- `SAFE_LIMITS`

## Exempel på körning

```bash
$ PYTHONPATH=./src ./venv/bin/python src/auto_optimizer.py --auto-apply

================================================================================
AUTO OPTIMIZER - Starting optimization cycle
================================================================================
Analyzing system for optimization opportunities...
Current metrics: COP=2.85, Delta T=5.8°C, Indoor=22.3°C

Found 2 optimization opportunities:
  1. [MEDIUM] Kurvjustering: 0 → -1
     Reason: För varmt inne (22.3°C), sänk för energibesparing
     Confidence: 85%, Expected savings: 260 kr/år
  2. [HIGH] Värmekurva: 7 → 6
     Reason: COP för låg (2.85), sänk kurva för bättre effektivitet
     Confidence: 78%, Expected savings: 1100 kr/år

Auto-applying up to 1 high-confidence action(s)...
Setting Kurvjustering (47011): 0 → -1
✓ Change applied and logged (ID: 42)
================================================================================
Cycle complete: 2 suggested, 1 applied
================================================================================
```

## Sammanfattning

✅ **Auto Optimizer är:**
- Intelligent och säker
- A/B-testad och verifierad
- Fullt konfigurerbar
- Transparent loggning

⚠️ **Rekommendation:**
Kör i **dry-run mode** första gången för att se förslag innan du aktiverar auto-apply!

🎯 **Optimal användning:**
Daglig cron-job med max 1 ändring/dag, confidence >70%
