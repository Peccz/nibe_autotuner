# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered optimization system for a Nibe F730 heat pump. The system:
- Collects operational data via myUplink API every 5 minutes
- Uses deterministic control with predictive optimization to minimize electricity costs
- Maintains comfort constraints (20.5-22°C indoor temperature)
- Operates via a "Degree Minutes Bank" that manages heat pump operation

**Current Version:** V12.0 (Proactive Optimization & Deterministic Banking)

## Core Architecture

### Data Flow
```
myUplink API → data_logger.py → SQLite DB → smart_planner.py → PlannedHeatingSchedule
                                              ↓
Home Assistant Sensors → data_logger.py → SQLite DB → gm_controller.py → myUplink Write API
```

### Three Critical Services (Run as systemd services)

1. **data_logger.py** (Port: None, Interval: 5min)
   - Fetches 102 parameters from Nibe heat pump via myUplink API
   - Fetches Home Assistant sensors (room temps, wind, etc.)
   - Calculates virtual parameters (e.g., VP_SYSTEM_MODE: 1=heating, 2=hot water, 3=defrost)
   - Stores all in `parameter_readings` table

2. **smart_planner.py** (Port: None, Cron: hourly)
   - Fetches 24h price forecast (via price_service) and weather forecast (SMHI)
   - Runs optimizer to find best offset schedule balancing cost vs. comfort
   - Writes plan to `planned_heating_schedule` table
   - Uses thermal simulation model to predict indoor temperatures

3. **gm_controller.py** (Port: None, Loop: 1min)
   - The "Bank" - Simulates Nibe's Degree Minutes (GM) locally
   - Reads current plan from `planned_heating_schedule`
   - Calculates target supply temperature based on plan offset
   - Accumulates GM debt/credit based on actual vs target supply temp
   - Writes GM setpoint (40940) to heat pump via myUplink API
   - Safety overrides: "Bastu-vakt" (force stop >23.5°C), anti-windup, critical temp protection

### Web Interfaces

4. **mobile_app.py** (Port: 5001, Flask)
   - Legacy dashboard UI - main user interface
   - Shows current status, temperatures, plan visualization
   - Located in `src/mobile/`

5. **api_server.py** (Port: 8000, FastAPI)
   - Modern REST API with routers in `src/api/routers/`
   - Documentation at http://localhost:8000/docs
   - Routers: status, dashboard_v5, parameters, metrics, ai_agent, user_settings, ventilation, visualizations

## Database Schema (SQLite)

**Location:** `data/nibe_autotuner.db`

**Key Tables:**
- `parameter_readings` - Time-series data (main table, indexed on timestamp)
- `planned_heating_schedule` - 24h optimized heating plan (hourly granularity)
- `gm_account` - The "Bank" balance and mode
- `devices` - Heat pump devices with user settings (min/max temps, away mode)
- `parameters` - Parameter metadata (102 parameters from Nibe)
- `parameter_changes` - Manual/AI changes log
- `ab_test_results` - A/B test effectiveness tracking
- `ai_decisions` - AI decision log (deprecated, use PlannedHeatingSchedule)
- `learning_events` - Thermal property learning (time constants, thermal mass)
- `hot_water_usage` - Hot water usage pattern detection

## Key Control Parameters

| Parameter ID | Name | Read/Write | Purpose |
|--------------|------|------------|---------|
| 40004 | Outdoor Temp (BT1) | Read | Input for heating curve |
| 40008 | Supply Temp (BT2) | Read | Water temp to radiators |
| 40033 | Indoor Temp (BT50) | Read | Room temp measurement (Nibe sensor) |
| 40940 | Degree Minutes WRITE | Write | **PRIMARY CONTROL** - GM setpoint |
| 40941 | Degree Minutes READ | Read | Actual GM value from pump |
| 47007 | Heating Curve | Write | Slope (0-15), default 5.0 |
| 47011 | Curve Offset | Write | Offset (-10 to +10), controlled via smart_planner |
| VP_SYSTEM_MODE | System Mode | Virtual | 1=Heating, 2=HotWater, 3=Defrost |
| HA_TEMP_DOWNSTAIRS | Downstairs Temp | HA Sensor | Primary indoor temp (better than BT50) |
| HA_TEMP_DEXTER | Dexter Temp | HA Sensor | Secondary zone (min 20.0°C) |

## Common Development Commands

### Setup
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (copy .env.example to .env first)
cp .env.example .env
# Edit .env with myUplink credentials and Home Assistant URL
```

### Running Services Manually (Development)
```bash
# Data collection (single run)
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/data/data_logger.py --once

# Data collection (continuous)
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/data/data_logger.py --interval 300

# Smart planner (generate plan)
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/smart_planner.py

# GM Controller (run control loop)
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/gm_controller.py

# Mobile app (dashboard)
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/mobile/mobile_app.py

# API server
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/api/api_server.py
```

### Production Deployment
```bash
# Deploy script (commits, pushes, syncs to RPi, restarts services)
./deploy_v4.sh

# Check service status
sudo systemctl status nibe-autotuner
sudo systemctl status nibe-gm-controller
sudo systemctl status nibe-mobile

# View logs
journalctl -u nibe-autotuner -f
journalctl -u nibe-gm-controller -f
journalctl -u nibe-mobile -f
```

### Database Operations
```bash
# Open database
sqlite3 data/nibe_autotuner.db

# Check recent readings
sqlite3 data/nibe_autotuner.db "SELECT p.parameter_id, p.parameter_name, r.value, r.timestamp
FROM parameter_readings r
JOIN parameters p ON r.parameter_id = p.id
WHERE r.timestamp > datetime('now', '-1 hour')
ORDER BY r.timestamp DESC LIMIT 20;"

