"""
Scientist Module: Advanced AI Calibration V4.0
Calibrates wind direction factors, thermal lag, and internal heat gain.
"""
import sys
import os
import json
import requests
from datetime import datetime, timedelta, timezone
from loguru import logger
import sqlite3
import pandas as pd
import google.generativeai as genai

sys.path.append('src')
from core.config import settings

def calibrate_price_model(conn):
    """
    Learn the correlation between Weather (Wind) and Electricity Price.
    Generates 'price_wind_sensitivity' and 'price_base_curve'.
    """
    logger.info("  -> Calibrating Price Prediction Model...")
    
    # 1. Fetch last 7 days of prices (SE3)
    history_days = 7
    prices = []
    
    try:
        today = datetime.now()
        for i in range(history_days):
            d = today - timedelta(days=i)
            d_str = d.strftime('%Y/%m-%d')
            url = f"https://www.elprisetjustnu.se/api/v1/prices/{d_str}_SE3.json"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                for p in data:
                    prices.append({
                        'time': p['time_start'],
                        'price': p['SEK_per_kWh']
                    })
    except Exception as e:
        logger.warning(f"Failed to fetch price history: {e}")
        return

    if not prices: return

    # 2. Fetch/Estimate Weather history
    # Ideally we query DB, but for now we assume a general wind pattern or fetch history if possible.
    # To keep it simple for V1: We send the price curve to AI and ask it to extract the
    # "Wind Sensitivity" assuming standard correlation, or just the Daily Profile.
    
    # We will aggregate prices by hour to get the "Base Profile"
    df = pd.DataFrame(prices)
    df['time'] = pd.to_datetime(df['time'])
    df['hour'] = df['time'].dt.hour
    
    hourly_avg = df.groupby('hour')['price'].mean().tolist()
    avg_price_week = df['price'].mean()
    
    # Normalized curve (1.0 = average)
    base_curve = [p / avg_price_week for p in hourly_avg]
    
    # 3. Ask AI to refine
    prompt = f"""
    Analyze this electricity price data (SE3, Sweden) for the last {history_days} days.
    Hourly Average Curve (Normalized): {json.dumps(base_curve)}
    Average Price: {avg_price_week} SEK/kWh.
    
    Task:
    1. 'price_wind_sensitivity': Estimate a coefficient (factor). How much does high wind typically lower the price in this region? (Standard assumption: 0.02 to 0.10).
    2. 'weekend_discount_factor': How much lower are prices on Sat/Sun/Holidays vs Weekdays? (e.g. 0.85 means 15% cheaper).
    3. 'price_temp_sensitivity': Estimate price increase per degree C drop below zero (SEK/kWh/°C). (Standard: 0.05 - 0.20).
    
    Respond ONLY with JSON: {{ "price_wind_sensitivity": float, "weekend_discount_factor": float, "price_temp_sensitivity": float }}
    """
    
    model = genai.GenerativeModel('gemini-2.5-flash') # Use Flash for speed
    try:
        response = model.generate_content(prompt)
        res_json = json.loads(response.text.strip('`json \n'))
        
        # Save Sensitivity
        val = res_json.get('price_wind_sensitivity', 0.05)
        conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", 
                     ('price_wind_sensitivity', val, 'Price reduction factor per m/s wind'))
        
        # Save Weekend Discount
        weekend_factor = res_json.get('weekend_discount_factor', 0.90)
        conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", 
                     ('weekend_discount_factor', weekend_factor, 'Price multiplier for weekends/holidays'))

        # Save Temp Sensitivity
        temp_sens = res_json.get('price_temp_sensitivity', 0.10)
        conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", 
                     ('price_temp_sensitivity', temp_sens, 'Price increase per degree colder'))
        
        logger.info(f"  ✓ Calibrated Price Model: WindSens={val}, Weekend={weekend_factor}, TempSens={temp_sens}")
        conn.commit()
        
    except Exception as e:
        logger.error(f"AI Price Calibration failed: {e}")

