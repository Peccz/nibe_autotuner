import sys
import os
import sqlite3
import pandas as pd
from loguru import logger

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def calibrate_and_backfill():
    logger.info("Starting Sensor Calibration & History Backfill...")
    
    db_path = 'data/nibe_autotuner.db'
    conn = sqlite3.connect(db_path)
    
    # 1. Fetch IDs
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM parameters WHERE parameter_id = 'HA_TEMP_DOWNSTAIRS'")
        res = cur.fetchone()
        if not res:
            logger.error("HA_TEMP_DOWNSTAIRS parameter not found.")
            return
        ha_id = res[0]
        
        cur.execute("SELECT id FROM parameters WHERE parameter_id = '40033'") # BT50 Room Temp
        res = cur.fetchone()
        if not res:
            logger.error("BT50 (40033) parameter not found.")
            return
        bt50_id = res[0]
        
        # 2. Load Overlapping Data (Last 48h)
        logger.info("Analyzing sensor correlation (Last 48h)...")
        # Match on Minute precision
        query = f"""
        SELECT 
            t1.timestamp, 
            t1.value as ha_val, 
            t2.value as bt50_val
        FROM parameter_readings t1
        JOIN parameter_readings t2 ON strftime('%Y-%m-%d %H:%M', t1.timestamp) = strftime('%Y-%m-%d %H:%M', t2.timestamp)
        WHERE t1.parameter_id = {ha_id} 
        AND t2.parameter_id = {bt50_id}
        ORDER BY t1.timestamp DESC
        LIMIT 1000
        """
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            logger.warning("No overlapping data found (even with minute matching).")
            return

        # 3. Calculate Offset
        df['diff'] = df['ha_val'] - df['bt50_val']
        offset = df['diff'].mean()
        correlation = df['ha_val'].corr(df['bt50_val'])
        
        logger.info(f"Analysis Results:")
        logger.info(f"  Data Points: {len(df)}")
        logger.info(f"  Correlation: {correlation:.4f}")
        logger.info(f"  Mean Offset: {offset:.4f} C (IKEA is {'warmer' if offset > 0 else 'colder'} than BT50)")
        
        # Save offset to tuning
        conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", 
                     ('sensor_offset_bt50', offset, 'Calibrated offset: HA - BT50'))
        
        # 4. Backfill History
        # Find all BT50 readings where NO HA reading exists (approximate match)
        logger.info("Identifying historical gaps...")
        
        missing_query = f"""
        SELECT t2.timestamp, t2.value, t2.device_id
        FROM parameter_readings t2
        LEFT JOIN parameter_readings t1 
            ON strftime('%Y-%m-%d %H:%M', t1.timestamp) = strftime('%Y-%m-%d %H:%M', t2.timestamp) 
            AND t1.parameter_id = {ha_id}
        WHERE t2.parameter_id = {bt50_id}
        AND t1.id IS NULL
        """
        
        missing_df = pd.read_sql_query(missing_query, conn)
        logger.info(f"Found {len(missing_df)} historical points to backfill.")
        
        if len(missing_df) > 0:
            # Prepare insert data
            to_insert = []
            for _, row in missing_df.iterrows():
                calibrated_val = row['value'] + offset
                # Using the same device_id as the source reading
                to_insert.append((row['device_id'], ha_id, row['timestamp'], calibrated_val))
            
            # Batch insert
            logger.info("Applying calibrated backfill...")
            conn.executemany(
                "INSERT INTO parameter_readings (device_id, parameter_id, timestamp, value) VALUES (?, ?, ?, ?)",
                to_insert
            )
            conn.commit()
            logger.info(f"✓ Successfully backfilled {len(to_insert)} readings.")
        else:
            logger.info("History is already complete.")

    except Exception as e:
        logger.error(f"Calibration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    calibrate_and_backfill()

