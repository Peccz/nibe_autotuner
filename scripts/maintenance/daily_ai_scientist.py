"""
Scientist Module: Advanced AI Calibration V6.0 (Stability & Isolation)
Implements robust control theory to calibrate house physics without drift.
"""
import sys
import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

sys.path.append('src')
from core.config import settings

# --- CONSTANTS & SAFETY BOUNDS ---
MIN_LEAKAGE = 0.005
MAX_LEAKAGE = 0.015
MIN_RAD_EFF = 0.005
MAX_RAD_EFF = 0.020

# Inertia: How much of the NEW value do we accept per day? (0.1 = 10%)
LEARNING_RATE = 0.10 

def get_db_connection():
    db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_path.startswith('./'):
            db_path = os.path.join(project_root, db_path[2:])
        else:
            db_path = os.path.join(project_root, db_path)
    return sqlite3.connect(db_path)

def analyze_cooling_regime(df):
    """
    Isolates periods where:
    1. Compressor is OFF (< 5Hz)
    2. Night time (01:00 - 05:00) -> No Sun, No Activity
    3. No rapid drops (> 0.5C/h) -> No Open Windows
    """
    # Filter for Night & Off
    mask = (df.index.hour >= 1) & (df.index.hour <= 5) & \
           (df['41778'] < 5) & \
           (df.get('SOLAR_GAIN', 0) < 5)
    
    segment = df[mask]
    if len(segment) < 6: # Need at least 30 mins of data
        return None, None

    # Calculate Drop
    start_temp = segment['HA_TEMP_DEXTER'].iloc[0]
    end_temp = segment['HA_TEMP_DEXTER'].iloc[-1]
    duration_h = (segment.index[-1] - segment.index[0]).total_seconds() / 3600
    
    if duration_h < 0.5: return None, None

    temp_drop = start_temp - end_temp
    
    # Anomaly Detection: Window Open?
    drop_rate = temp_drop / duration_h
    if drop_rate > 0.5:
        logger.warning(f"  ⚠️ Anomalous drop rate ({drop_rate:.2f} C/h). Ignoring (Window?).")
        return None, None
        
    if drop_rate < 0:
        logger.warning(f"  ⚠️ Temp rose during cooling phase. Ignoring (Internal heat?).")
        return None, None

    # Calculate K-value (Leakage)
    # Formula: Rate = k * DeltaT
    avg_indoor = segment['HA_TEMP_DEXTER'].mean()
    avg_outdoor = segment['40004'].mean()
    delta_t = avg_indoor - avg_outdoor
    
    if delta_t < 5: return None, None # Too warm outside to measure leakage accurately

    k_leakage = drop_rate / delta_t
    return k_leakage, "Valid Night Cooling"

def analyze_heating_regime(df):
    """
    Isolates periods where:
    1. Compressor is RUNNING (> 40Hz)
    2. Heating Curve is active (Supply > 30C)
    3. Duration > 1h
    """
    mask = (df['41778'] > 40) & (df['40008'] > 30)
    segment = df[mask]
    
    if len(segment) < 12: # Need 1 hour
        return None

    # Calculate Rise
    start_temp = segment['HA_TEMP_DEXTER'].iloc[0]
    end_temp = segment['HA_TEMP_DEXTER'].iloc[-1]
    duration_h = (segment.index[-1] - segment.index[0]).total_seconds() / 3600
    
    rise_rate = (end_temp - start_temp) / duration_h
    
    # Physics: Rise = (Input - Loss) / Mass
    # Input = k_rad * (Supply - Indoor)^1.3
    # We approximate: k_rad = (RiseRate + Loss) / DeltaT_Emitter^1.3
    # Note: We need current leakage estimate for this.
    return None # TODO: Implement advanced solver. For now, we trust Manual Rad Efficiency.

def apply_stability_filter(current_val, measured_val, param_name):
    """
    Applies constraints and smoothing.
    """
    if measured_val is None:
        return current_val
    
    # 1. Hard Bounds
    if param_name == 'thermal_leakage_dexter':
        if measured_val < MIN_LEAKAGE: measured_val = MIN_LEAKAGE
        if measured_val > MAX_LEAKAGE: measured_val = MAX_LEAKAGE
    
    # 2. Moving Average (Inertia)
    new_val = (current_val * (1 - LEARNING_RATE)) + (measured_val * LEARNING_RATE)
    
    logger.info(f"  ⚖️ Stability: {param_name} | Old: {current_val:.5f} | Raw: {measured_val:.5f} | New: {new_val:.5f}")
    return new_val

def run_calibration():
    logger.info("Starting Scientist V6.0 (Stability Edition)...")
    conn = get_db_connection()
    
    # Load Data
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=24)
    query = """
    SELECT r.timestamp, p.parameter_id, r.value 
    FROM parameter_readings r 
    JOIN parameters p ON r.parameter_id = p.id 
    WHERE r.timestamp >= ? 
    AND p.parameter_id IN ('HA_TEMP_DOWNSTAIRS', 'HA_TEMP_DEXTER', '40004', '41778', '40008', 'SOLAR_GAIN')
    ORDER BY r.timestamp ASC
    """
    df = pd.read_sql_query(query, conn, params=(start_time,))
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    pivoted = df.pivot_table(index='timestamp', columns='parameter_id', values='value').ffill().dropna()
    
    # --- 1. Calibrate Leakage (Dexter) ---
    current_leak = conn.execute("SELECT value FROM system_tuning WHERE parameter_id='thermal_leakage_dexter'").fetchone()
    current_leak = current_leak[0] if current_leak else 0.009
    
    raw_leak, reason = analyze_cooling_regime(pivoted)
    
    if raw_leak:
        new_leak = apply_stability_filter(current_leak, raw_leak, 'thermal_leakage_dexter')
        conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)",
                     ('thermal_leakage_dexter', new_leak, f"V6: {reason}"))
        conn.commit()
        logger.success(f"Updated Leakage: {new_leak:.5f}")
    else:
        logger.info("No valid cooling regime found. Keeping leakage constant.")

    # --- 2. Calibrate Leakage (Downstairs) ---
    # TODO: Similar logic for downstairs if needed.

    conn.close()

if __name__ == "__main__":
    run_calibration()