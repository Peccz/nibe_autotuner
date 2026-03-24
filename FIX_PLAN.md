# Fix Plan - Nibe Autotuner Audit Issues

**Generated:** 2026-03-24
**Based on:** Comprehensive codebase audit
**Total Issues:** 10 (3 Critical, 3 High, 4 Medium/Low)

---

## PHASE 1: CRITICAL FIXES (Fix Immediately)

### ✅ Issue #1: Missing 'desc' Import in gm_controller.py

**Severity:** CRITICAL
**File:** `src/services/gm_controller.py`
**Line:** 84
**Risk:** Service will crash when trying to fetch system mode from database

**Problem:**
```python
# Line 84 - Uses 'desc' but never imports it
reading = self.db.query(ParameterReading).filter_by(parameter_id=param.id).order_by(desc(ParameterReading.timestamp)).first()
```

**Fix:**
```python
# Add to imports at top of file (after line 10)
from sqlalchemy import desc
```

**Testing:**
```bash
# After fix, verify service starts without errors
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/gm_controller.py

# Check logs for successful system mode detection
journalctl -u nibe-gm-controller -n 50 | grep "system_mode"
```

**Deployment:**
1. Make change to `src/services/gm_controller.py`
2. Test locally
3. Deploy with `./deploy_v4.sh`
4. Monitor logs for 1 hour after deployment

---

### ✅ Issue #2: Missing PYTHONPATH in nibe-mobile.service

**Severity:** CRITICAL
**File:** `nibe-mobile.service`
**Line:** 11 (add after ExecStart)
**Risk:** Mobile app may fail with import errors

**Problem:**
```ini
# nibe-mobile.service is missing PYTHONPATH environment variable
# Other services have it:
Environment="PYTHONPATH=/home/peccz/AI/nibe_autotuner/src"
```

**Fix:**
```ini
[Service]
Type=simple
User=peccz
WorkingDirectory=/home/peccz/AI/nibe_autotuner
Environment="PYTHONPATH=/home/peccz/AI/nibe_autotuner/src"  # <-- ADD THIS LINE
ExecStart=/home/peccz/AI/nibe_autotuner/venv/bin/python src/mobile/mobile_app.py
Restart=always
RestartSec=10
```

**Testing:**
```bash
# After fix, reload systemd and restart service
sudo systemctl daemon-reload
sudo systemctl restart nibe-mobile
sudo systemctl status nibe-mobile

# Check for import errors
journalctl -u nibe-mobile -n 50 | grep -i "error\|import"

# Verify mobile app is accessible
curl http://localhost:5001/
```

**Deployment:**
1. Edit `nibe-mobile.service`
2. Run `sudo cp nibe-mobile.service /etc/systemd/system/`
3. Run `sudo systemctl daemon-reload`
4. Run `sudo systemctl restart nibe-mobile`
5. Verify web interface works

---

### ✅ Issue #3: No Verification of Write Success

**Severity:** CRITICAL
**File:** `src/services/gm_controller.py`
**Lines:** 155-157
**Risk:** Silent failures when writing to heat pump

**Problem:**
```python
# Assumes write succeeded without checking
self.client.set_point_value(device.device_id, self.PARAM_GM_WRITE, gm_to_write)
self.last_written_gm = gm_to_write  # Updates before confirming write worked
```

**Fix:**
```python
# Enhanced version with verification
try:
    # Attempt write
    self.client.set_point_value(device.device_id, self.PARAM_GM_WRITE, gm_to_write)

    # Wait for write to propagate (myUplink API typically takes 1-2 seconds)
    time.sleep(2)

    # Read back to verify
    all_points_verify = self.client.get_device_points(device.device_id)
    p_verify = {str(item['parameterId']): item for item in all_points_verify}
    actual_gm = float(p_verify.get(self.PARAM_GM_READ, {}).get('value', 0))

    # Check if write succeeded (allow ±10 tolerance for rounding)
    if abs(actual_gm - gm_to_write) > 10:
        logger.warning(f"⚠️ GM Write Verification Failed! Wrote {gm_to_write}, pump shows {actual_gm}")
        # Don't update last_written_gm - will retry on next tick
    else:
        self.last_written_gm = gm_to_write
        logger.info(f"✓ GM Write Verified: {gm_to_write} (Pump confirms {actual_gm})")

except Exception as e:
    logger.error(f"GM Write failed: {e}")
    # Don't update last_written_gm - will retry
```

