import sys
import os
from datetime import datetime, timedelta
from typing import List
import numpy as np

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/src")

from services.weather_service import SMHIWeatherService
from services.price_service import PriceService
from core.config import settings

# Mock Constants
SHUN_LIMIT = 29.0
BASE_CURVE = 7.0
COP_BASE = 4.8
COP_DROP_PER_DELTA = 0.06 # COP drops by 0.06 per degree lift
COMPRESSOR_POWER = 1.5 # kW input approx

def calculate_cop(outdoor, supply):
    delta = supply - outdoor
    # Simple linear approximation for F730
    # At 0/35 -> Delta 35 -> COP ~4.5 ? No F730 is inverter.
    # Let's say: COP = 5.5 - (0.08 * Delta)
    # 0/35 -> 5.5 - 2.8 = 2.7
    # 0/50 -> 5.5 - 4.0 = 1.5
    cop = max(1.0, 5.5 - (0.08 * delta))
    return cop

def run_scenario(strategy_name, weather, prices, start_temp_down, start_temp_dex):
    print(f"\n--- Simulating Strategy: {strategy_name} ---")
    
    t_down = start_temp_down
    t_dex = start_temp_dex
    
    total_kwh_in = 0.0
    total_cost = 0.0
    min_dex = 99.0
    
    # Physics (Simplified from SmartPlanner)
    leak_down = 0.0085
    leak_dex = 0.0118
    rad_eff = 0.0135
    slab_eff = 0.015
    trans_coeff = 0.005
    
    for i in range(24):
        w = weather[i]
        p = prices[i].price_per_kwh
        out = w.temperature
        
        # Decide Action based on Strategy
        action = "REST"
        offset = 0.0
        
        if strategy_name == "Spetsvärme (Offset +4)":
            # Reactive: Run if Dexter < 19.8
            if t_dex < 19.8:
                action = "RUN"
                offset = 4.0
        
        elif strategy_name == "Basvärme (Offset +1)":
            # Proactive: Run longer/often to keep mass warm
            # Run if Dexter < 20.0 (Higher threshold to compensate slowness)
            if t_dex < 20.0:
                action = "RUN"
                offset = 1.0
        
        # Calculate Supply
        base_supply = 20 + ((20 - out) * BASE_CURVE * 0.15)
        pred_supply = base_supply + 22 + offset # Using the bad formula just for stress testing? NO use corrected.
        # Correct formula:
        pred_supply = 20 + ((20 - out) * BASE_CURVE * 0.15) + offset
        
        supply_down = min(pred_supply, SHUN_LIMIT)
        
        # Energy Consumption
        kwh_consumed = 0.0
        if action == "RUN":
            # Assume compressor runs at nominal power
            cop = calculate_cop(out, pred_supply)
            kwh_consumed = COMPRESSOR_POWER
            
            # Heat Output
            heat_output = kwh_consumed * cop
            
            # Distribution (approx)
            # Higher supply = more output
            # Just use gain factors directly
            gain_down = max(0, (supply_down - t_down) * slab_eff)
            gain_dex = max(0, (pred_supply - t_dex) * rad_eff)
            
            # Update temps
            t_down += gain_down
            t_dex += gain_dex
            
            total_kwh_in += kwh_consumed
            total_cost += kwh_consumed * p
        
        # Losses
        loss_d = (t_down - out) * leak_down
        loss_x = (t_dex - out) * leak_dex
        trans = (t_down - t_dex) * trans_coeff
        
        t_down += -loss_d - trans
        t_dex += -loss_x + trans
        
        min_dex = min(min_dex, t_dex)
        
    print(f"Result:")
    print(f"  Min Dexter Temp: {min_dex:.2f}°C")
    print(f"  Total Energy:    {total_kwh_in:.2f} kWh")
    print(f"  Total Cost:      {total_cost:.2f} SEK")
    
    return total_cost, min_dex

if __name__ == "__main__":
    # Setup Data
    ws = SMHIWeatherService()
    ps = PriceService()
    
    forecast = ws.get_forecast(24)
    prices = ps.get_prices_today() + ps.get_prices_tomorrow()
    prices = prices[:24] # First 24h
    
    if not forecast or not prices:
        print("Error fetching data")
        exit()
        
    # Start conditions
    start_down = 21.0
    start_dex = 20.0
    
    c1, m1 = run_scenario("Spetsvärme (Offset +4)", forecast, prices, start_down, start_dex)
    c2, m2 = run_scenario("Basvärme (Offset +1)", forecast, prices, start_down, start_dex)
    
    print("\n=== FINAL VERDICT ===")
    if m1 < 19.5 and m2 >= 19.5:
        print("Basvärme wins (Spets failed comfort)")
    elif m2 < 19.5 and m1 >= 19.5:
        print("Spetsvärme wins (Bas failed comfort)")
    elif c1 < c2:
        print(f"Spetsvärme is cheaper by {c2-c1:.2f} SEK")
    else:
        print(f"Basvärme is cheaper by {c1-c2:.2f} SEK")