# Check current plan
sqlite3 data/nibe_autotuner.db "SELECT * FROM planned_heating_schedule WHERE timestamp > datetime('now') ORDER BY timestamp LIMIT 24;"

# Check GM account balance
sqlite3 data/nibe_autotuner.db "SELECT * FROM gm_account;"
```

### Testing
```bash
# Run tests
pytest tests/

# Test myUplink API connection
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/test_api.py

# Test write access to pump
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/test_write_access.py
```

## Architecture Details

### The "Bank" Concept (GM Controller)
The GM Controller simulates Nibe's internal Degree Minutes counter locally:
- **Deposits (positive GM):** Supply temp exceeds target → building heat surplus
- **Withdrawals (negative GM):** Supply temp below target → accumulating heat debt
- **Transaction:** `delta_gm = (actual_supply - target_supply) * minutes`
- **Pause conditions:** Hot water production, defrost mode
- **Write strategy:** Only write to pump when deviation >50 GM or target changed >10 GM (reduces API calls)

### Smart Planner Optimization
Uses deterministic thermal model to predict indoor temps 24h ahead:
- **Inputs:** Outdoor temp forecast, electricity price forecast, current indoor temp
- **Outputs:** Optimal offset schedule (24 hourly values)
- **Constraints:** Indoor temp must stay 20.5-22.0°C (configurable per device)
- **Objective:** Minimize `sum(price * heating_cost)` subject to comfort constraints
- **Thermal model:** First-order thermal differential equation (see `services/optimizer.py`)

### Safety Mechanisms
1. **Bastu-vakt:** If indoor >23.5°C, force GM=100 (stop heating)
2. **Anti-windup:** Clamp GM balance to [-2000, 200]
3. **Critical temp protection:** If indoor <19°C, enforce GM ≥ -350 (allow electric heater)
4. **Dexter protection:** If Dexter zone <20.0°C, use equivalent temp for planning

### Configuration System
Centralized in `src/core/config.py` using Pydantic Settings:
- `SHUNT_LIMIT = 32.0` - Max supply temp
- `DEFAULT_HEATING_CURVE = 5.0` - Base curve slope
- `DATABASE_URL = "sqlite:///./data/nibe_autotuner.db"`
- Ports: `API_PORT=8000`, `MOBILE_PORT=5001`

All settings can be overridden via environment variables (e.g., `export HEATING_CURVE=6.0`).

## Important Implementation Notes

### PYTHONPATH Requirements
When running scripts, ALWAYS set `PYTHONPATH=/home/peccz/AI/nibe_autotuner/src` to ensure imports work correctly:
```bash
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/gm_controller.py
```

### myUplink API Rate Limits
- Free tier: 15 requests per minute
- Data logger runs every 5 min = 3 requests/min (safe)
- GM controller runs every 1 min but only writes occasionally

### Home Assistant Integration
The system fetches sensors from Home Assistant REST API:
- Requires `HA_URL` and `HA_TOKEN` in `.env`
- Critical sensors: `sensor.dexter_temperature`, `sensor.downstairs_temperature`
- Wind sensor: Used for heat loss calculations in optimizer

### Database Migrations
Alembic migrations are in `src/data/migrate_*.py`. When adding new columns:
1. Create migration script (e.g., `migrate_add_new_feature.py`)
2. Import `Base` from `data.database`, not `models`
3. Test on dev database before deploying

### Testing Philosophy
- Unit tests for core logic (optimizer, thermal model)
- Integration tests for API clients
- Manual testing on Raspberry Pi before production deployment
- **No automated tests for hardware writes** - too risky on real heat pump

## Version History References

- **V8.0:** Deterministic Control System (removed AI agent, pure P-controller)
- **V10.1:** GM Controller with Hot Water awareness (pause bank during HW)
- **V12.0:** Current - Proactive optimizer with 24h price/weather forecasting

See `TO_CLAUDE.md` for detailed design decisions and architectural rationale.
See `PROJECT_SUMMARY.md` for archaeology and system status summary.
See `docs/` for scientific baselines, parameters, and database design.

## When Making Changes

1. **Never bypass safety limits:** MIN_BALANCE=-2000, MAX_BALANCE=200, Bastu-vakt threshold=23.5°C
2. **Test GM writes carefully:** Incorrect GM values can make house too cold/hot
3. **Preserve dual-zone logic:** Dexter (office) has separate minimum (20.0°C) vs downstairs (20.5°C)
4. **Check PYTHONPATH:** Import errors are almost always due to missing PYTHONPATH
5. **Commit before deploy:** `deploy_v4.sh` includes git commit/push
6. **Monitor logs after changes:** `journalctl -u nibe-gm-controller -f` shows real-time control decisions

## Useful Queries

### Check if optimizer is working
```sql
SELECT timestamp, planned_action, planned_offset, electricity_price, simulated_indoor_temp
FROM planned_heating_schedule
WHERE timestamp > datetime('now')
ORDER BY timestamp LIMIT 10;
```

### Verify GM controller is active
```sql
SELECT * FROM gm_account;
-- Should have recent last_updated timestamp
```

### Find recent parameter changes
```sql
SELECT pc.timestamp, p.parameter_name, pc.old_value, pc.new_value, pc.reason
FROM parameter_changes pc
JOIN parameters p ON pc.parameter_id = p.id
ORDER BY pc.timestamp DESC LIMIT 10;
```

### Debug stuck system mode
```sql
SELECT r.timestamp, p.parameter_name, r.value
FROM parameter_readings r
JOIN parameters p ON r.parameter_id = p.id
WHERE p.parameter_id = 'VP_SYSTEM_MODE'
ORDER BY r.timestamp DESC LIMIT 20;
```