def run_daily_calibration():
    logger.info("Starting Multi-Zone AI Calibration (Scientist 4.0)...")
    
    if not settings.GOOGLE_API_KEY: return

    # Resolve DB path from settings
    db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    if not os.path.isabs(db_path):
        # Handle relative paths (e.g., ./data/...)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_path.startswith('./'):
            db_path = os.path.join(project_root, db_path[2:])
        else:
            db_path = os.path.join(project_root, db_path)

    conn = sqlite3.connect(db_path)
    
    # 1. Run Physics Calibration
    try:
        calibrate_physics(conn)
    except Exception as e:
        logger.error(f"Physics calibration error: {e}")

    # 2. Run Price Model Calibration
    try:
        calibrate_price_model(conn)
    except Exception as e:
        logger.error(f"Price calibration error: {e}")

    conn.close()

def calibrate_physics(conn):
    start_time = datetime.utcnow() - timedelta(hours=24)
    
    # Load all relevant data
    query = """
    SELECT r.timestamp, p.parameter_id, r.value 
    FROM parameter_readings r 
    JOIN parameters p ON r.parameter_id = p.id 
    WHERE r.timestamp >= ? 
    AND p.parameter_id IN ('HA_TEMP_DOWNSTAIRS', 'HA_TEMP_DEXTER', '40004', '41778', 'EXT_WIND_SPEED', 'EXT_WIND_DIRECTION')
    """
    df = pd.read_sql_query(query, conn, params=(start_time,))
    
    if df.empty:
        logger.warning("No data for physics calibration.")
        return

    tuning_res = conn.execute("SELECT parameter_id, value FROM system_tuning").fetchall()
    current_tuning = {row[0]: row[1] for row in tuning_res}
    
    summary = df.groupby('parameter_id')['value'].agg(['mean', 'min', 'max']).to_dict()
    
    prompt = f"""
    You are a building physics expert. Calibrate this house model based on observed data.
    
    Current Tuning: {json.dumps(current_tuning)}
    Yesterday's Summary: {json.dumps(summary)}
    
    HIERARCHICAL CALIBRATION STRATEGY:
    1. BASELINE (Leakage): Look at periods when pump was OFF/LOW. Calibrate 'thermal_leakage' (C/h per DeltaT). Note: Wind impact is now SQUARE law (WindSpeed^2).
    2. EFFICIENCY (Heating): Look at periods when pump was RUNNING. Calibrate 'rad_efficiency' & 'slab_efficiency'. 
       Note: We now use a POWER LAW: Gain = coeff * (Supply - Indoor)^1.3 for rads, and ^1.1 for slab.
    3. DISTURBANCES: Fine-tune 'wind_sensitivity' (coeff for Wind^2) and 'solar_gain'.
    
    CONSTRAINTS:
    - Do NOT change values by more than 20% in a single run (stability).
    - rad_efficiency (new scale) should be around 0.002 - 0.010.
    - slab_efficiency (new scale) should be around 0.001 - 0.005.
    - wind_sensitivity (new scale) should be around 0.0001 - 0.001.
    
    Goal: Update these factors:
    - 'thermal_leakage' & 'thermal_leakage_dexter'
    - 'rad_efficiency' & 'slab_efficiency'
    - 'wind_sensitivity' & 'wind_sensitivity_dexter'
    - 'wind_direction_west_factor'
    - 'solar_gain_coeff' & 'solar_gain_dexter'
    - 'inter_zone_transfer'
    
    Respond ONLY with JSON.
    """

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    response = model.generate_content(prompt)
    new_values = json.loads(response.text.strip('`json \n'))
    
    # List of allowed params to update/create
    allowed_params = [
        'thermal_leakage', 'thermal_leakage_dexter', 'rad_efficiency', 'slab_efficiency',
        'wind_sensitivity', 'wind_sensitivity_dexter', 'wind_direction_west_factor',
        'solar_gain_coeff', 'solar_gain_dexter', 'internal_heat_gain', 'internal_gain_dexter',
        'thermal_inertia_lag', 'inter_zone_transfer'
    ]

    for pid, val in new_values.items():
        if pid in current_tuning or pid in allowed_params: 
            conn.execute("INSERT OR REPLACE INTO system_tuning (parameter_id, value, description) VALUES (?, ?, ?)", 
                         (pid, float(val), 'AI Calibrated'))
            logger.info(f"  ✓ Calibrated {pid} -> {val}")
    conn.commit()

if __name__ == "__main__":
    run_daily_calibration()