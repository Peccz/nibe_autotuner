import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# --- CONFIG ---
TARGET_TEMP = 21.0
K_P = 4.0        # Reaction to temperature error
K_ECO = 3.0      # Reaction to price deviation
CLAMP_MIN = -5.0 # Min allowed offset
CLAMP_MAX = 5.0  # Max allowed offset

def simulate():
    conn = sqlite3.connect('data/nibe_autotuner.db')
    
    # 1. Fetch Data (Last 24h)
    query = """
    SELECT strftime('%Y-%m-%d %H:00', r.timestamp) as hour, 
           AVG(CASE WHEN p.parameter_id='HA_TEMP_DEXTER' THEN r.value END) as dexter,
           AVG(CASE WHEN p.parameter_id='HA_TEMP_DOWNSTAIRS' THEN r.value END) as downstairs,
           AVG(CASE WHEN p.parameter_id='40004' THEN r.value END) as outdoor,
           MAX(s.electricity_price) as price
    FROM parameter_readings r 
    JOIN parameters p ON r.parameter_id = p.id 
    LEFT JOIN planned_heating_schedule s ON strftime('%Y-%m-%d %H:00', s.timestamp) = strftime('%Y-%m-%d %H:00', r.timestamp)
    WHERE r.timestamp > datetime('now', '-24 hours')
    GROUP BY hour
    ORDER BY hour
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Fill missing prices (forward fill)
    df['price'] = df['price'].fillna(method='ffill')
    df['price'] = df['price'].fillna(method='bfill') # If start is empty
    
    # Calculate Daily Average Price (Simple rolling avg proxy for now)
    avg_price = df['price'].mean()
    
    print(f"\n=== SIMULATION PARAMETERS ===")
    print(f"Target: {TARGET_TEMP}C | K_p: {K_P} | K_eco: {K_ECO}")
    print(f"Daily Avg Price: {avg_price:.2f} kr/kWh\n")
    
    print(f"{ 'TIME':<16} | { 'IN (C)':<6} | { 'PRICE':<6} | { 'ERR':<5} | { 'P-TERM':<6} | { 'E-TERM':<6} | { 'OFFSET':<6}")
    print("-" * 80)
    
    offsets = []
    
    for _, row in df.iterrows():
        # Input: Use lowest indoor temp to ensure comfort
        indoor = min(row['dexter'], row['downstairs']) if pd.notnull(row['dexter']) else row['downstairs']
        if pd.isnull(indoor): continue
        
        # 1. P-Term (Temperature Error)
        error = TARGET_TEMP - indoor
        p_term = error * K_P
        
        # 2. Eco-Term (Price Deviation)
        # Ratio: 0.5 (Cheap) -> (1 - 0.5) * K = 0.5*K
        # Ratio: 1.5 (Expensive) -> (1 - 1.5) * K = -0.5*K
        price_ratio = row['price'] / avg_price if avg_price > 0 else 1.0
        eco_term = (1.0 - price_ratio) * K_ECO
        
        # 3. Total Offset
        raw_offset = p_term + eco_term
        final_offset = max(CLAMP_MIN, min(CLAMP_MAX, round(raw_offset)))
        
        offsets.append(final_offset)
        
        print(f"{row['hour']:<16} | {indoor:6.2f} | {row['price']:6.2f} | {error:5.2f} | {p_term:6.2f} | {eco_term:6.2f} | {final_offset:6.0f}")

if __name__ == "__main__":
    simulate()