**Alternative (Lighter):**
If read-back verification adds too much API load, at minimum check the response:

```python
try:
    response = self.client.set_point_value(device.device_id, self.PARAM_GM_WRITE, gm_to_write)
    # myUplink API returns parameter info on success
    if response:
        self.last_written_gm = gm_to_write
        logger.info(f"✓ GM Write Acknowledged: {gm_to_write}")
    else:
        logger.warning(f"⚠️ GM Write returned empty response")
except Exception as e:
    logger.error(f"GM Write failed: {e}")
```

**Testing:**
```bash
# Monitor logs for write verification messages
journalctl -u nibe-gm-controller -f | grep "GM Write"

# Manually verify pump responds to commands
sqlite3 data/nibe_autotuner.db "SELECT * FROM gm_account ORDER BY last_updated DESC LIMIT 1;"
```

**Deployment:**
1. Implement fix in `gm_controller.py`
2. Test locally for 30 minutes
3. Deploy with `./deploy_v4.sh`
4. Monitor for 24 hours to ensure no issues

---

## PHASE 2: HIGH PRIORITY FIXES (Fix This Week)

### 🟡 Issue #4: Race Condition in smart_planner.py

**Severity:** HIGH
**File:** `src/services/smart_planner.py`
**Lines:** 114-123
**Risk:** GM controller might read empty schedule during update

**Problem:**
```python
conn.execute("DELETE FROM planned_heating_schedule")  # <-- Window of vulnerability
conn.executemany("""
    INSERT INTO planned_heating_schedule ...
""", plan_rows)
conn.commit()
```

**Timeline of race:**
```
T=0s   smart_planner: DELETE all rows
T=0.5s gm_controller: Reads schedule → gets EMPTY!
T=1s   smart_planner: INSERT new rows
T=1.5s smart_planner: COMMIT
```

**Fix Option A: Use Transaction (Recommended)**
```python
# Start transaction
conn.execute("BEGIN EXCLUSIVE")  # SQLite exclusive lock

try:
    conn.execute("DELETE FROM planned_heating_schedule")
    conn.executemany("""
        INSERT INTO planned_heating_schedule ...
    """, plan_rows)
    conn.commit()
except Exception as e:
    conn.rollback()
    logger.error(f"Failed to update schedule: {e}")
    raise
```

**Fix Option B: Atomic Swap with Staging Table**
```python
# Create staging table (one-time migration)
# planned_heating_schedule_staging (same schema)

# Write to staging first
conn.execute("DELETE FROM planned_heating_schedule_staging")
conn.executemany("""
    INSERT INTO planned_heating_schedule_staging ...
""", plan_rows)
conn.commit()

# Atomic swap
conn.execute("BEGIN EXCLUSIVE")
conn.execute("DELETE FROM planned_heating_schedule")
conn.execute("""
    INSERT INTO planned_heating_schedule
    SELECT * FROM planned_heating_schedule_staging
""")
conn.commit()
```

**Recommendation:** Use Option A (simpler, sufficient for SQLite)

**Testing:**
```bash
# Run smart_planner and gm_controller simultaneously
# Verify gm_controller never sees empty schedule

# Terminal 1
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/smart_planner.py

# Terminal 2
journalctl -u nibe-gm-controller -f | grep "planned_offset"
```

**Deployment:**
1. Implement transaction fix
2. Test locally with concurrent processes
3. Deploy with `./deploy_v4.sh`
4. Monitor for scheduling gaps

---

### 🟡 Issue #5: SafetyGuard Not Used in Control Path

**Severity:** HIGH
**File:** `src/services/gm_controller.py`
**Risk:** Duplicate safety logic, harder to maintain/audit

**Problem:**
- `src/services/safety_guard.py` exists with `validate_decision()` method
- `gm_controller.py` implements its own ad-hoc safety checks
- No unified validation layer

**Current Safety Checks in gm_controller:**
```python
# Line 124: Bastu-vakt
if cur_indoor > 23.5:
    account.balance = 100.0

# Line 134: Critical temp override
if cur_indoor > self.CRITICAL_TEMP_LIMIT and raw_gm < ...:
    gm_to_write = self.EL_HEATER_START_LIMIT + 50
```

