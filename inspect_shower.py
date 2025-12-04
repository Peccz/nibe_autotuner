import sqlite3
import pandas as pd
from datetime import datetime

def inspect_shower_data():
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    
    # Parameter 40013 (Hot Water Top)
    param_id = '40013'
    
    # Get internal ID
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM parameters WHERE parameter_id = ?", (param_id,))
    pid = cursor.fetchone()[0]
    
    # Query specific window (Adjust date if needed, user said 2025-12-04)
    # Assuming today is roughly that date or user means "yesterday/today"
    # Let's look broadly at the last 24h to find the dip
    query = """
    SELECT timestamp, value 
    FROM parameter_readings 
    WHERE parameter_id = ? 
    ORDER BY timestamp DESC
    LIMIT 500
    """
    
    df = pd.read_sql_query(query, conn, params=(pid,))
    conn.close()
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    
    # Calculate drop
    df['diff'] = df['value'].diff()
    
    print(f"{ 'Time':<20} | {'Temp':<6} | {'Change':<6}")
    print("-" * 40)
    
    # Filter for the time window user mentioned (approx)
    # Or just show the biggest drops
    
    biggest_drops = df[df['diff'] < -0.1].sort_values('diff')
    
    print("\nBIGGEST DROPS FOUND:")
    for _, row in biggest_drops.head(10).iterrows():
        print(f"{row['timestamp']} | {row['value']:>5.1f} | {row['diff']:>5.1f}")

    print("\nALL DATA 17:00-21:00 (approx):")
    # Filter roughly
    subset = df[df['timestamp'].dt.hour.isin([17, 18, 19, 20, 21])]
    for _, row in subset.iterrows():
        # Mark drops
        mark = "<---" if row['diff'] < -0.2 else ""
        print(f"{row['timestamp'].strftime('%H:%M')} | {row['value']:>5.1f} | {row['diff']:>5.1f} {mark}")

if __name__ == "__main__":
    inspect_shower_data()
