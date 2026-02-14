import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --- PHYSICS PARAMETERS ---
K_LEAK = 0.002  # Reduced from 0.003
K_GAIN = 0.15   # Increased from 0.12

def test_prediction():
    conn = sqlite3.connect('data/nibe_autotuner.db')
    
    # 1. Fetch Data
    query = """
    SELECT 
        strftime('%Y-%m-%d %H:00', r.timestamp) as hour,
        AVG(CASE WHEN p.parameter_id = 'HA_TEMP_DEXTER' THEN r.value END) as actual_temp,
        AVG(CASE WHEN p.parameter_id = '40004' THEN r.value END) as outdoor_temp,
        AVG(s.planned_offset) as offset
    FROM parameter_readings r
    JOIN parameters p ON r.parameter_id = p.id
    LEFT JOIN planned_heating_schedule s ON strftime('%Y-%m-%d %H:00', s.timestamp) = strftime('%Y-%m-%d %H:00', r.timestamp)
    WHERE r.timestamp > datetime('now', '-2 days')
    AND p.parameter_id IN ('HA_TEMP_DEXTER', '40004')
    GROUP BY hour
    ORDER BY hour ASC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    df = df.dropna(subset=['actual_temp', 'outdoor_temp'])
    df['offset'] = df['offset'].fillna(0)
    
    print("TIME             | ACTUAL | PRED   | ERR")
    print("-" * 40)
    
    if df.empty:
        print("No data found.")
        return

    current_pred = df['actual_temp'].iloc[0]
    
    for _, row in df.iterrows():
        err = row['actual_temp'] - current_pred
        
        print(f"{row['hour']} | {row['actual_temp']:.2f}   | {current_pred:.2f}   | {err:+.2f}")
        
        # Calculate next hour
        delta_t = current_pred - row['outdoor_temp']
        loss = K_LEAK * delta_t
        gain = K_GAIN * row['offset']
        
        current_pred = current_pred - loss + gain

if __name__ == "__main__":
    test_prediction()