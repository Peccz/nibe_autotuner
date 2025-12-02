# Autonomous AI Agent Setup Guide

Den autonoma AI-agenten använder Claude API för att analysera systemet och fatta intelligenta beslut om värmepumpens inställningar.

## Skillnad mellan Auto-Optimizer och AI-Agent

### Auto-Optimizer (Regelbaserad)
- Följer förutbestämda regler
- Snabb och förutsägbar
- Kräver ingen extern API
- Begränsad till definierade scenarion

### AI-Agent (Claude-driven)
- Använder naturligt språk och resonemang
- Kan hantera oväntade situationer
- Lär från A/B-test resultat
- Förklarar beslut i klartext
- Kräver Claude API-nyckel

**Rekommendation:** Börja med Auto-Optimizer. Uppgradera till AI-Agent när du vill ha mer avancerad analys och resonemang.

---

## 1. Skaffa Claude API-nyckel

### Skapa konto hos Anthropic

1. Gå till: https://console.anthropic.com/
2. Skapa konto (behöver email och betalmetod)
3. Navigera till **API Keys**
4. Klicka **Create Key**
5. Kopiera nyckeln (visas bara en gång!)

### Priser (2025)

**Claude 3.5 Sonnet:**
- Input: $3 per million tokens
- Output: $15 per million tokens

**Uppskattad kostnad för Nibe Autotuner:**
- Per analys: ~1,500 input tokens + ~300 output tokens
- Kostnad per analys: ~$0.0045 + ~$0.0045 = **~$0.009 (0.10 kr)**
- En gång per dag i ett år: ~365 × 0.10 kr = **~37 kr/år**

Mycket billigt! Långt mindre än potentiella besparingar (450-900 kr/år från ventilation enbart).

---

## 2. Konfigurera API-nyckel

### Metod 1: Environment Variable (Rekommenderat för Cron)

```bash
# Skapa .env fil i projekt-rooten
cd /home/peccz/AI/nibe_autotuner
nano .env
```

Lägg till:
```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx
```

Spara och stäng (Ctrl+X, Y, Enter).

**Sätt rätt permissions:**
```bash
chmod 600 .env  # Endast ägaren kan läsa
```

### Metod 2: System Environment (Global)

```bash
# Lägg till i ~/.bashrc eller ~/.profile
echo 'export ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx' >> ~/.bashrc
source ~/.bashrc
```

### Metod 3: Direkt i kod (Minst säker)

```python
agent = AutonomousAIAgent(
    analyzer=analyzer,
    api_client=api_client,
    weather_service=weather_service,
    device_id=device.device_id,
    anthropic_api_key='sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx'  # Direkt här
)
```

⚠️ **Varning:** Committa ALDRIG API-nycklar till Git!

---

## 3. Installera anthropic-biblioteket

```bash
cd /home/peccz/AI/nibe_autotuner
source venv/bin/activate
pip install anthropic
```

Uppdatera requirements.txt:
```bash
echo "anthropic>=0.18.0" >> requirements.txt
```

---

## 4. Testa AI-agenten manuellt

### Dry Run (endast analys, inga ändringar)

```bash
cd /home/peccz/AI/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python src/autonomous_ai_agent.py
```

**Output exempel:**
```
================================================================================
AUTONOMOUS AI AGENT - Analysis
================================================================================
Calling Claude API for analysis...

Claude response:
{
  "action": "adjust",
  "parameter": "curve_offset",
  "current_value": 0,
  "suggested_value": -1,
  "reasoning": "Indoor temperature is 22.3°C which is slightly warm. Reducing curve offset by 1 will lower temperature by ~0.5°C while improving COP by ~0.1. This will save energy without sacrificing comfort.",
  "confidence": 0.85,
  "expected_impact": "Indoor temp will decrease to ~21.8°C. COP will improve from 3.07 to ~3.17. Daily savings: ~2 kr."
}

================================================================================
AI DECISION
================================================================================
Action: adjust
Parameter: curve_offset
Change: 0 → -1
Reasoning: Indoor temperature is 22.3°C which is slightly warm...
Confidence: 85%
Expected Impact: Indoor temp will decrease to ~21.8°C. COP will improve...
================================================================================
```

### Live Run (tillämpa ändringar)

