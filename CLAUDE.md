# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Primary Reference

**Read `DNA.md` before doing anything else.** It is the single source of truth for this project — architecture, canonical files, safety constraints, known pitfalls, and AI agent protocol.

After reading DNA.md, acknowledge with **"DNA.md läst"** before starting work.

---

## Quick Reference

**Active planner:** V16 robust planner (`PLANNER_ENGINE=v16_active` in `.env` on the RPi).
The optimizer base (`src/services/optimizer.py`) is still the V14.0 two-zone model; V15 and V16 are layered planning engines selected at runtime, **not** separate code branches.

### Planner engine switch (`PLANNER_ENGINE`)
`smart_planner.py` picks which plan it writes to `planned_heating_schedule` based on `settings.PLANNER_ENGINE` (config default `v15_shadow`; production RPi `v16_active`):
- `v14` — V14 two-zone writer (base fallback)
- `v15_shadow` — computes V15 for comparison/logging but **writes the V14 plan**
- `v15_active` — writes the V15 plan (falls back to V14 if V15 fails)
- `v16_active` — writes the V16 robust plan (falls back to V15/V14 if V16 fails)

V16 prioritizes comfort/safety → over-heat shedding → price (in that order), and blocks positive offset/BOOST outside the morning window, during current over-heat, at the ventilation cap, or when price data falls back to 1.0 SEK/kWh. Note DNA.md section 1 still labels the system "V14.0"; section 11 (Active Work & State) is the authoritative record of what is actually deployed.

### Three Critical Services
1. `data_logger.py` — every 5 min, fetches myUplink + HA + Open-Meteo
2. `smart_planner.py` — every hour (systemd timer), 24h optimization plan
3. `gm_controller.py` — every 1 min, writes GM setpoint (40940) to pump

### Canonical files live in `src/` — the repo root is full of legacy scratch
The repository root contains many one-off, superseded scratch files (`fix_*.py`, `update_*.py`, `patch_*.py`, `models_*.py`, `mobile_app*.py`, `analyzer_*.py`, `*_v2`, `temp_*`). **These are NOT canonical and must not be edited or imported.** The real code is under `src/` only — see DNA.md section 3 for the canonical file map. Never create `_v2`/`_final`/`_fixed` variants; edit the canonical file in place.

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
./deploy_v4.sh   # commit + push + rsync to RPi (100.100.118.62) + pip install + migrate + restart

sudo systemctl status nibe-autotuner
sudo systemctl status nibe-gm-controller
journalctl -u nibe-gm-controller -f
```
**Note:** `deploy_v4.sh` restarts `nibe-autotuner`, `nibe-api`, `nibe-gm-controller` and enables the `nibe-smart-planner` timer, but does **not** restart `nibe-mobile` — restart it manually if the dashboard changed. Service files in the repo use the dev path `/home/peccz/AI/nibe_autotuner`; the deploy script `sed`s them to the RPi path `/home/peccz/nibe_autotuner`.

### Key Database Queries
```bash
sqlite3 data/nibe_autotuner.db "SELECT * FROM gm_account;"
sqlite3 data/nibe_autotuner.db "SELECT timestamp, planned_action, planned_offset, electricity_price, simulated_indoor_temp FROM planned_heating_schedule WHERE timestamp > datetime('now') ORDER BY timestamp LIMIT 10;"
```

### Testing
`pytest.ini` sets `testpaths = tests`, so `pytest` alone runs the suite. Tests import from `src/`, so set PYTHONPATH:
```bash
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src pytest                              # full suite
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src pytest tests/test_safety_guardrails.py   # one file
PYTHONPATH=/home/peccz/AI/nibe_autotuner/src pytest tests/test_v15_backtest.py -k mpc # one test by name
```
Safety/control regressions live in `tests/test_safety_guardrails*.py`, `tests/test_gm_controller_warm_override.py`, and `tests/test_v15_*` — run these after any optimizer, planner, or GM-controller change.

---

See `DNA.md` for complete architecture, design decisions, known pitfalls, and optimizer constants.
See `docs/` for scientific baselines, parameters, and database design.
