"""
Deterministic Control System V8.0
Replaces AI prediction with Industrial Control Theory (P-Controller + Eco-Factor).
"""
import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger

sys.path.append('src')
from core.config import settings
from services.price_service import price_service
from services.weather_service import SMHIWeatherService

# --- CONTROL PARAMETERS ---
TARGET_TEMP = 21.0
K_P = 4.0         # Proportional Gain (Temp Error)
K_ECO = 3.0       # Economic Gain (Price Factor)
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

def calculate_plan():
    logger.info("Starting Deterministic Control V8.0...")
    conn = get_db_connection()
    
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
    
    # Safety fallback
    if dexter is None and downstairs is None:
        logger.error("No indoor temp data! Defaulting to Offset 0.")
        indoor_temp = TARGET_TEMP
    else:
        # Use the COLDEST room to determine need
        valid_temps = [t for t in [dexter, downstairs] if t is not None]
        indoor_temp = min(valid_temps)

    logger.info(f"Status: Indoor={indoor_temp}C (Target {TARGET_TEMP}), Outdoor={outdoor}C")

    # 2. Get Prices (Next 12h)
    prices = price_service.get_prices(hours=12)
    if not prices:
        logger.warning("No price data. Assuming average.")
        avg_price = 1.0
        prices = [{'time_start': datetime.utcnow() + timedelta(hours=i), 'SEK_per_kWh': 1.0} for i in range(12)]
    else:
        avg_price = sum(p['SEK_per_kWh'] for p in prices) / len(prices)

    # 3. Calculate Plan for Next 6 Hours
    plan_rows = []
    
    for i in range(6):
        future_time = datetime.utcnow() + timedelta(hours=i)
        
        # Find price for this hour
        price = next((p['SEK_per_kWh'] for p in prices if p['time_start'].hour == future_time.hour), avg_price)
        
        # --- THE ALGORITHM ---
        
        # P-Term (Temperature Error)
        # Error > 0 means too cold -> Positive Offset
        error = TARGET_TEMP - indoor_temp
        p_term = error * K_P
        
        # Eco-Term (Price Deviation)
        # Price < Avg means Cheap -> Positive Offset
        if avg_price > 0:
            price_ratio = price / avg_price
            eco_term = (1.0 - price_ratio) * K_ECO
        else:
            eco_term = 0
            
        # Total
        raw_offset = p_term + eco_term
        
        # Safety Clamping
        final_offset = max(OFFSET_MIN, min(OFFSET_MAX, round(raw_offset)))
        
        # Action Logic
        action = "RUN"
        if final_offset < -2: action = "REST" # If we brake hard, we rest.
        if final_offset > 0: action = "RUN"
        
        logger.info(f"Hour +{i}: Price={price:.2f} (Ratio {price_ratio:.2f}) -> Eco={eco_term:.1f}, P-Term={p_term:.1f} -> Offset={final_offset}")
        
        plan_rows.append((
            future_time.replace(minute=0, second=0, microsecond=0),
            action,
            float(final_offset),
            price,
            indoor_temp, # Simulated is now just "Current" (No physics prediction)
            indoor_temp,
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