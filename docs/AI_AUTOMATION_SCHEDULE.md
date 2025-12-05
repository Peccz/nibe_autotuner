# AI Automation Schedule

Komplett schema för automatisk drift av Nibe Autotuner med AI-agent.

## Översikt

Systemet kör tre automatiska processer per dag:

1. **05:00** - Morgonanalys (genererar testförslag)
2. **06:00** - Morgonoptimering (ventilation + pump)
3. **19:00** - Kvällsoptimering (ventilation + pump)

---

## 1. Morgonanalys (05:00)

**Skript:** `scripts/run_morning_analysis.sh`

### Vad den gör:
- Analyserar senaste 24h data
- Genererar prioriterad lista med testförslag
- Lagrar förslag i databas
- Visar förslag i GUI under "AI" fliken

### Exempel output:
```
GENERATED 3 TEST PROPOSALS
==========================================================================
1. [HIGH] curve_offset
   Hypothesis: Reducing curve offset will maintain comfort while improving COP
   Expected: +0.1 COP (~3%), saves ~50 kr/month
   Confidence: 85%

2. [MEDIUM] heating_curve
   Hypothesis: Lower heating curve improves efficiency in mild weather
   Expected: +0.15 COP (~5%), saves ~80 kr/month
   Confidence: 72%

3. [LOW] increased_ventilation
   Hypothesis: Reduced ventilation keeps exhaust warmer
   Expected: +0.2 COP (~7%), saves ~100 kr/month
   Confidence: 68%
```

### Förslag-prioritering:
AI-agenten rankordnar tester baserat på:
1. **Säkerhet** - Inga risker för komfort eller systemet
2. **Förväntat resultat** - Hur mycket kan vi förbättra?
3. **Konfidens** - Hur säker är AI:n?
4. **Väder** - Passar testet nuvarande förhållanden?
5. **Historik** - Vad har fungerat tidigare?

### Test-livscykel:
```
Proposed → Pending → Active (48h) → Completed → Result stored
```

---

## 2. Morgonoptimering (06:00)

**Skript:** `scripts/run_twice_daily_optimization.sh`

### Vad den gör:

#### Steg 1: Ventilationsoptimering
- Kontrollerar utomhustemperatur
- Väljer optimal ventilationsstrategi:
  - **>10°C**: WARM (normal ventilation)
  - **0-10°C**: MILD (något reducerad)
  - **-10-0°C**: COLD (reducerad)
  - **<-10°C**: EXTREME_COLD (minimerad)
- Uppdaterar 3 ventilationsparametrar

#### Steg 2: Pumpoptimering
- **Med AI-agent** (om ANTHROPIC_API_KEY finns):
  - Claude analyserar senaste 12h
  - Fattar beslut: adjust/hold/investigate
  - Tillämpar ändringar om konfidens >70%
  - Loggar resonemang i databas

- **Utan AI-agent** (regelbaserad):
  - Auto-Optimizer kör standard logic
  - Max 1 ändring per 48h
  - Fokus på säkerhet

### Morgon-fokus:
- Förbered för dagsförbrukning
- Optimera för komfort (folk vaknar)
- Ta hänsyn till väder-prognos

---

## 3. Kvällsoptimering (19:00)

**Skript:** `scripts/run_twice_daily_optimization.sh`

### Vad den gör:
Samma som morgonoptimering, men med kvällsfokus:

### Kväll-fokus:
- Förbered för nattförbrukning
- Lägre elpris nattetid → mer aggressiv optimering
- Mindre risk (folk sover, mindre störning)

---

## Installation

### 1. Uppdatera databas

Skapa nya tabeller för AI-funktioner:

```bash
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python -c "
from models import init_db
engine = init_db('sqlite:///./data/nibe_autotuner.db')
print('✓ Database updated with AI tables')
"
```

### 2. Installera anthropic (för AI-agent)

```bash
./venv/bin/pip install anthropic
```

### 3. Konfigurera API-nyckel (valfritt)

