import sqlite3
import pandas as pd
import numpy as np

DB_PATH = 'data/nibe_autotuner.db'

def analyze_zone_balance():
    conn = sqlite3.connect(DB_PATH)
    
    query = """
    SELECT 
        r.timestamp,
        GROUP_CONCAT(CASE WHEN p.parameter_id = 'HA_TEMP_DEXTER' THEN r.value END) as temp_dexter,
        GROUP_CONCAT(CASE WHEN p.parameter_id = 'HA_TEMP_DOWNSTAIRS' THEN r.value END) as temp_down,
        GROUP_CONCAT(CASE WHEN p.parameter_id = '40008' THEN r.value END) as temp_supply
    FROM parameter_readings r
    JOIN parameters p ON r.parameter_id = p.id
    WHERE r.timestamp > datetime('now', '-7 days')
    AND p.parameter_id IN ('HA_TEMP_DEXTER', 'HA_TEMP_DOWNSTAIRS', '40008')
    GROUP BY r.timestamp
    ORDER BY r.timestamp ASC
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Clean data
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    for col in ['temp_dexter', 'temp_down', 'temp_supply']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Resample
    df = df.set_index('timestamp').resample('30min').mean().interpolate().dropna()
    
    # Calculate Diff (Down - Dexter) -> Positive means Down is warmer
    df['zone_diff'] = df['temp_down'] - df['temp_dexter']
    
    # Bin by Supply Temp
    # We create bins: <30, 30-35, 35-40, 40+
    bins = [0, 30, 35, 40, 45, 60]
    labels = ['<30', '30-35', '35-40', '40-45', '45+']
    df['supply_bin'] = pd.cut(df['temp_supply'], bins=bins, labels=labels)
    
    print("\n📊 ZONE BALANCE ANALYSIS (Supply Temp vs Zone Diff)")
    print("   (Diff = Downstairs - Dexter. Higher = Dexter is colder)")
    print("-" * 60)
    print(f"{ 'SUPPLY TEMP':<12} | { 'AVG DIFF (C)':<15} | { 'DEXTER (Avg)':<15} | {'SAMPLES'}")
    print("-" * 60)
    
    stats = df.groupby('supply_bin')['zone_diff'].agg(['mean', 'count'])
    dexter_stats = df.groupby('supply_bin')['temp_dexter'].mean()
    
    for bin_label in labels:
        if bin_label in stats.index:
            diff = stats.loc[bin_label, 'mean']
            count = stats.loc[bin_label, 'count']
            dex = dexter_stats.loc[bin_label]
            print(f"{bin_label:<12} | {diff:+.2f} C         | {dex:.1f} C           | {count}")

if __name__ == "__main__":
    analyze_zone_balance()
