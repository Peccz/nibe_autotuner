import sqlite3
import pandas as pd
import numpy as np

DB_PATH = 'data/nibe_autotuner.db'

def analyze_zone_balance_refined():
    conn = sqlite3.connect(DB_PATH)
    
    query = """
    SELECT 
        r.timestamp,
        GROUP_CONCAT(CASE WHEN p.parameter_id = 'HA_TEMP_DEXTER' THEN r.value END) as temp_dexter,
        GROUP_CONCAT(CASE WHEN p.parameter_id = 'HA_TEMP_DOWNSTAIRS' THEN r.value END) as temp_down,
        GROUP_CONCAT(CASE WHEN p.parameter_id = '40008' THEN r.value END) as temp_supply,
        GROUP_CONCAT(CASE WHEN p.parameter_id = '41778' THEN r.value END) as compressor
    FROM parameter_readings r
    JOIN parameters p ON r.parameter_id = p.id
    WHERE r.timestamp > datetime('now', '-7 days')
    AND p.parameter_id IN ('HA_TEMP_DEXTER', 'HA_TEMP_DOWNSTAIRS', '40008', '41778')
    GROUP BY r.timestamp
    ORDER BY r.timestamp ASC
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Clean data
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    for col in ['temp_dexter', 'temp_down', 'temp_supply', 'compressor']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Resample to 1h to smooth out spikes
    df = df.set_index('timestamp').resample('1H').mean().interpolate().dropna()
    
    # Filter 1: Active Heating Only (Comp > 20 Hz)
    df = df[df['compressor'] > 20]
    
    # Filter 2: No Hot Water (Supply < 48C)
    df = df[df['temp_supply'] < 48]
    
    # LAG COMPENSATION
    # Floor takes time. We correlate Supply(T-2h) with Diff(T).
    # Shift supply forward by 2 rows (2 hours).
    df['lagged_supply'] = df['temp_supply'].shift(2)
    df = df.dropna()
    
    # Calculate Diff (Down - Dexter)
    df['zone_diff'] = df['temp_down'] - df['temp_dexter']
    
    # Binning
    bins = [20, 30, 35, 40, 50]
    labels = ['<30', '30-35', '35-40', '40+']
    df['supply_bin'] = pd.cut(df['lagged_supply'], bins=bins, labels=labels)
    
    print("\n📊 REFINED ZONE ANALYSIS (Lagged Supply -2h, No VV)")
    print("-" * 65)
    print(f"{ 'SUPPLY (Lagged)':<16} | { 'AVG DIFF':<15} | { 'DEXTER':<15} | {'SAMPLES'}")
    print("-" * 65)
    
    stats = df.groupby('supply_bin')['zone_diff'].agg(['mean', 'count'])
    dexter_stats = df.groupby('supply_bin')['temp_dexter'].mean()
    
    for bin_label in labels:
        if bin_label in stats.index:
            diff = stats.loc[bin_label, 'mean']
            count = stats.loc[bin_label, 'count']
            dex = dexter_stats.loc[bin_label]
            print(f"{bin_label:<16} | {diff:+.2f} C         | {dex:.1f} C           | {count}")

if __name__ == "__main__":
    analyze_zone_balance_refined()
