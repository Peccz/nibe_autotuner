# Changelog - AI Agent Implementation

**Date:** 2025-12-02
**Summary:** Complete autonomous AI agent system with test proposal, twice-daily optimization, and mobile GUI integration

---

## New Features

### 1. Autonomous AI Agent (`src/autonomous_ai_agent.py`)
- Uses Claude API for intelligent decision-making
- Analyzes system performance and weather
- Makes optimization decisions with reasoning
- Logs all decisions to database
- Applies changes with >70% confidence
- **Cost:** ~0.10 kr per analysis (~110 kr/year)
- **Expected savings:** +650-1,300 kr/year

### 2. Test Proposer (`src/test_proposer.py`)
- Analyzes last 24h of data every morning
- Generates prioritized list of test proposals
- Stores proposals in database
- AI-driven or rule-based (fallback)
- Ranks by safety, impact, confidence

### 3. Mobile GUI - AI Tab
- **Template:** `src/mobile/templates/ai_agent.html`
- **Route:** `/ai-agent`
- **Sections:**
  - Status (enabled, last run, cost)
  - Latest Decision (action, reasoning, confidence)
  - Planned Tests (from morning analysis)
  - Active Tests (48h ongoing)
  - Completed Tests (results, COP improvement)
  - Learning Statistics (success rate, avg improvement)
  - Automation Schedule (twice-daily)

### 4. Twice-Daily Optimization
- **Script:** `scripts/run_twice_daily_optimization.sh`
- **Morning (06:00):** Optimize for daytime
- **Evening (19:00):** Optimize for nighttime
- **Process:**
  1. Ventilation optimization (temperature-based)
  2. Pump optimization (AI or rule-based)
- Uses AI agent if ANTHROPIC_API_KEY available
- Falls back to Auto-Optimizer otherwise

### 5. Morning Analysis
- **Script:** `scripts/run_morning_analysis.sh`
- **Time:** 05:00 daily
- Analyzes last 24h
- Generates 3-5 test proposals
- Stores in database for GUI display
- Updates test priority rankings

---

## Database Changes

### New Tables

#### `planned_tests`
- `id`: Primary key
- `parameter_id`: Foreign key to parameters
- `current_value`: Current parameter value
- `proposed_value`: Suggested new value
- `hypothesis`: Why this test might help
- `expected_improvement`: Expected benefit
- `priority`: 'high', 'medium', 'low'
- `confidence`: 0.0-1.0
- `reasoning`: AI explanation
- `status`: 'pending', 'active', 'completed', 'cancelled'
- `proposed_at`: When test was proposed
- `started_at`: When test started
- `completed_at`: When test completed
- `result_id`: Link to ABTestResult

#### `ai_decision_log`
- `id`: Primary key
- `timestamp`: When decision was made
- `action`: 'adjust', 'hold', 'investigate'
- `parameter_id`: Parameter to adjust
- `current_value`: Old value
- `suggested_value`: New value
- `reasoning`: AI explanation (up to 2000 chars)
- `confidence`: 0.0-1.0
- `expected_impact`: Expected effect (up to 500 chars)
- `applied`: Boolean - was change applied?
- `parameter_change_id`: Link to ParameterChange if applied

---

## Modified Files

### `src/models.py`
- Added `PlannedTest` model
- Added `AIDecisionLog` model

### `src/autonomous_ai_agent.py`
- Added `_log_decision()` method
- Logs all decisions to database
- Integrates with new models

### `src/mobile_app.py`
- Added route `/ai-agent` (page)
- Added API `/api/ai-agent/status`
- Added API `/api/ai-agent/latest-decision`
- Added API `/api/ai-agent/planned-tests`
- Added API `/api/ai-agent/active-tests`
- Added API `/api/ai-agent/completed-tests`
- Added API `/api/ai-agent/learning-stats`

### `src/mobile/templates/base.html`
- Added AI tab (🤖) to bottom navigation
- Between "Grafer" and "A/B Test"

### `requirements.txt`
- Added `anthropic>=0.18.0`

---

## New Scripts

### `scripts/run_morning_analysis.sh`
Morning test proposal generation
- Runs at 05:00
- Analyzes 24h data
- Generates test proposals
- Stores in database

### `scripts/run_twice_daily_optimization.sh`
Twice-daily system optimization
- Runs at 06:00 and 19:00
- Step 1: Ventilation optimization
- Step 2: Pump optimization (AI or rules)
- Time-aware (morning vs evening focus)

### `scripts/run_ai_agent.sh`
Standalone AI agent runner (LIVE mode)
- Applies changes
- For cron scheduling

### `scripts/run_ai_agent_dry_run.sh`
Test AI agent without changes
- Safe testing
- Shows what would be done

---

## New Documentation

### `AUTONOMOUS_AI_SETUP.md`
Complete setup guide for AI agent:
- API key acquisition
- Configuration options
- Cost estimation
- Testing procedures
- Comparison with Auto-Optimizer
- Troubleshooting

