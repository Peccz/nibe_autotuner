"""
Deterministic Control System V8.0
Replaces AI prediction with Industrial Control Theory (P-Controller + Eco-Factor).
"""
import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta, timezone
from loguru import logger

sys.path.append('src')
from core.config import settings
from services.price_service import price_service
from services.weather_service import SMHIWeatherService

# --- CONTROL PARAMETERS (DEFAULTS) ---
TARGET_TEMP = 21.5        # Main target for downstairs
MIN_DEXTER = 20.0         # Safety minimum for upstairs
DEFAULT_K_P = 2.5         # Proportional Gain (Milder)
DEFAULT_K_ECO = 3.0       # Economic Gain
OFFSET_MIN = -10.0
OFFSET_MAX = 5.0

def get_db_connection():
    db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_path.startswith('./'):
            db_path = os.path.join(project_root, db_path[2:])
        else:
            db_path = os.path.join(project_root, db_path)
    return sqlite3.connect(db_path)

def get_tuning_param(conn, param_id, default_val):
    try:
        res = conn.execute("SELECT value FROM system_tuning WHERE parameter_id=?", (param_id,)).fetchone()
        return float(res[0]) if res else default_val
    except Exception:
        return default_val

def calculate_plan():
    logger.info("Starting Deterministic Control V8.1 (Dual-Zone Priority)...")
    conn = get_db_connection()
    
    # Load Tuning
    K_P = get_tuning_param(conn, 'control_kp', DEFAULT_K_P)
    K_ECO = get_tuning_param(conn, 'control_keco', DEFAULT_K_ECO)
    OFFSET_BIAS = get_tuning_param(conn, 'control_bias', 0.0)
    
    # 1. Get Current Status
    query = """
    SELECT p.parameter_id, r.value 
    FROM parameter_readings r 
    JOIN parameters p ON r.parameter_id = p.id 
    WHERE r.timestamp > datetime('now', '-1 hour')
    AND p.parameter_id IN ('HA_TEMP_DOWNSTAIRS', 'HA_TEMP_DEXTER', '40004')
    ORDER BY r.timestamp DESC
    """
    df = pd.read_sql_query(query, conn)
    
    dexter = df[df['parameter_id']=='HA_TEMP_DEXTER']['value'].iloc[0] if not df[df['parameter_id']=='HA_TEMP_DEXTER'].empty else None
    downstairs = df[df['parameter_id']=='HA_TEMP_DOWNSTAIRS']['value'].iloc[0] if not df[df['parameter_id']=='HA_TEMP_DOWNSTAIRS'].empty else None
    outdoor = df[df['parameter_id']=='40004']['value'].iloc[0] if not df[df['parameter_id']=='40004'].empty else 0.0
    
    # --- DUAL ZONE PRIORITY LOGIC ---
    if downstairs is None:
        indoor_ref = dexter if dexter is not None else TARGET_TEMP
    else:
        # Normal Case: Aim for 21.5 downstairs
        indoor_ref = downstairs
        
        # Safety: If Dexter is too cold, he takes priority
        if dexter is not None and dexter < MIN_DEXTER:
            # We map Dexter's 20.0 to Downstairs' 21.5 (compensating for the 1.5C diff)
            dexter_equivalent = dexter + 1.5
            if dexter_equivalent < indoor_ref:
                logger.warning(f"Dexter priority! {dexter}C is below {MIN_DEXTER}C.")
                indoor_ref = dexter_equivalent

    logger.info(f"Status: InRef={indoor_ref:.2f}C (Target {TARGET_TEMP}), Outdoor={outdoor}C")

    # 2. Get Prices (Next 12h)
    prices_today = price_service.get_prices_today()
    prices_tomorrow = price_service.get_prices_tomorrow()
    all_prices = prices_today + prices_tomorrow
    
    # Filter: Keep prices from current hour onwards
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    prices = [p for p in all_prices if p.time_start >= now]

    if not prices:
        logger.warning("No price data. Assuming average 1.0.")
        avg_price = 1.0
        # Create dummy data
        from dataclasses import dataclass
        @dataclass
        class DummyPrice:
            time_start: datetime
            price_per_kwh: float
        prices = [DummyPrice(now + timedelta(hours=i), 1.0) for i in range(12)]
    else:
        avg_price = sum(p.price_per_kwh for p in prices) / len(prices)

    # 3. Calculate Plan for Next 6 Hours
    plan_rows = []
    
    for i in range(6):
        future_time = now + timedelta(hours=i)
        
        # Find price for this hour
        price_obj = next((p for p in prices if p.time_start.hour == future_time.hour and p.time_start.day == future_time.day), None)
        price = price_obj.price_per_kwh if price_obj else avg_price
        
        # --- THE ALGORITHM ---
        
        # P-Term (Temperature Error)
        # Error > 0 means too cold -> Positive Offset
        error = TARGET_TEMP - indoor_ref
        p_term = error * K_P
        
        # Eco-Term (Price Deviation)
        # Price < Avg means Cheap -> Positive Offset
        if avg_price > 0:
            price_ratio = price / avg_price
            eco_term = (1.0 - price_ratio) * K_ECO
        else:
            eco_term = 0
            
        # Total
        raw_offset = p_term + eco_term + OFFSET_BIAS
        
        # Safety Clamping
        final_offset = max(OFFSET_MIN, min(OFFSET_MAX, round(raw_offset)))
        
        # Action Logic
        # Default to RUN (Pump is permitted to run according to curve + offset)
        action = "RUN"
        
        # Only set REST (Blocking) if we are actively braking hard
        if final_offset <= -3: 
            action = "REST"
        
        logger.info(f"Hour +{i}: Price={price:.2f} (Ratio {price_ratio:.2f}) -> Eco={eco_term:.1f}, P-Term={p_term:.1f} -> Offset={final_offset}")
        
        plan_rows.append((
            future_time.replace(minute=0, second=0, microsecond=0),
            action,
            float(final_offset),
            price,
            downstairs if downstairs is not None else indoor_ref,
            dexter if dexter is not None else indoor_ref,
            outdoor,
            0 # Wind placeholder
        ))

    # 4. Commit to DB
    conn.execute("DELETE FROM planned_heating_schedule") # Clear old AI plans
    conn.executemany("""
        INSERT INTO planned_heating_schedule 
        (timestamp, planned_action, planned_offset, electricity_price, 
         simulated_indoor_temp, simulated_dexter_temp, outdoor_temp, wind_speed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, plan_rows)
    
    conn.commit()
    conn.close()
    logger.success("✓ Control System V8.0 updated plan.")

def plan_next_24h():
    """Wrapper for backward compatibility with main.py calls"""
    calculate_plan()

if __name__ == "__main__":
    calculate_plan()