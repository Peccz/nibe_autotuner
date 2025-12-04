"""
Hot Water Usage Pattern Analyzer
Detects usage patterns based on rapid temperature drops in the water heater.
"""
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from loguru import logger
from typing import Dict, Tuple

class HotWaterPatternAnalyzer:
    def __init__(self, db_path='data/nibe_autotuner.db'):
        self.db_path = db_path
        # Parameter 40013 is "Hot Water Top" (BT7) - best indicator of usage
        self.param_id_top = '40013' 
        self.usage_map = {} # (weekday, hour) -> probability

    def train_on_history(self, days_back=30):
        """
        Analyze historical data to learn usage patterns.
        Looks for drops > 2°C in short timeframes.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get parameter internal ID
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM parameters WHERE parameter_id = ?", (self.param_id_top,))
            res = cursor.fetchone()
            if not res:
                logger.warning(f"Parameter {self.param_id_top} not found in DB")
                return
            
            p_id = res[0]
            start_date = datetime.now() - timedelta(days=days_back)
            
            query = """
            SELECT timestamp, value 
            FROM parameter_readings 
            WHERE parameter_id = ? AND timestamp > ?
            ORDER BY timestamp ASC
            """
            
            df = pd.read_sql_query(query, conn, params=(p_id, start_date))
            conn.close()
            
            if df.empty:
                logger.warning("No hot water data found")
                return

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['value'] = pd.to_numeric(df['value'])
            
            # Calculate rate of change (diff per ~5 min step)
            df['diff'] = df['value'].diff()
            
            # Define "Usage Event": Temp drops more than 1.5 degrees in one reading (5 min)
            # Or cumulative drop could be better, but let's start simple.
            # A shower usually drops temp by 5-10 degrees over 10-15 mins.
            # So a drop of < -0.5 per 5 min step is significant if sustained.
            # Let's look for rapid drops < -1.0.
            usage_events = df[df['diff'] < -1.0].copy()
            
            usage_events['hour'] = usage_events['timestamp'].dt.hour
            usage_events['weekday'] = usage_events['timestamp'].dt.weekday # 0=Mon, 6=Sun
            
            # Build probability map
            # Count events per (weekday, hour)
            counts = usage_events.groupby(['weekday', 'hour']).size()
            
            # Normalize (approximate probability)
            # Max usage seen in a slot becomes "100% likely" relative to this household's habits
            max_events = counts.max() if not counts.empty else 1
            
            self.usage_map = {}
            for (wd, hr), count in counts.items():
                prob = min(1.0, count / max(1, (days_back / 7))) # Events per specific weekday over period
                # Or simpler: relative score
                score = count / max_events
                self.usage_map[(wd, hr)] = round(score, 2)
                
            logger.info(f"Analyzed {len(df)} readings. Found {len(usage_events)} usage events.")
            
        except Exception as e:
            logger.error(f"Error analyzing HW patterns: {e}")

    def get_usage_probability(self, timestamp: datetime) -> float:
        """Get probability (0.0-1.0) of hot water usage for a specific time"""
        if not self.usage_map:
            self.train_on_history()
            
        wd = timestamp.weekday()
        hr = timestamp.hour
        
        # Check current hour and next hour (pre-heating)
        prob_now = self.usage_map.get((wd, hr), 0.0)
        
        next_t = timestamp + timedelta(hours=1)
        prob_next = self.usage_map.get((next_t.weekday(), next_t.hour), 0.0)
        
        return max(prob_now, prob_next)

    def get_status_string(self) -> str:
        prob = self.get_usage_probability(datetime.now())
        if prob > 0.6: return "HIGH"
        if prob > 0.3: return "MEDIUM"
        return "LOW"

if __name__ == "__main__":
    analyzer = HotWaterPatternAnalyzer()
    analyzer.train_on_history()
    print("Current Usage Probability:", analyzer.get_usage_probability(datetime.now()))
    
    # Print "High Risk" times
    print("\nHigh Usage Times detected:")
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    for (wd, hr), prob in analyzer.usage_map.items():
        if prob > 0.3:
            print(f"{days[wd]} {hr:02d}:00 - Score: {prob}")