### `AI_AUTOMATION_SCHEDULE.md`
Complete automation documentation:
- Schedule overview
- What each job does
- Installation steps
- Monitoring
- Safety rules
- Cost analysis
- Performance measurement
- Troubleshooting

---

## CRON Schedule

### New Schedule (Recommended)

```cron
# Morning Analysis: Generate test proposals
0 5 * * * /home/peccz/nibe_autotuner/scripts/run_morning_analysis.sh >> /var/log/nibe-morning-analysis.log 2>&1

# Morning Optimization: Ventilation + Pump
0 6 * * * /home/peccz/nibe_autotuner/scripts/run_twice_daily_optimization.sh >> /var/log/nibe-optimization.log 2>&1

# Evening Optimization: Ventilation + Pump
0 19 * * * /home/peccz/nibe_autotuner/scripts/run_twice_daily_optimization.sh >> /var/log/nibe-optimization.log 2>&1
```

### Old Schedule (Deprecated)

```cron
# REMOVE THESE - Replaced by new schedule
# 0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh
# 0 6 * * * /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh
```

---

## Deployment Steps

### On Development Machine

1. **Update database schema:**
```bash
cd /home/peccz/AI/nibe_autotuner
PYTHONPATH=./src ./venv/bin/python -c "from models import init_db; init_db()"
```

2. **Install dependencies:**
```bash
./venv/bin/pip install anthropic
```

3. **Test scripts locally:**
```bash
# Test morning analysis
./scripts/run_morning_analysis.sh

# Test twice-daily optimization
./scripts/run_twice_daily_optimization.sh
```

### On Raspberry Pi

1. **Copy files to RPi:**
```bash
# Python files
scp -i ~/.ssh/id_nibe_rpi src/test_proposer.py peccz@raspberrypi:/home/peccz/nibe_autotuner/src/
scp -i ~/.ssh/id_nibe_rpi src/autonomous_ai_agent.py peccz@raspberrypi:/home/peccz/nibe_autotuner/src/
scp -i ~/.ssh/id_nibe_rpi src/models.py peccz@raspberrypi:/home/peccz/nibe_autotuner/src/
scp -i ~/.ssh/id_nibe_rpi src/mobile_app.py peccz@raspberrypi:/home/peccz/nibe_autotuner/src/

# Templates
scp -i ~/.ssh/id_nibe_rpi src/mobile/templates/ai_agent.html peccz@raspberrypi:/home/peccz/nibe_autotuner/src/mobile/templates/
scp -i ~/.ssh/id_nibe_rpi src/mobile/templates/base.html peccz@raspberrypi:/home/peccz/nibe_autotuner/src/mobile/templates/

# Scripts
scp -i ~/.ssh/id_nibe_rpi scripts/run_morning_analysis.sh peccz@raspberrypi:/home/peccz/nibe_autotuner/scripts/
scp -i ~/.ssh/id_nibe_rpi scripts/run_twice_daily_optimization.sh peccz@raspberrypi:/home/peccz/nibe_autotuner/scripts/
scp -i ~/.ssh/id_nibe_rpi scripts/run_ai_agent.sh peccz@raspberrypi:/home/peccz/nibe_autotuner/scripts/
scp -i ~/.ssh/id_nibe_rpi scripts/run_ai_agent_dry_run.sh peccz@raspberrypi:/home/peccz/nibe_autotuner/scripts/

# Documentation
scp -i ~/.ssh/id_nibe_rpi AUTONOMOUS_AI_SETUP.md peccz@raspberrypi:/home/peccz/nibe_autotuner/
scp -i ~/.ssh/id_nibe_rpi AI_AUTOMATION_SCHEDULE.md peccz@raspberrypi:/home/peccz/nibe_autotuner/
```

2. **On RPi - Update database and install dependencies:**
```bash
ssh -i ~/.ssh/id_nibe_rpi peccz@raspberrypi

cd /home/peccz/nibe_autotuner

# Update database
PYTHONPATH=./src ./venv/bin/python -c "from models import init_db; init_db('sqlite:///./data/nibe_autotuner.db')"

# Install dependencies
./venv/bin/pip install anthropic

# Make scripts executable
chmod +x scripts/run_morning_analysis.sh
chmod +x scripts/run_twice_daily_optimization.sh
chmod +x scripts/run_ai_agent*.sh
```

3. **On RPi - Update crontab:**
```bash
crontab -e

# Add new lines:
0 5 * * * /home/peccz/nibe_autotuner/scripts/run_morning_analysis.sh >> /var/log/nibe-morning-analysis.log 2>&1
0 6 * * * /home/peccz/nibe_autotuner/scripts/run_twice_daily_optimization.sh >> /var/log/nibe-optimization.log 2>&1
0 19 * * * /home/peccz/nibe_autotuner/scripts/run_twice_daily_optimization.sh >> /var/log/nibe-optimization.log 2>&1

# Remove old lines (if present):
# 0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh
# 0 6 * * * /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh
```