**Endast om du vill använda AI-agent istället för regelbaserad:**

```bash
nano .env
```

Lägg till:
```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx
```

### 4. Sätt permissions på scripts

```bash
chmod +x scripts/run_morning_analysis.sh
chmod +x scripts/run_twice_daily_optimization.sh
```

### 5. Lägg till i crontab

```bash
crontab -e
```

Lägg till dessa rader:

```cron
# Morning Analysis: Generate test proposals
0 5 * * * /home/peccz/nibe_autotuner/scripts/run_morning_analysis.sh >> /var/log/nibe-morning-analysis.log 2>&1

# Morning Optimization: Ventilation + Pump
0 6 * * * /home/peccz/nibe_autotuner/scripts/run_twice_daily_optimization.sh >> /var/log/nibe-optimization.log 2>&1

# Evening Optimization: Ventilation + Pump
0 19 * * * /home/peccz/nibe_autotuner/scripts/run_twice_daily_optimization.sh >> /var/log/nibe-optimization.log 2>&1
```

**⚠️ Ta bort gamla cron-jobb:**
```cron
# TA BORT DESSA (ersatta av nya)
# 0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh
# 0 6 * * * /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh
```

---

## Övervaka

### Se senaste körningar

```bash
# Morgonanalys
tail -f /var/log/nibe-morning-analysis.log

# Optimeringar
tail -f /var/log/nibe-optimization.log
```

### Se testförslag i GUI

1. Öppna mobil-GUI: http://raspberrypi:8502
2. Gå till "AI" fliken (🤖)
3. Se sektioner:
   - **Planerade Tester** - Förslag från morgonanalys
   - **Pågående Tester** - Aktivt test (48h period)
   - **Genomförda Tester** - Resultat med COP-förbättring
   - **Senaste Beslut** - Vad AI:n bestämde senast

### Se AI-beslut

```bash
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python -c "
from models import AIDecisionLog, init_db
from sqlalchemy.orm import sessionmaker

engine = init_db('sqlite:///./data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()

decisions = session.query(AIDecisionLog).order_by(
    AIDecisionLog.timestamp.desc()
).limit(5).all()

for d in decisions:
    print(f'{d.timestamp}: {d.action}')
    if d.parameter:
        print(f'  Parameter: {d.parameter.parameter_name}')
    print(f'  Reasoning: {d.reasoning[:100]}...')
    print(f'  Applied: {d.applied}')
    print()
"
```

---

## Säkerhetsregler

Systemet följer strikt dessa regler:

### AI-Agent
- **Max 1 ändring per 48h** per parameter
- **Minst 70% konfidens** krävs för att tillämpa
- **Inomhustemperatur ≥20°C** alltid
- **Loggning** av alla beslut (även rejected)

### Ventilationsoptimering
- **Minimum ventilation** upprätthålls enligt BBR
- **35-50 L/s** för 5 personer (säkerhet)
- **Gradvis ändring** - inga plötsliga hopp
- **Tolerans 0.5°C** - undvik micro-justeringar

### Test-genomförande
- **48h period** före/efter jämförelse
- **Degree-hours normalisering** för rättvisa resultat
- **Automatisk återställning** vid failure
- **Användarsynlighet** - allt visas i GUI

---

## Felsökning

### Problem: Morgonanalys genererar inga förslag

**Orsak:** Troligen för lite data eller systemet är redan optimalt.

**Lösning:**
```bash
# Kör manuellt med debug
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python src/test_proposer.py
```

### Problem: AI-agent gör inga ändringar

**Möjliga orsaker:**
1. Konfidens <70%
2. Senaste ändring var för nyligen (<48h)
3. System redan optimalt

**Kontrollera:**
```bash
tail -100 /var/log/nibe-optimization.log | grep "AI Decision"
```

### Problem: "ANTHROPIC_API_KEY not found"

**Lösning:**
```bash
# Antingen:
# 1. Lägg till i .env fil
echo "ANTHROPIC_API_KEY=sk-ant-api03-xxx" >> .env

# 2. Eller kör utan AI (regelbaserad):
# Systemet faller automatiskt tillbaka till Auto-Optimizer
```

