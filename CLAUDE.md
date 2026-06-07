# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Primary Reference

**Read `DNA.md` before doing anything else.** It is the single source of truth for this project — architecture, canonical files, safety constraints, known pitfalls, and AI agent protocol.

After reading DNA.md, acknowledge with **"DNA.md läst"** before starting work.

---

## Quick Reference

**Current Version:** V14.0 (Tvåzons Proaktiv Optimering)

### Three Critical Services
1. `data_logger.py` — every 5 min, fetches myUplink + HA + Open-Meteo
2. `smart_planner.py` — every hour (systemd timer), 24h optimization plan
3. `gm_controller.py` — every 1 min, writes GM setpoint (40940) to pump

### Safety Limits (NEVER touch without explicit approval)
- `MIN_BALANCE = -2000`
- `MAX_BALANCE = 200`
- `BASTU_VAKT = 23.5°C`
- `CRITICAL_TEMP_LIMIT = 19.0°C`

### PYTHONPATH (CRITICAL)
Always set when running scripts manually:
```bash
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/gm_controller.py
```

### Running Services Manually
```bash
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/data/data_logger.py --once
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/smart_planner.py
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/services/gm_controller.py
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/mobile/mobile_app.py
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/api/api_server.py
```

### Production Deployment
```bash
./deploy_v4.sh   # commit + rsync to RPi + restart services

sudo systemctl status nibe-autotuner
sudo systemctl status nibe-gm-controller
journalctl -u nibe-gm-controller -f
```

### Key Database Queries
```bash
sqlite3 data/nibe_autotuner.db "SELECT * FROM gm_account;"
sqlite3 data/nibe_autotuner.db "SELECT timestamp, planned_action, planned_offset, electricity_price, simulated_indoor_temp FROM planned_heating_schedule WHERE timestamp > datetime('now') ORDER BY timestamp LIMIT 10;"
```

### Testing
```bash
pytest tests/
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src python src/test_api.py
```

---

See `DNA.md` for complete architecture, design decisions, known pitfalls, and optimizer constants.
See `docs/` for scientific baselines, parameters, and database design.
