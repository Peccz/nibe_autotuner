"""
Smart Planner V12.0 (The Optimizer)
Uses deterministic simulation and optimization to schedule heating.
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
from services.optimizer import optimize_24h_plan, predict_temperatures

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
    logger.info("Starting V13.0 Optimizer...")
    conn = get_db_connection()
    weather_service = SMHIWeatherService()

    # 0. Load device settings (comfort temps + away mode)
    device_row = conn.execute("""
        SELECT away_mode_enabled, away_mode_end_date,
               target_indoor_temp_min, target_indoor_temp_max,
               min_indoor_temp_user_setting
        FROM devices LIMIT 1
    """).fetchone()

    away_mode = False
    opt_min_temp = settings.OPTIMIZER_MIN_TEMP
    opt_target_temp = settings.OPTIMIZER_TARGET_TEMP

    if device_row:
        away_enabled = bool(device_row[0])
        away_end_str = device_row[1]
        away_end = datetime.fromisoformat(away_end_str) if away_end_str else None

        if away_enabled and (away_end is None or away_end > datetime.now(timezone.utc).replace(tzinfo=None)):
            away_mode = True
            opt_min_temp = 16.0
            opt_target_temp = 17.0
            logger.info("BORTA-LÄGE aktivt — optimerar för 16–17°C")
        else:
            # Use per-device comfort settings if configured
            if device_row[2]:
                opt_min_temp = float(device_row[2])
            if device_row[3]:
                opt_target_temp = float(device_row[3])

    # 1. Get Current Status (Start Point)
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

    # Priority Logic (Safety)
    min_dexter = opt_min_temp - 0.5  # Dexter's floor is 0.5°C below main floor
    max_dexter = opt_target_temp      # Dexter's ceiling = same as main max (e.g. 22°C)

    start_temp = opt_target_temp  # Default fallback

    if downstairs is None:
        start_temp = dexter if dexter is not None else opt_target_temp
    else:
        start_temp = downstairs
        if dexter is not None and dexter < min_dexter:
            # Too cold in Dexter's room → raise effective start temp (heat more)
            dexter_equiv = dexter + 1.5
            if dexter_equiv < start_temp:
                start_temp = dexter_equiv
                logger.info(f"Using Dexter (Equiv {dexter_equiv:.2f}C) as start temp.")
        elif dexter is not None and dexter > max_dexter:
            # Too warm in Dexter's room → raise effective start temp (heat less)
            dexter_equiv = dexter - 1.5
            if dexter_equiv > start_temp:
                start_temp = dexter_equiv
                logger.info(f"Dexter for varm ({dexter:.2f}C > {max_dexter:.2f}C). Equiv {dexter_equiv:.2f}C som starttemp.")

    # 2. Get Data for Next 24h
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    
    # Prices
    prices_today = price_service.get_prices_today()
    prices_tomorrow = price_service.get_prices_tomorrow()
    all_prices = prices_today + prices_tomorrow
    
    # Weather
    forecasts = weather_service.get_forecast()
    
    # Align Data
    price_list = []
    outdoor_list = []
    
    for i in range(24):
        future_time = now + timedelta(hours=i)

        # Price — normalise both sides to UTC to avoid CET/CEST offset mismatch
        p_obj = next(
            (p for p in all_prices
             if p.time_start.astimezone(timezone.utc).hour == future_time.hour
             and p.time_start.astimezone(timezone.utc).day == future_time.day),
            None
        )
        price_list.append(p_obj.price_per_kwh if p_obj else 1.0)
        
        # Weather (Outdoor Temp)
        w_obj = next((f for f in forecasts if f.timestamp.hour == future_time.hour and f.timestamp.day == future_time.day), None)
        outdoor_list.append(w_obj.temperature if w_obj else -5.0)

    # 3. Run Optimization
    offsets = optimize_24h_plan(start_temp, outdoor_list, price_list,
                                min_temp=opt_min_temp, target_temp=opt_target_temp)
    
    # 4. Save Plan
    plan_rows = []
    simulated_temps = predict_temperatures(start_temp, outdoor_list, offsets)
    
    for i in range(24):
        future_time = now + timedelta(hours=i)
        
        # Action Logic
        action = "RUN"
        if offsets[i] <= settings.OPTIMIZER_REST_THRESHOLD:
            action = "REST"
        
        plan_rows.append((
            future_time,
            action,
            float(offsets[i]),
            price_list[i],
            simulated_temps[i], # Downstairs sim
            simulated_temps[i] - 1.5, # Dexter sim (approx)
            outdoor_list[i],
            0 # Wind
        ))

    # Use explicit transaction to prevent race condition with gm_controller
    try:
        conn.execute("BEGIN EXCLUSIVE")
        conn.execute("DELETE FROM planned_heating_schedule")
        conn.executemany("""
            INSERT INTO planned_heating_schedule
            (timestamp, planned_action, planned_offset, electricity_price,
             simulated_indoor_temp, simulated_dexter_temp, outdoor_temp, wind_speed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, plan_rows)
        conn.commit()
        logger.success("✓ V12.0 Optimized Plan Generated.")
    except Exception as e:
        conn.rollback()
        logger.error(f"✗ Failed to update heating schedule: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    calculate_plan()
