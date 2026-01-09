"""
Scientist Module: Physics Calibration
Compares yesterday's simulation vs reality and updates model constants.
"""
import sys
import os
from datetime import datetime, timedelta
from loguru import logger
import sqlite3
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../../src'))

from core.config import settings

def get_param_id(cursor, name):
    cursor.execute("SELECT id FROM parameters WHERE parameter_id = ?", (name,))
    res = cursor.fetchone()
    return res[0] if res else None

def run_calibration():
    logger.info("Starting Physics Calibration (The Scientist)...")
    db_path = '/home/peccz/nibe_autotuner/data/nibe_autotuner.db'
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get IDs
        id_down = get_param_id(cursor, 'HA_TEMP_DOWNSTAIRS')
        id_dexter = get_param_id(cursor, 'HA_TEMP_DEXTER')
        id_comp = get_param_id(cursor, '41778') # Compressor Hz
        id_outdoor = get_param_id(cursor, '40004')

        if not all([id_down, id_dexter, id_comp, id_outdoor]):
            logger.error("Missing critical parameters for calibration. (Have you logged IKEA data yet?)")
            return

        # Analysis period: Last 24 hours
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=24)

        # 1. Load Data
        query = "SELECT timestamp, parameter_id, value FROM parameter_readings WHERE timestamp >= ? AND parameter_id IN (?, ?, ?, ?)"
        df = pd.read_sql_query(query, conn, params=(start_time, id_down, id_dexter, id_comp, id_outdoor))
        
        if df.empty or len(df) < 50:
            logger.warning("Insufficient data points for meaningful calibration.")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.pivot(index='timestamp', columns='parameter_id', values='value').resample('5T').mean().interpolate()
        
        # Rename columns for easier access
        mapping = {id_outdoor: 'outdoor', id_down: 'downstairs', id_dexter: 'dexter', id_comp: 'compressor'}
        df = df.rename(columns=mapping)
        
        # 2. Analyze Cooling (when compressor is OFF)
        cooling_df = df[df['compressor'] < 10].copy()
        if len(cooling_df) > 12: # At least 1 hour of cooling
            cooling_df['dt_down'] = cooling_df['downstairs'].diff()
            cooling_df['dt_dexter'] = cooling_df['dexter'].diff()
            cooling_df['delta_t'] = 21.0 - cooling_df['outdoor'] # Temp difference to outside
            
            # Calculate C/h loss
            loss_down = cooling_df['dt_down'].mean() * 12 # Hourly rate
            loss_dexter = cooling_df['dt_dexter'].mean() * 12
            avg_delta = cooling_df['delta_t'].mean()
            
            k_down = abs(loss_down / avg_delta) if avg_delta > 0 else 0.005
            k_dexter = abs(loss_dexter / avg_delta) if avg_delta > 0 else 0.007
            
            logger.info(f"CALIBRATION RESULT (Cooling):")
            logger.info(f"  Downstairs K-factor: {k_down:.5f} C/h per deg DeltaT")
            logger.info(f"  Dexter K-factor:     {k_dexter:.5f} C/h per deg DeltaT")
            logger.info(f"  Ratio (Dexter/Down): {k_dexter/k_down:.2f}x" if k_down > 0 else "  Ratio: N/A")

        # 3. Analyze Heating (when compressor is ON)
        heating_df = df[df['compressor'] > 30].copy()
        if len(heating_df) > 12:
            heating_df['dt_down'] = heating_df['downstairs'].diff()
            heating_df['dt_dexter'] = heating_df['dexter'].diff()
            
            gain_down = heating_df['dt_down'].mean() * 12
            gain_dexter = heating_df['dt_dexter'].mean() * 12
            
            logger.info(f"CALIBRATION RESULT (Heating):")
            logger.info(f"  Downstairs Gain: {gain_down:.3f} C/h")
            logger.info(f"  Dexter Gain:     {gain_dexter:.3f} C/h")
            logger.info(f"  Ratio (Dexter/Down): {gain_dexter/gain_down:.2f}x" if gain_down > 0 else "  Ratio: N/A")

        conn.close()
        logger.info("Calibration complete. Results logged to console.")

    except Exception as e:
        logger.error(f"Error during calibration: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_calibration()
