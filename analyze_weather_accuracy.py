import sys
import sqlite3
from datetime import datetime, timedelta, timezone
from services.weather_service import SMHIWeatherService
from loguru import logger

# Setup minimal logging
logger.remove()
logger.add(sys.stderr, level="ERROR")

def check_diff():
    # 1. Get Pump Data
    conn = sqlite3.connect('data/nibe_autotuner.db')
    cursor = conn.cursor()
    
    # Get last 12h readings for param 1 (Outdoor)
    cursor.execute("""
        SELECT timestamp, value 
        FROM parameter_readings 
        WHERE parameter_id=1 
        AND timestamp > datetime('now', '-12 hours')
        ORDER BY timestamp ASC
    """)
    pump_readings = cursor.fetchall()
    conn.close()

    if not pump_readings:
        print("No pump readings found.")
        return

    # 2. Get SMHI Forecast
    try:
        ws = SMHIWeatherService()
        forecasts = ws.get_forecast()
    except Exception as e:
        print(f"Error fetching SMHI: {e}")
        return
    
    if forecasts:
        first_fc = forecasts[0]
        print(f"DEBUG: Next Forecast (SMHI): {first_fc.timestamp} -> {first_fc.temperature}°C")
    
    if pump_readings:
        last_pump = pump_readings[-1]
        print(f"DEBUG: Last Pump Read:       {last_pump[0]} -> {last_pump[1]}°C")

    # Estimate diff based on latest vs next
    if forecasts and pump_readings:
        diff = float(last_pump[1]) - float(first_fc.temperature)
        print(f"Approximate Diff (Pump - SMHI): {diff:+.2f}°C")

if __name__ == "__main__":
    check_diff()
