"""
Scientist Module: Advanced AI Calibration V4.0
Calibrates wind direction factors, thermal lag, and internal heat gain.
"""
import sys
import os
import json
from datetime import datetime, timedelta
from loguru import logger
import sqlite3
import pandas as pd
import google.generativeai as genai

sys.path.append('src')
from core.config import settings

def run_daily_calibration():
    logger.info("Starting Multi-Zone AI Calibration (Scientist 4.0)...")
    
    if not settings.GOOGLE_API_KEY: return

    # Resolve DB path from settings
    db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        # Handle relative paths (e.g., ./data/...)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_path.startswith('./'):
            db_path = os.path.join(project_root, db_path[2:])
        else:
            db_path = os.path.join(project_root, db_path)

    conn = sqlite3.connect(db_path)
    
    start_time = datetime.utcnow() - timedelta(hours=24)
    
    # Load all relevant data
    query = """
    SELECT r.timestamp, p.parameter_id, r.value 
    FROM parameter_readings r 
    JOIN parameters p ON r.parameter_id = p.id 
    WHERE r.timestamp >= ? 
    AND p.parameter_id IN ('HA_TEMP_DOWNSTAIRS', 'HA_TEMP_DEXTER', '40004', '41778')
    """
    df = pd.read_sql_query(query, conn, params=(start_time,))
    
    tuning_res = conn.execute("SELECT parameter_id, value FROM system_tuning").fetchall()
    current_tuning = {row[0]: row[1] for row in tuning_res}
    
    summary = df.groupby('parameter_id')['value'].agg(['mean', 'min', 'max']).to_dict()
    
    prompt = f"""
    You are a building physics expert. Calibrate this house model.
Current Tuning: {json.dumps(current_tuning)}
Yesterday's Summary: {json.dumps(summary)}
    
    Goal: Update these factors based on the observed response:
    - 'thermal_leakage': Overall heat loss rate.
    - 'rad_efficiency': How much 1C of supply delta heats Dexter's room.
    - 'wind_direction_west_factor': Does west wind cool Dexter's room faster?
    - 'thermal_inertia_lag': Minutes of delay before room reacts to pump.
    - 'internal_heat_gain': Base C/h rise from resident activity.
    
    Respond ONLY with JSON.
    """

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-3-pro-preview')
    
    try:
        response = model.generate_content(prompt)
        new_values = json.loads(response.text.strip('`json \n'))
        for pid, val in new_values.items():
            if pid in current_tuning:
                conn.execute("UPDATE system_tuning SET value = ? WHERE parameter_id = ?", (float(val), pid))
                logger.info(f"  ✓ Calibrated {pid} -> {val}")
        conn.commit()
    except Exception as e:
        logger.error(f"Calibration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_daily_calibration()