**⚠️ Testa först med dry run!**

Modifiera `autonomous_ai_agent.py` main-funktionen:
```python
# Rad 454: Ändra dry_run till False
decision = agent.analyze_and_decide(hours_back=72, dry_run=False)
```

Eller skapa separat test-script:
```python
from autonomous_ai_agent import AutonomousAIAgent
from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from models import Device, init_db
from sqlalchemy.orm import sessionmaker

engine = init_db('sqlite:///./data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()
device = session.query(Device).first()

api_client = MyUplinkClient()
analyzer = HeatPumpAnalyzer()
weather_service = SMHIWeatherService()

agent = AutonomousAIAgent(
    analyzer=analyzer,
    api_client=api_client,
    weather_service=weather_service,
    device_id=device.device_id
)

# LIVE RUN - Tillämpar ändringar!
decision = agent.analyze_and_decide(hours_back=72, dry_run=False)
```

---

## 5. Automatisera med Cron (Valfritt)

### Skapa wrapper-script

Se `scripts/run_ai_agent.sh` (skapas i nästa steg).

### Lägg till i crontab

```bash
crontab -e
```

Lägg till (kör kl 04:00 varje dag):
```cron
# Autonomous AI Agent (alternativ till Auto-Optimizer)
0 4 * * * /home/peccz/nibe_autotuner/scripts/run_ai_agent.sh >> /var/log/nibe-ai-agent.log 2>&1
```

**⚠️ VIKTIGT:** Använd ANTINGEN Auto-Optimizer ELLER AI-Agent i cron, inte båda!

### Välj ett:

**Alternativ A - Auto-Optimizer (Regelbaserad):**
```cron
0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh >> /var/log/nibe-auto-optimizer.log 2>&1
```

**Alternativ B - AI-Agent (Claude-driven):**
```cron
0 4 * * * /home/peccz/nibe_autotuner/scripts/run_ai_agent.sh >> /var/log/nibe-ai-agent.log 2>&1
```

---

## 6. Övervaka och Felsök

### Se senaste loggar

```bash
tail -f /var/log/nibe-ai-agent.log
```

### Manuell körning med debug

```bash
cd /home/peccz/AI/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python -c "
import os
os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx'

from autonomous_ai_agent import AutonomousAIAgent
from analyzer import HeatPumpAnalyzer
from api_client import MyUplinkClient
from weather_service import SMHIWeatherService
from models import Device, init_db
from sqlalchemy.orm import sessionmaker

engine = init_db('sqlite:///./data/nibe_autotuner.db')
Session = sessionmaker(bind=engine)
session = Session()
device = session.query(Device).first()

api_client = MyUplinkClient()
analyzer = HeatPumpAnalyzer()
weather_service = SMHIWeatherService()

agent = AutonomousAIAgent(
    analyzer=analyzer,
    api_client=api_client,
    weather_service=weather_service,
    device_id=device.device_id
)

decision = agent.analyze_and_decide(hours_back=72, dry_run=True)
print(f'\nDecision: {decision.action}')
print(f'Reasoning: {decision.reasoning}')
"
```

### Vanliga fel

#### "ANTHROPIC_API_KEY not found"

**Problem:** API-nyckel inte satt.

**Lösning:**
```bash
# Kontrollera .env fil
cat /home/peccz/AI/nibe_autotuner/.env

# Eller sätt direkt:
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxx
```

#### "anthropic module not found"

**Problem:** Biblioteket inte installerat.

**Lösning:**
```bash
cd /home/peccz/AI/nibe_autotuner
source venv/bin/activate
pip install anthropic
```

#### "API request failed: 401 Unauthorized"

**Problem:** Felaktig API-nyckel.

**Lösning:**
- Kontrollera att nyckeln är korrekt kopierad
- Verifiera på https://console.anthropic.com/

#### "API request failed: 429 Rate limit"

**Problem:** För många förfrågningar.

**Lösning:**
- Claude API har generösa rate limits
- Om detta händer, vänta 1 minut
- Kör inte AI-agent oftare än 1 gång/dag

---

## 7. Jämförelse av beslut

### Auto-Optimizer beslut (regelbaserad)