**Fix:**
```python
# At top of gm_controller.py
from services.safety_guard import SafetyGuard, AIDecisionSchema

class GMController:
    def __init__(self):
        # ... existing code ...
        self.safety_guard = SafetyGuard()

    def run_tick(self):
        # ... existing code to calculate gm_to_write ...

        # Before writing, validate with SafetyGuard
        decision = AIDecisionSchema(
            action='adjust',
            parameter='40940',  # GM parameter
            current_value=cur_pump_gm,
            suggested_value=gm_to_write,
            reasoning=f"Bank balance {account.balance}, action {action}",
            confidence=1.0
        )

        is_safe, reason, safe_value = self.safety_guard.validate_decision(
            decision,
            device.device_id
        )

        if not is_safe:
            logger.warning(f"⚠️ SafetyGuard blocked GM write: {reason}")
            if safe_value is not None:
                gm_to_write = safe_value
                logger.info(f"Using SafetyGuard-adjusted value: {safe_value}")
            else:
                logger.error("SafetyGuard rejected with no safe alternative. Holding.")
                return  # Don't write anything

        # Proceed with write...
```

**Benefits:**
- Centralized safety logic
- Easier to audit and update safety rules
- Consistent safety across all control paths (AI agent, GM controller, manual)

**Testing:**
```bash
# Test safety boundary cases
# 1. Set indoor temp to 23.6°C (should trigger Bastu-vakt)
# 2. Set indoor temp to 18.5°C (should trigger critical override)
# 3. Verify SafetyGuard logs appear

journalctl -u nibe-gm-controller -f | grep "SafetyGuard"
```

**Deployment:**
1. Implement SafetyGuard integration
2. Test with simulated extreme conditions
3. Deploy and monitor for 48 hours
4. Verify no safety regressions

---

### 🟡 Issue #6: Replace Bare Exception Handlers

**Severity:** HIGH
**Files:** 48+ files across codebase
**Risk:** Silent errors, hard to debug

**Problem Examples:**

```python
# gm_controller.py:86 - Silently swallows ALL errors
try:
    system_mode = reading.value
except: pass  # ❌ BAD: Hides ImportError, AttributeError, etc.

# data_logger.py:167 - Too broad but logs error
except Exception as e:  # ⚠️ BETTER but still broad
    logger.error(f"Error logging HA readings: {e}")
```

**Fix Strategy:**

**Pattern 1: Known Failure Case**
```python
# When specific error is expected and safe to ignore
try:
    system_mode = reading.value
except (AttributeError, IndexError):
    system_mode = 1.0  # Default to heating mode
    logger.debug("System mode reading unavailable, using default")
```

**Pattern 2: Unexpected But Non-Critical**
```python
# When error should be logged but not crash service
try:
    self._fetch_ha_sensors()
except (requests.RequestException, ValueError) as e:
    logger.warning(f"HA sensor fetch failed (will retry next cycle): {e}")
    # Continue with stale data
```

**Pattern 3: Critical Path**
```python
# When error should crash service (fail-fast)
try:
    device = self.db.query(Device).first()
    if not device:
        raise ValueError("No device found in database")
except Exception as e:
    logger.critical(f"Fatal error in control loop: {e}")
    raise  # Let systemd restart service
```

**Implementation Plan:**
1. Identify all 48 exception handlers
2. Categorize by criticality (critical/important/optional)
3. Fix critical paths first (gm_controller, data_logger, smart_planner)
4. Fix remaining in batches

**Files to prioritize:**
- `src/services/gm_controller.py` (10 instances)
- `src/data/data_logger.py` (8 instances)
- `src/services/smart_planner.py` (3 instances)
- `src/services/analyzer.py` (12 instances)

**Testing:**
```bash
# Inject failures and verify proper error handling
# 1. Disconnect network (test API failures)
# 2. Corrupt database (test DB failures)
# 3. Invalid sensor data (test validation failures)

# Check that errors are logged properly
journalctl -u nibe-gm-controller --since "5 minutes ago" | grep -i error
```

**Deployment:**
1. Fix critical services first
2. Deploy one service at a time
3. Monitor error logs for regressions
4. Fix remaining services in batches

---

## PHASE 3: MEDIUM PRIORITY (Fix This Month)

