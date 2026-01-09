# Nibe Autotuner V4.0 - Context Snapshot (2026-01-09)

## Current Status: READY FOR DEPLOYMENT
We have completed the full intelligence upgrade to Version 4.0. All code is written and saved locally in `/home/peccz/AI/nibe_autotuner`.

## Key Implementations:
1.  **SmartPlanner 4.0:** 
    - Physical Multi-Zone logic (Downstairs slab vs Upstairs radiators).
    - Wind Direction awareness (West wind penalty for Dexter's room).
    - COP Shield (Defrost penalty if Temp < 5C and Humidity > 80%).
    - Delta-T driven physics engine.
2.  **Ventilation Manager 4.0:**
    - Humidity preservation (slowing fan to 30% if dry).
    - Rapid shower detection (using derivative of humidity).
    - Frost Guard (Overriding fan speed based on BT16 evaporator temp and Compressor Hz).
3.  **The Scientist 4.0:**
    - Nightly AI calibration of: `thermal_leakage`, `rad_efficiency`, `thermal_inertia_lag`, `internal_heat_gain`, and `wind_direction_west_factor`.
4.  **UI / API V4.0:**
    - New endpoint `/api/v4/dashboard` delivering high-fidelity data.
    - New HTML dashboard (`dashboard_v4.html`) with Dark Mode, Glassmorphism, and 24h predictive timeline.

## Pending Actions (Next Session):
1.  **Upload files to RPi:** Sync `src/data/models.py`, `src/api_server.py`, `src/services/smart_planner.py`, `src/services/ventilation_manager.py`, and `src/mobile/templates/dashboard_v4.html`.
2.  **Database Migration:** Verify the new columns (`wind_speed`, `wind_direction`) in `planned_heating_schedule`.
3.  **Restart Services:** Execute `sudo systemctl restart nibe-api nibe-autotuner`.

## Critical Parameters:
- **47273:** Speed 2 (Normal Fan Speed) - Set to 50.0% standard.
- **50005:** Increased Ventilation (Boost) - Binary switch.
- **40020:** BT16 (Evaporator Temp) - Used for Frost Guard.
- **41778:** Compressor Hz - Used for Frost Guard and load analysis.
- **47011:** Curve Offset - Used for "Radiator Blasts".