4. **On RPi - Restart mobile app:**
```bash
sudo systemctl restart nibe-mobile-app
```

5. **Verify:**
```bash
# Check mobile app is running
sudo systemctl status nibe-mobile-app

# Check cron jobs
crontab -l

# Test GUI
# Open: http://raspberrypi:8502/ai-agent
```

---

## Testing

### 1. Test Morning Analysis
```bash
cd /home/peccz/nibe_autotuner
./scripts/run_morning_analysis.sh
```

Expected output:
- Analyzes 24h data
- Generates 3-5 proposals
- Shows priority, hypothesis, expected improvement
- Confirms storage in database

### 2. Test Twice-Daily Optimization
```bash
./scripts/run_twice_daily_optimization.sh
```

Expected output:
- Step 1: Ventilation strategy
- Step 2: AI decision or rule-based action
- Summary of changes (if any)

### 3. Test AI Agent (Dry Run)
```bash
./scripts/run_ai_agent_dry_run.sh
```

Expected output:
- Full system analysis
- AI decision with reasoning
- "⚠️ This change was NOT applied (dry run mode)"

### 4. Test Mobile GUI
1. Open browser: `http://raspberrypi:8502`
2. Click AI tab (🤖)
3. Should see:
   - Status (enabled/disabled)
   - Latest decision (if any)
   - Planned tests (if morning analysis has run)
   - Learning statistics

---

## Safety and Rollback

### If Something Goes Wrong

**Disable AI automation:**
```bash
# Comment out cron jobs
crontab -e
# Add # before the 3 new lines

# Or remove entirely
crontab -l | grep -v "run_morning_analysis\|run_twice_daily_optimization" | crontab -
```

**Revert to old schedule:**
```bash
crontab -e

# Re-add old jobs:
0 3 * * * /home/peccz/nibe_autotuner/scripts/run_auto_optimizer.sh >> /var/log/nibe-auto-optimizer.log 2>&1
0 6 * * * /home/peccz/nibe_autotuner/scripts/run_ventilation_optimizer.sh >> /var/log/nibe-ventilation-optimizer.log 2>&1
```

**Restore old mobile_app.py:**
```bash
cd /home/peccz/nibe_autotuner
git checkout src/mobile_app.py src/mobile/templates/base.html
sudo systemctl restart nibe-mobile-app
```

---

## Performance Expectations

### First Week
- **Morning Analysis:** ~3-5 test proposals per day
- **Test Execution:** 1-2 tests per week (48h each)
- **AI Decisions:** Mostly "hold" (system needs baseline)
- **COP Improvement:** Minimal (collecting data)

### After 1 Month
- **Test Database:** 20-30 completed tests
- **Success Rate:** 60-80% (AI learns what works)
- **COP Improvement:** +0.1 to +0.3 (cumulative)
- **Confidence:** AI becomes more confident (70-90%)

### After 3 Months
- **Optimized System:** Most parameters tuned
- **Seasonal Adaptation:** AI understands winter patterns
- **Estimated Savings:** +500-1,000 kr from baseline
- **Test Frequency:** Reduces (fewer opportunities)

---

## Known Limitations

1. **API Key Required for Full AI:**
   - Without key: Falls back to rule-based
   - With key: Uses Claude for smarter decisions
   - Cost: ~110 kr/year

2. **Weather-Dependent:**
   - AI waits for stable weather for tests
   - Extreme conditions → fewer tests
   - Spring/Fall → most active testing

3. **Learning Period:**
   - First month: Collecting baseline
   - Second month: Initial optimizations
   - Third month onwards: Fine-tuning

4. **GUI Requires Data:**
   - Statistics show after tests complete
   - First 48h: Minimal data
   - After 1 week: Useful stats

---

## Future Enhancements

Possible additions (not yet implemented):

1. **User Test Approval:**
   - GUI button to approve/reject planned tests
   - Safety feature for cautious users

2. **Weather Integration in Tests:**
   - Only test during stable weather windows
   - Defer tests if extreme conditions coming

3. **Cost Tracking:**
   - Track actual API costs
   - Display ROI in GUI

4. **Seasonal Learning:**
   - Separate models for summer/winter
   - Automatic parameter switching

5. **Multi-Home Learning:**
   - (Future) Share anonymized learnings
   - Faster optimization for new users

---

## Support

**Questions?**
- Read: `AUTONOMOUS_AI_SETUP.md`
- Read: `AI_AUTOMATION_SCHEDULE.md`
- Check logs: `/var/log/nibe-*.log`

**Issues?**
- GitHub: [Create issue]
- Email: [Support email]

**Contributing?**
- Fork repo
- Improve AI prompts
- Share findings

---

**Happy Optimizing! 🤖🔥**
