"""
The Governor (Scientist V9.0)
Automated Control Loop Tuning based on Empirical Data.
"""
import sys
import os
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

sys.path.append('src')
from core.config import settings

def get_db_connection():
    db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_path.startswith('./'):
            db_path = os.path.join(project_root, db_path[2:])
        else:
            db_path = os.path.join(project_root, db_path)
    return sqlite3.connect(db_path)

def analyze_system_dynamics(conn):
    """
    Analyzes last 7 days to find:
    1. Holding Offset (Bias)
    2. System Power (Kp calibration)
    """
    logger.info("Governor: Analyzing system dynamics (7 days)...")
    
    query = """
    SELECT 
        r.timestamp,
        GROUP_CONCAT(CASE WHEN p.parameter_id = 'HA_TEMP_DEXTER' THEN r.value END) as temp_dexter,
        GROUP_CONCAT(CASE WHEN p.parameter_id = '40004' THEN r.value END) as temp_out,
        GROUP_CONCAT(CASE WHEN p.parameter_id = '40008' THEN r.value END) as temp_supply,
        GROUP_CONCAT(CASE WHEN p.parameter_id = '41778' THEN r.value END) as compressor
    FROM parameter_readings r
    JOIN parameters p ON r.parameter_id = p.id
    WHERE r.timestamp > datetime('now', '-7 days')
    AND p.parameter_id IN ('HA_TEMP_DEXTER', '40004', '40008', '41778')
    GROUP BY r.timestamp
    ORDER BY r.timestamp ASC
    """
    
    df = pd.read_sql_query(query, conn)
    
    # Clean data
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    for col in ['temp_dexter', 'temp_out', 'temp_supply', 'compressor']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.set_index('timestamp').resample('15min').mean().interpolate()
    
    # Filter: Night & Stable
    df = df[(df.index.hour >= 0) & (df.index.hour <= 5)]
    df['comp_diff'] = df['compressor'].diff().abs()
    df = df[df['comp_diff'] < 20]
    
    if len(df) < 20:
        logger.warning("Governor: Not enough clean data.")
        return None, None

    # Calculate Rates
    df['temp_change_1h'] = df['temp_dexter'].diff(4)
    
    # Calculate Real Offset (vs Curve 4.0 which is new base)
    BASE_CURVE = 4.0
    df['theoretical_supply'] = 20 + (20 - df['temp_out']) * BASE_CURVE * 0.15
    df['real_offset'] = df['temp_supply'] - df['theoretical_supply']
    
    df = df.dropna()
    df['offset_bin'] = df['real_offset'].round()
    
    stats = df.groupby('offset_bin')['temp_change_1h'].agg(['mean', 'count'])
    stats = stats[stats['count'] > 4]
    
    # 1. FIND BIAS (Holding Offset)
    # The offset where temp change is closest to 0
    if stats.empty: return None, None
    
    holding_offset_row = stats.iloc[(stats['mean']).abs().argsort()[:1]]
    if holding_offset_row.empty: return None, None
    
    bias = holding_offset_row.index[0]
    
    # 2. FIND POWER (Kp)
    # Slope of change vs offset
    try:
        high = stats.loc[stats.index.max()]
        low = stats.loc[stats.index.min()]
        slope = (high['mean'] - low['mean']) / (high.name - low.name)
        # Ideal Kp = TargetCorrectionSpeed / Slope
        # We want to correct 1C error in 5h (0.2C/h)
        kp = 0.2 / slope if slope > 0.01 else 3.0
    except:
        kp = 3.0 # Fallback
        
    return bias, kp

def run_governor():
    conn = get_db_connection()
    
    try:
        new_bias, new_kp = analyze_system_dynamics(conn)
        
        if new_bias is not None:
            # Load current settings
            curr_bias_row = conn.execute("SELECT value FROM system_tuning WHERE parameter_id='control_bias'").fetchone()
            curr_kp_row = conn.execute("SELECT value FROM system_tuning WHERE parameter_id='control_kp'").fetchone()
            
            curr_bias = curr_bias_row[0] if curr_bias_row else 0.0
            curr_kp = curr_kp_row[0] if curr_kp_row else 3.0
            
            # Apply Inertia (20% update rate)
            alpha = 0.2
            final_bias = (curr_bias * (1-alpha)) + (new_bias * alpha)
            final_kp = (curr_kp * (1-alpha)) + (new_kp * alpha)
            
            # Clamp
            final_kp = max(1.0, min(6.0, final_kp))
            final_bias = max(-5.0, min(5.0, final_bias))
            
            logger.info(f"Governor Update:")
            logger.info(f"  Bias: {curr_bias:.2f} -> {new_bias:.2f} (Target) -> {final_bias:.2f} (Set)")
            logger.info(f"  Kp:   {curr_kp:.2f} -> {new_kp:.2f} (Target) -> {final_kp:.2f} (Set)")
            
            conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description, last_updated) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", 
                         ('control_bias', final_bias, 'Governor Calibrated Bias'))
            conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description, last_updated) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", 
                         ('control_kp', final_kp, 'Governor Calibrated Kp'))
            conn.commit()
            logger.success("✓ Governor updated tuning parameters.")
            
    except Exception as e:
        logger.error(f"Governor failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_governor()