```
Scenario: COP 2.8, Inomhus 22.5°C, Ute -5°C

Regelbaserad logik:
1. Inomhus >22°C → Minska värmning
2. COP <3.0 → Optimera inställningar
3. Ute <0°C → Aktivera vinter-strategi

→ Åtgärd: Minska curve_offset med 1

Resonemang: [Inget förklarat, följer bara regler]
```

### AI-Agent beslut (Claude-driven)

```
Scenario: COP 2.8, Inomhus 22.5°C, Ute -5°C

AI-analys:
"Indoor temperature is 22.5°C which is comfortable but slightly warm.
Reducing heating would improve efficiency. However, outdoor temperature
is -5°C and weather forecast shows -8°C tomorrow. Reducing heating now
would mean we need to increase it tomorrow, causing inefficient cycling.

Recent A/B test showed that curve_offset -1 improved COP by 0.12 without
comfort issues. Delta T is good (2.1°C) so system is operating efficiently.

Recommendation: Hold current settings for 24h to see weather trend."

→ Åtgärd: Hold (ingen ändring)

Resonemang: Ser framåt i väder-prognos, lär från A/B-tester,
            förstår ineffektivitet av för snabba ändringar
```

**Fördel AI-Agent:**
- Kontextuell förståelse
- Långsiktig planering
- Lär från historik
- Förklarar resonemang

---

## 8. Kostnadsuppföljning

### Spåra API-användning

```python
# Lägg till i autonomous_ai_agent.py (valfritt)
def analyze_and_decide(self, hours_back: int = 72, dry_run: bool = True) -> AIDecision:
    # ... existing code ...

    # After API call
    usage = message.usage
    logger.info(f"Token usage: {usage.input_tokens} input, {usage.output_tokens} output")

    # Estimate cost
    input_cost = usage.input_tokens / 1_000_000 * 3.0  # $3/M tokens
    output_cost = usage.output_tokens / 1_000_000 * 15.0  # $15/M tokens
    total_cost_usd = input_cost + output_cost
    total_cost_sek = total_cost_usd * 10.5  # ~10.5 SEK/USD

    logger.info(f"Cost: ${total_cost_usd:.4f} (~{total_cost_sek:.2f} kr)")
```

### Månadlig kostnad (uppskattning)

```
Körningar per månad: 30 (en gång/dag)
Tokens per körning: ~1,800 (1,500 input + 300 output)
Kostnad per körning: ~0.10 kr
Månadskostnad: ~3 kr
Årskostnad: ~37 kr

Jämför med:
- Ventilationsoptimering sparar: 450-900 kr/år
- Auto-optimizer sparar: 200-400 kr/år
- AI-agent kostar: -37 kr/år

Netto: +613 kr/år (minimum)
```

---

## 9. Säkerhet och Best Practices

### API-nyckel säkerhet

✅ **Gör:**
- Spara i `.env` fil med `chmod 600`
- Använd environment variables
- Lägg till `.env` i `.gitignore`

❌ **Gör INTE:**
- Committa API-nycklar till Git
- Dela nycklar i kod
- Logga nycklar i klartext

### Användning

✅ **Gör:**
- Börja med dry run
- Övervaka första veckorna
- Jämför med Auto-Optimizer
- Kör max 1 gång/dag

❌ **Gör INTE:**
- Kör både Auto-Optimizer och AI-Agent samtidigt
- Kör oftare än 1 gång/dag (onödigt)
- Ignorera AI:ns reasoning (lär dig av den!)

---

## 10. Nästa Steg

1. **Skaffa API-nyckel** från Anthropic Console
2. **Konfigurera `.env`** med ANTHROPIC_API_KEY
3. **Testa manuellt** med dry run först
4. **Jämför beslut** med Auto-Optimizer
5. **Välj en** för automatisering i cron
6. **Övervaka** i en vecka
7. **Utvärdera** om AI-agent ger bättre resultat

---

## Support och Feedback

**Problem?**
- Kontrollera loggar: `tail -f /var/log/nibe-ai-agent.log`
- Verifiera API-nyckel: https://console.anthropic.com/
- Kör manuell test först

**Vill ha mer kontroll?**
- Ändra `confidence` threshold (0.70 → 0.85 för mer konservativ)
- Justera prompt i `autonomous_ai_agent.py`
- Lägg till extra safety rules