### 🟢 Issue #7: Improve Session Management

**Severity:** MEDIUM
**Files:** `gm_controller.py`, `data_logger.py`, `smart_planner.py`
**Risk:** Resource leaks, database locks

**Problem:**
```python
# data_logger.py:29 - Session never closed
self.session = get_session()

# gm_controller.py:41 - Session held forever
self.db = SessionLocal()
```

**Fix:**

**Option A: Context Manager for Short-Lived Operations**
```python
# In smart_planner.py
def calculate_plan():
    with get_db_connection() as conn:
        # ... all database operations ...
        conn.commit()
    # Connection automatically closed
```

**Option B: Periodic Session Refresh for Long-Running Services**
```python
# In gm_controller.py
class GMController:
    def __init__(self):
        self.session_refresh_interval = 3600  # 1 hour
        self.last_session_refresh = datetime.now()
        self._refresh_session()

    def _refresh_session(self):
        if hasattr(self, 'db'):
            self.db.close()
        self.db = SessionLocal()
        self.last_session_refresh = datetime.now()

    def run_tick(self):
        # Refresh session every hour
        if (datetime.now() - self.last_session_refresh).total_seconds() > self.session_refresh_interval:
            logger.info("Refreshing database session")
            self._refresh_session()

        # ... rest of logic ...
```

**Recommendation:** Use Option B for long-running services (gm_controller, data_logger)

**Testing:**
```bash
# Monitor for database locks
sqlite3 data/nibe_autotuner.db "PRAGMA database_list;"

# Check open file descriptors
lsof -p $(pgrep -f gm_controller) | grep database

# Run for 24 hours and verify no memory leaks
ps aux | grep python | grep gm_controller
```

---

### 🟢 Issue #8: Standardize Import Paths

**Severity:** MEDIUM
**Files:** Multiple across codebase
**Risk:** Deployment fragility, confusing for new developers

**Problem:**
```python
# Different files use different strategies:

# data_logger.py - Absolute imports (GOOD)
from integrations.auth import MyUplinkAuth

# gm_controller.py - Manual path hacking (BAD)
sys.path.insert(0, os.path.abspath('src'))
from data.database import SessionLocal
```

**Fix: Create Proper Python Package**

**Step 1: Create pyproject.toml**
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "nibe-autotuner"
version = "12.0.0"
description = "AI-powered Nibe heat pump optimization"
requires-python = ">=3.10"
dependencies = [
    "myuplink>=0.7.0",
    "sqlalchemy>=2.0.0",
    "pydantic>=2.5.0",
    "fastapi>=0.104.0",
    "loguru>=0.7.0",
    # ... rest from requirements.txt
]

[project.scripts]
nibe-data-logger = "nibe_autotuner.data.data_logger:main"
nibe-gm-controller = "nibe_autotuner.services.gm_controller:main"
nibe-smart-planner = "nibe_autotuner.services.smart_planner:main"
```

**Step 2: Rename src/ to nibe_autotuner/**
```bash
mv src nibe_autotuner
```

**Step 3: Update all imports**
```python
# Old:
from data.database import SessionLocal

# New:
from nibe_autotuner.data.database import SessionLocal
```

**Step 4: Update systemd services**
```ini
# Old:
Environment="PYTHONPATH=/home/peccz/AI/nibe_autotuner/src"
ExecStart=/home/peccz/AI/nibe_autotuner/venv/bin/python src/data/data_logger.py

