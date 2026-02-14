# Nibe Autotuner - Project Archaeology & Status

Generated: sön  1 feb 2026 19:59:27 CET

## Source Code Analysis
### src/core/config.py
- **Purpose:** Centralized configuration via Pydantic Settings.
- **Status:** Active (V8.0).
- **Key Params:** SHUNT_LIMIT=32.0, HEATING_CURVE=5.0, PORTS=8000/5001.

### src/services/smart_planner.py
- **Purpose:** Deterministic P-Controller for Heating Offset.
- **Status:** Active (V8.0).
- **Logic:** Offset = (Target - Actual)*Kp + (1 - PriceRatio)*Keco.
- **Safety:** Clamps offset between -10 and +5.

### src/services/gm_controller.py
- **Purpose:** The Bank. Manages GM budget and writes to pump.
- **Status:** Active (V8.0).
- **Safety:** Includes 'Bastu-vakt' (Force stop > 23.5C) and Anti-Windup.

### src/api/api_server.py
- **Purpose:** Modern FastAPI backend (Port 8000).
- **Status:** Active (V8.0).
- **Modules:** Integrates routers for Status, Plan, AI, Settings.

### src/mobile/mobile_app.py
- **Purpose:** Legacy Flask Dashboard (Port 5001).
- **Status:** Active (V8.0).
- **Note:** Serves the main UI used by the user.

### src/data/data_logger.py
- **Purpose:** Core service. Logs Nibe, HA, and Weather data.
- **Status:** Active (V8.0).
- **Features:** Handles stuck Nibe timestamps, integrates multiple data sources.

## Scripts Analysis
### deploy_v4.sh
- **Purpose:** Robust deployment script. Git commit + Push + Rsync + Restart.
- **Status:** Active.

## Database Structure
- **Type:** SQLite (data/nibe_autotuner.db)
- **Key Tables:** parameter_readings, planned_heating_schedule, gm_account (The Bank).

## Logic Audit (V8.0)
- **Data Flow:** HA Sensors -> Data Logger -> DB -> Smart Planner -> DB -> GM Controller -> Nibe API.
- **Smart Planner:** Pure P-Controller. Robust but naive.
- **GM Controller:** Holds the 'Bank' logic. Safety overrides (Bastu-Vakt, Anti-Windup) are critical.
- **Weakness:** High dependency on HA sensor freshness. GM sync tolerance (500) is too loose.

## Upgrade to V12.0 (Proactive Control)
- **Problem:** P-controller is reactive and lags behind rapid outdoor temperature drops.
- **Solution:** Add D-Term (Trend) and Weather Feed-forward (Forecast).
- **Kd (Derivative):** Reacts to rate of indoor temp change.
- **Kw (Weather):** Anticipates outdoor temp drops using SMHI data.

## V12.0: The Deterministic Optimizer
- **Method:** Price/COP Ranking & Thermal Buffering.
- **Proactive:** Uses 24h price and weather forecast to pre-heat.
- **Safety:** Enforces comfort limits by raising 'water level' of acceptable price.

