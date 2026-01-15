import sys
import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/src")

def evaluate():
    print("\n════════════════════════════════════════════════════════════════")
    print("  Nibe Autotuner - Historical Performance Evaluation (24h)")
    print("════════════════════════════════════════════════════════════════")
    
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    
    # 1. Fetch Data (Last 24h)
    start_time = datetime.utcnow() - timedelta(hours=24)
    
    # Dexter Temp
    df_dex = pd.read_sql_query("""
        SELECT timestamp, value as temp_dexter 
        FROM parameter_readings 
        WHERE parameter_id = (SELECT id FROM parameters WHERE parameter_id = 'HA_TEMP_DEXTER')
        AND timestamp > ?
    """, conn, params=(start_time,))
    
    # Downstairs Temp
    df_down = pd.read_sql_query("""
        SELECT timestamp, value as temp_down
        FROM parameter_readings 
        WHERE parameter_id = (SELECT id FROM parameters WHERE parameter_id = 'HA_TEMP_DOWNSTAIRS')
        AND timestamp > ?
    """, conn, params=(start_time,))
    
    # Compressor (Run Status) - BT2 Supply Temp is a good proxy for effort
    df_run = pd.read_sql_query("""
        SELECT timestamp, value as supply_temp
        FROM parameter_readings 
        WHERE parameter_id = (SELECT id FROM parameters WHERE parameter_id = '40008')
        AND timestamp > ?
    """, conn, params=(start_time,))
    
    # 2. Analyze Comfort (Dexter)
    if not df_dex.empty:
        min_dex = df_dex['temp_dexter'].min()
        avg_dex = df_dex['temp_dexter'].mean()
        bad_hours = len(df_dex[df_dex['temp_dexter'] < 19.5]) / 12 # Approx hours (assuming 5min logs)
        
        print(f"\n[COMFORT - DEXTER]")
        print(f"  Min Temp: {min_dex:.2f}°C")
        print(f"  Avg Temp: {avg_dex:.2f}°C")
        print(f"  Time < 19.5°C: {bad_hours:.1f} hours")
        if min_dex < 19.5:
            print("  ⚠️ Comfort breach detected!")
        else:
            print("  ✅ Comfort targets met.")
            
    # 3. Analyze Running
    if not df_run.empty:
        # Assume RUN if supply > 28 (approx)
        runs = df_run[df_run['supply_temp'] > 28.0]
        run_hours = len(runs) / 12
        
        print(f"\n[OPERATION]")
        print(f"  Run Time: {run_hours:.1f} hours (approx)")
        print(f"  Max Supply: {df_run['supply_temp'].max():.1f}°C")
        
    conn.close()

if __name__ == "__main__":
    evaluate()