### Problem: Ventilationen ändras inte

**Kontrollera:**
```bash
# Se aktuell ventilationsstrategi
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python -c "
from ventilation_optimizer import VentilationOptimizer
from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from models import Device, init_db
from sqlalchemy.orm import sessionmaker

engine = init_db('sqlite:///./data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()
device = session.query(Device).first()

analyzer = HeatPumpAnalyzer()
api_client = MyUplinkClient()

optimizer = VentilationOptimizer(
    api_client=api_client,
    analyzer=analyzer,
    device_id=device.device_id
)

# Hämta rekommendation (dry run)
result = optimizer.apply_recommended_settings(dry_run=True)
print(f'Rekommenderad strategi: {result[\"strategy_name\"]}')
print(f'Utomhustemperatur: {result[\"outdoor_temp\"]:.1f}°C')
print(f'Ändring krävs: {result[\"changed\"]}')
"
```

---

## Kostnadsuppskattning

### Med AI-Agent (Claude API)

**Daglig användning:**
- 1× Morgonanalys (testförslag): ~0.10 kr
- 2× Optimering (morgon + kväll): ~0.20 kr
- **Total per dag:** ~0.30 kr
- **Per månad:** ~9 kr
- **Per år:** ~110 kr

**Jämfört med besparingar:**
- Ventilationsoptimering: +450-900 kr/år
- Pumpoptimering: +200-400 kr/år
- **Total besparing:** +650-1,300 kr/år

**Netto:** +540 till +1,190 kr/år (efter API-kostnad)

### Utan AI-Agent (Regelbaserad)

**Kostnad:** 0 kr
**Besparing:** +650-1,300 kr/år

**Skillnad:**
AI-agent kan potentiellt hitta optimeringar som regelbaserad missar, men kostar 110 kr/år extra.

---

## Prestandamätning

### Spåra AI:ns prestation

GUI visar automatiskt:

**Inlärningsstatistik:**
- Lyckandegrad (% lyckade tester)
- Genomsnittlig COP-förbättring
- Genomsnittlig konfidens
- Totalt antal tester

**Bästa upptäckter:**
Top 3 tester med störst COP-förbättring

### Manuell analys

```bash
cd /home/peccz/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python -c "
from models import PlannedTest, ABTestResult, init_db
from sqlalchemy.orm import sessionmaker

engine = init_db('sqlite:///./data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()

# Hämta genomförda tester
tests = session.query(PlannedTest).filter_by(status='completed').join(
    ABTestResult
).all()

print(f'Totalt genomförda tester: {len(tests)}')
print()

for test in tests:
    result = test.result
    print(f'{test.parameter.parameter_name}:')
    print(f'  COP-förändring: {result.cop_change_percent:+.1f}%')
    print(f'  Success score: {result.success_score}/100')
    print(f'  Rekommendation: {result.recommendation}')
    print()
"
```

---

## Nästa Steg

1. **Kör i 1 vecka** - Övervaka loggar
2. **Granska testförslag** - Se vad AI:n föreslår
3. **Jämför resultat** - AI vs regelbaserad
4. **Justera schema** - Om behövs (t.ex. andra tider)
5. **Finjustera konfidens** - Höj till 0.80 för mer konservativ

---

## Support

**Problem med AI-agent?**
- Läs: `AUTONOMOUS_AI_SETUP.md`
- Loggar: `/var/log/nibe-*.log`
- Test manuellt först

**Problem med ventilation?**
- Läs: `VENTILATION_GUIDE.md`
- Kontrollera BBR-minimum (35-50 L/s)

**Problem med cron?**
- Läs: `CRON_SETUP.md`
- Verifiera: `crontab -l`
- Test scripts manuellt

**Allmänna frågor?**
- GitHub Issues: [länk]
- Dokumentation: `docs/`

---

**Lycka till med din fully automated Nibe-optimering! 🤖🔥**