# New (using installed scripts):
ExecStart=/home/peccz/AI/nibe_autotuner/venv/bin/nibe-data-logger
```

**Step 5: Install in development mode**
```bash
pip install -e .
```

**Benefits:**
- No more PYTHONPATH juggling
- Proper versioning
- Easier to distribute
- Professional project structure

**Risk:** High-impact change, thorough testing required

**Testing:**
```bash
# After restructure, test all services
pip install -e .
nibe-data-logger --once
nibe-smart-planner
nibe-gm-controller  # Ctrl+C after 1 minute
```

**Deployment:**
This is a breaking change. Recommended approach:
1. Create a new branch `feature/package-structure`
2. Implement changes
3. Test thoroughly on Raspberry Pi staging environment
4. Deploy during low-risk period (summer when heating is off)

---

### 🟢 Issue #9: Update .env.example

**Severity:** MEDIUM
**File:** `.env.example`
**Risk:** Incomplete setup for new installations

**Problem:**
`.env.example` is missing several variables defined in `src/core/config.py`:

**Missing Variables:**
```python
# From config.py Settings class
HA_SENSOR_DOWNSTAIRS: str
HA_SENSOR_DEXTER: str
HA_SENSOR_OUTDOOR: str
HA_SENSOR_WIND_SPEED: str
HA_SENSOR_WIND_DIRECTION: str
SHUNT_LIMIT_C: float = 32.0
DEFAULT_HEATING_CURVE: float = 5.0
API_PORT: int = 8000
MOBILE_PORT: int = 5001
```

**Fix:**
```bash
# .env.example (complete version)
# myUplink API Credentials
MYUPLINK_CLIENT_ID=your_client_id_here
MYUPLINK_CLIENT_SECRET=your_client_secret_here
MYUPLINK_CALLBACK_URL=http://localhost:8080/oauth/callback

# Database
DATABASE_URL=sqlite:///./data/nibe_autotuner.db

# Home Assistant Integration
HA_URL=http://homeassistant.local:8123
HA_TOKEN=your_long_lived_access_token

# Home Assistant Sensors
HA_SENSOR_DOWNSTAIRS=sensor.downstairs_temperature
HA_SENSOR_DEXTER=sensor.dexter_temperature
HA_SENSOR_OUTDOOR=sensor.outdoor_temperature
HA_SENSOR_WIND_SPEED=sensor.wind_speed
HA_SENSOR_WIND_DIRECTION=sensor.wind_direction

# Heat Pump Configuration
SHUNT_LIMIT_C=32.0
DEFAULT_HEATING_CURVE=5.0

# API Ports
API_PORT=8000
MOBILE_PORT=5001

# Optional: Gemini AI API Key (for advanced features)
GEMINI_API_KEY=your_gemini_api_key_here
```

**Testing:**
```bash
# Create fresh .env from example
cp .env.example .env.test
# Edit .env.test with real credentials
# Verify all services start with only .env.test
```

**Deployment:**
1. Update `.env.example`
2. Document in README which variables are required vs optional
3. Commit and push

---

### 🟢 Issue #10: Archive Old Variant Files

**Severity:** LOW
**Files:** 78+ files in root directory
**Risk:** Confusing project structure, wastes space

**Problem:**
Root directory has many backup/variant files:
```
agent_v2_after_away.py
agent_v2_away_fixed.py
agent_v2_away.py
agent_v2_clean_base.py
... (20+ more agent_v2_*.py files)

analyzer_broken_import.py
analyzer_check_final.py
analyzer_check.py
... (15+ more analyzer_*.py files)

mobile_app_analytics.py
mobile_app_final_fixed.py
... (10+ more mobile_app_*.py files)
```

**Fix:**
```bash
# Create archive directory
mkdir -p archive/old_versions

# Move all variant files
mv agent_v2_*.py archive/old_versions/
mv analyzer_*.py archive/old_versions/
mv mobile_app_*.py archive/old_versions/
mv data_logger_*.py archive/old_versions/

# Keep only active files in root
# (Actually most should be deleted as they're in git history)
```

**Better Approach:**
Since these are in git history, just delete them:

```bash
# List old files
git ls-files | grep -E "(agent_v2_|analyzer_|mobile_app_|data_logger_)" > old_files.txt

# Review list
cat old_files.txt

# Delete if confirmed
xargs rm < old_files.txt

# Commit cleanup
git add -A
git commit -m "Remove old variant files (preserved in git history)"
```

**Testing:**
```bash
# Verify no active code depends on these files
grep -r "import.*agent_v2" src/
grep -r "import.*analyzer_cleaned" src/

# Should return nothing
```

**Deployment:**
1. Review old_files.txt carefully
2. Confirm none are referenced
3. Delete and commit
4. Push to GitHub

---

## TESTING STRATEGY

### Unit Tests to Add

**Priority 1: Safety Boundaries**
```python
# tests/test_gm_controller_safety.py
def test_bastu_vakt_triggers():
    """Verify Bastu-vakt activates above 23.5°C"""

def test_critical_temp_override():
    """Verify protection at 19°C"""

def test_gm_balance_bounds():
    """Verify MIN_BALANCE and MAX_BALANCE enforcement"""