**Feedback?**
- Spara AI:ns resonemang
- Jämför med Auto-Optimizer
- Dela resultat i GitHub issues

---

## Bilaga A: Prompt Engineering

AI-agenten använder en detaljerad prompt som inkluderar:

1. **System Context:**
   - Aktuell status (temperaturer, COP, inställningar)
   - Väderprognos
   - Senaste ändringar
   - A/B-test resultat

2. **Safety Rules:**
   - Aldrig <20°C inomhus
   - Max 1 parameter åt gången
   - Minst 70% konfidens
   - Respektera 48h A/B-test period

3. **Output Format:**
   - Strukturerad JSON
   - action: adjust/hold/investigate
   - Detaljerat resonemang
   - Konfidensgrad
   - Förväntad påverkan

**Anpassa prompt:**
- Öppna `src/autonomous_ai_agent.py`
- Hitta `analyze_and_decide()` metoden
- Ändra `prompt = f"""..."""` sektionen
- Lägg till egna regler eller prioriteringar

Exempel:
```python
## Your Task

Analyze the system performance and decide if any adjustments are needed.

Consider:
1. **Efficiency**: Is COP optimal for current conditions?
2. **Comfort**: Is indoor temperature comfortable (20-22°C)?
3. **Cost**: Prioritize energy savings over comfort if >21°C  # CUSTOM RULE
4. **Stability**: Avoid changes during very cold weather (<-10°C)  # CUSTOM RULE
```

---

## Bilaga B: Exempel på AI-beslut

### Scenario 1: Normal drift

```json
{
  "action": "hold",
  "parameter": null,
  "current_value": null,
  "suggested_value": null,
  "reasoning": "System is performing well. COP is 3.15 which is excellent for -3°C outdoor temperature. Indoor temperature is 21.2°C which is in the comfort zone. Delta T is 2.0°C showing good heat transfer. No changes needed.",
  "confidence": 0.92,
  "expected_impact": "Continue stable operation with good efficiency"
}
```

### Scenario 2: Optimering möjlig

```json
{
  "action": "adjust",
  "parameter": "curve_offset",
  "current_value": 0,
  "suggested_value": -1,
  "reasoning": "Indoor temperature has been stable at 22.3°C for 48 hours, which is warmer than necessary. Weather forecast shows mild temperatures (0 to 5°C) for the next 3 days, making this a good time to reduce heating. Recent A/B test confirmed that curve_offset -1 maintains 21.8°C while improving COP by 0.12. This change will save approximately 2 kr/day without sacrificing comfort.",
  "confidence": 0.87,
  "expected_impact": "Indoor temp: 22.3°C → 21.8°C, COP: 3.05 → 3.17, Daily savings: ~2 kr"
}
```

### Scenario 3: Investigation needed

```json
{
  "action": "investigate",
  "parameter": null,
  "current_value": null,
  "suggested_value": null,
  "reasoning": "Delta T has dropped from 2.2°C to 1.4°C over the last 12 hours, which suggests either increased flow rate or reduced heat transfer. This is unusual and could indicate a developing issue (air in system, pump speed change, or partial blockage). Before making parameter adjustments, we should monitor for another 24 hours to determine if this is temporary (e.g., hot water production cycle) or persistent.",
  "confidence": 0.78,
  "expected_impact": "Continue monitoring Delta T trend. If it stays low, may need to adjust pump speed or investigate system"
}
```

### Scenario 4: Weather-proactive

```json
{
  "action": "adjust",
  "parameter": "start_compressor",
  "current_value": -200,
  "suggested_value": -150,
  "reasoning": "Weather forecast shows temperature drop from -2°C to -12°C in the next 18 hours. Current degree minutes is -180, which is close to the compressor start threshold of -200. If we wait until outdoor temperature drops, the system will struggle to catch up, leading to comfort issues and lower COP. Proactively reducing the start threshold to -150 will allow the compressor to start earlier, pre-heating the house before the cold snap arrives. This prevents inefficient emergency heating mode.",
  "confidence": 0.81,
  "expected_impact": "Compressor will start earlier, maintaining 21°C indoor temp during cold snap. Prevents COP drop from late response."
}
```

---

**Lycka till med din autonoma AI-agent!**
