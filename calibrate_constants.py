import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- CONFIG ---
DB_PATH = 'data/nibe_autotuner.db'
BASE_CURVE = 5.0  # We assume Curve 5.0 is base
TARGET_INDOOR = 21.0

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def analyze():
    print("🔍 STARTING DEEP DATA ANALYSIS (7 DAYS)...")
    conn = get_db_connection()
    
    # 1. Fetch Raw Data (High Resolution)
    # We join readings to get everything in one go.
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
    
    print("   -> Fetching data from DB...")
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Clean up formatting (SQLite GROUP_CONCAT returns strings)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    for col in ['temp_dexter', 'temp_out', 'temp_supply', 'compressor']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Resample to 15-min intervals to align timestamps and fill gaps
    df = df.set_index('timestamp').resample('15min').mean().interpolate()
    
    # 2. FILTERING ("The Wash")
    print(f"   -> Raw data points: {len(df)}")
    
    # Filter 1: Night Time Only (00:00 - 05:00) to avoid Sun/Internal gains
    df = df[(df.index.hour >= 0) & (df.index.hour <= 5)]
    
    # Filter 2: Compressor Active (Heating Mode) OR Steady Off
    # Remove transitions where compressor jumps wildly
    df['comp_diff'] = df['compressor'].diff().abs()
    df = df[df['comp_diff'] < 20] # Only stable operation
    
    print(f"   -> Washed data points (Night & Stable): {len(df)}")
    
    if len(df) < 10:
        print("❌ Not enough clean data found.")
        return

    # 3. PHYSICS CALCULATIONS
    
    # Calculate Rate of Change (degC per hour)
    # We take the difference over 1 hour (4 steps of 15 min)
    df['temp_change_1h'] = df['temp_dexter'].diff(4) 
    
    # Calculate "Effective Offset"
    # Logic: Based on outdoor temp and Curve 5, what SHOULD supply be?
    # Difference is the "Real Offset" the pump is producing (regardless of what we asked for).
    # Nibe approx formula: Supply = 20 + (20 - Out) * Curve * 0.15 (approx slope)
    df['theoretical_supply'] = 20 + (20 - df['temp_out']) * BASE_CURVE * 0.15
    df['real_offset'] = df['temp_supply'] - df['theoretical_supply']
    
    # Drop NaNs created by diff/shifting
    df = df.dropna()

    # 4. STATISTICAL ANALYSIS
    
    # Bin by Offset to see effect
    # We round Real Offset to nearest integer
    df['offset_bin'] = df['real_offset'].round()
    
    stats = df.groupby('offset_bin')['temp_change_1h'].agg(['mean', 'count', 'std'])
    
    # Filter bins with too little data
    stats = stats[stats['count'] > 4]
    
    print("\n📊 ANALYSIS RESULTS (Effect of Offset on Indoor Temp Change):")
    print("   (Based on Curve 5.0 Baseline)")
    print(f"{ 'OFFSET':<8} | { 'CHANGE (C/h)':<15} | { 'STABILITY (Std)':<15} | { 'HOURS OBSERVED'}")
    print("-" * 65)
    
    for offset, row in stats.iterrows():
        mean_change = row['mean']
        trend = "Steady"
        if mean_change > 0.05: trend = "Rising ↗"
        if mean_change < -0.05: trend = "Falling ↘"
        
        print(f"{offset:<8.0f} | {mean_change:+.3f} ({trend}) | {row['std']:.3f}           | {row['count']/4:.1f} h")

    # 5. RECOMMENDATION ENGINE
    print("\n💡 OPTIMIZATION INSIGHTS:")
    
    # Find the "Holding Offset" (Where change is closest to 0)
    holding_offset_row = stats.iloc[(stats['mean']).abs().argsort()[:1]]
    if not holding_offset_row.empty:
        hold_val = holding_offset_row.index[0]
        print(f"   -> HOLDING OFFSET: approx {hold_val:+.0f}")
        print(f"      To keep temp steady, the system effectively needs Offset {hold_val:+.0f}.")
        if hold_val > 2:
            print("      ⚠️ Curve 5.0 is too low. Consider raising to 6.0.")
        elif hold_val < -2:
            print("      ⚠️ Curve 5.0 is too high. Consider lowering to 4.0.")
        else:
            print("      ✅ Curve 5.0 is well balanced.")
    
    # Find "Power" (Difference between low and high offset effect)
    try:
        high_off = stats.loc[stats.index.max()]
        low_off = stats.loc[stats.index.min()]
        
        diff_offset = high_off.name - low_off.name
        diff_effect = high_off['mean'] - low_off['mean']
        
        if diff_offset > 0:
            power_per_step = diff_effect / diff_offset
            print(f"   -> SYSTEM POWER: {power_per_step:.3f} C/h per Offset step.")
            
            # Calibration of K_P
            # We want K_P * Power = Response Speed.
            # If we want to correct a 1.0C error in, say, 5 hours (0.2C/h)...
            # We need 0.2 / Power = Required Offset.
            # So K_P should be around (Required Offset / 1.0).
            
            ideal_kp = 0.15 / power_per_step # Target 0.15C/h correction speed for 1C error
            print(f"   -> RECOMMENDED K_P: {ideal_kp:.1f} (Current: 4.0)")
            
    except:
        print("   -> Could not calculate System Power (not enough spread in data).")

if __name__ == "__main__":
    analyze()