```

**Priority 2: Control Logic**
```python
# tests/test_smart_planner.py
def test_optimizer_comfort_constraint():
    """Verify indoor temp stays within 20.5-22°C"""

def test_optimizer_cost_minimization():
    """Verify plan reduces cost vs baseline"""
```

**Priority 3: Integration**
```python
# tests/test_integration.py
def test_full_control_loop():
    """Mock APIs, run full data → plan → control loop"""
```

### Manual Testing Checklist

After deploying critical fixes:
- [ ] Verify gm_controller starts without errors
- [ ] Confirm mobile app loads at http://localhost:5001
- [ ] Check API responds at http://localhost:8000/docs
- [ ] Monitor logs for 1 hour for errors
- [ ] Verify heat pump responds to GM writes
- [ ] Check database for scheduling gaps
- [ ] Test safety override by simulating high temp

---

## DEPLOYMENT TIMELINE

### Week 1: Critical Fixes
- **Day 1**: Fix missing import (#1)
- **Day 2**: Add PYTHONPATH to service (#2)
- **Day 3**: Implement write verification (#3)
- **Day 4-5**: Testing and monitoring
- **Day 6**: Deploy to production
- **Day 7**: Monitor and verify

### Week 2: High Priority
- **Day 1-2**: Fix race condition (#4)
- **Day 3-4**: Integrate SafetyGuard (#5)
- **Day 5-7**: Fix exception handlers (#6)

### Week 3-4: Medium Priority
- **Week 3**: Session management (#7), .env.example (#9)
- **Week 4**: Import path standardization (#8) - requires careful testing

### Month 2: Low Priority
- Archive cleanup (#10)
- Add unit tests
- Improve documentation

---

## ROLLBACK PLAN

For each change:

1. **Before Deployment**
   ```bash
   # Tag current production version
   git tag -a v12.0-stable -m "Last known good version before fixes"
   git push origin v12.0-stable
   ```

2. **If Issues After Deployment**
   ```bash
   # Rollback to previous version
   git checkout v12.0-stable
   ./deploy_v4.sh

   # Or rollback specific service
   sudo systemctl stop nibe-gm-controller
   git checkout v12.0-stable -- src/services/gm_controller.py
   sudo systemctl start nibe-gm-controller
   ```

3. **Database Rollback**
   ```bash
   # Backup before changes
   cp data/nibe_autotuner.db data/nibe_autotuner.db.backup-$(date +%Y%m%d)

   # Restore if needed
   cp data/nibe_autotuner.db.backup-20260324 data/nibe_autotuner.db
   ```

---

## SUCCESS METRICS

After implementing all fixes:

### Reliability
- [ ] No crashes in 7 days of operation
- [ ] No silent write failures
- [ ] No race condition gaps in schedule

### Safety
- [ ] All temperature overrides logged and verified
- [ ] SafetyGuard integration tested with extreme inputs
- [ ] No safety regressions detected

### Code Quality
- [ ] Import paths consistent across all files
- [ ] No bare `except:` handlers in critical paths
- [ ] Session management verified (no leaks)

### Documentation
- [ ] `.env.example` complete and accurate
- [ ] All fixes documented in git commits
- [ ] CLAUDE.md updated with lessons learned

---

## APPENDIX: File-by-File Change Summary

### Critical Changes
1. `src/services/gm_controller.py` - Add desc import, write verification, SafetyGuard
2. `nibe-mobile.service` - Add PYTHONPATH environment variable
3. `src/services/smart_planner.py` - Add transaction for race condition

### High Priority Changes
4. `src/services/gm_controller.py` - Replace exception handlers
5. `src/data/data_logger.py` - Replace exception handlers
6. `src/services/safety_guard.py` - Integration point (no changes needed)

### Medium Priority Changes
7. All service files - Session management improvements
8. All files - Import path standardization (breaking change)
9. `.env.example` - Add missing variables

### Low Priority Changes
10. Root directory - Archive/delete old files
11. `tests/` - Add comprehensive test suite

---

**Total Estimated Time:**
- Critical fixes: 1 week
- High priority: 2 weeks
- Medium priority: 2-3 weeks
- Low priority: 1 week
- **Total: 6-7 weeks for complete implementation**

**Minimum Viable Fix (Critical Only): 1 week**
