import sys
import os
from datetime import datetime
import numpy as np

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/src")

from services.weather_service import SMHIWeatherService
from services.price_service import PriceService
from core.config import settings

# Base Physics
BASE_CURVE = 7.0
COMPRESSOR_POWER = 1.5 

def calculate_cop(outdoor, supply):
    delta = supply - outdoor
    # Linear approx for F730 inverter
    return max(1.0, 5.5 - (0.08 * delta))

def run_simulation(shunt_limit, weather, prices):
    t_down = 21.0
    t_dex = 20.0
    total_cost = 0.0
    
    # Physics 2023 Standard
    leak_down = 0.0085
    leak_dex = 0.0118
    rad_eff = 0.0135
    slab_eff = 0.015
    trans_coeff = 0.005
    
    for i in range(24):
        w = weather[i]
        p = prices[i].price_per_kwh
        out = w.temperature
        
        # Strategy: SmartPlanner V6 Logic (Simplified)
        # 1. Secure Slab
        action = "REST"
        offset = 0.0
        
        # If Down < 20.5, we MUST run.
        # But wait, with higher shunt, we might run LESS.
        # Let's assume a reactive controller for fair comparison.
        if t_down < 20.5:
            action = "RUN"
            offset = 1.0 # Standard charge
        
        # 2. Secure Dexter
        if t_dex < 19.5:
            action = "RUN"
            offset = 4.0 # Boost
            
        # Physics Step
        base_supply = 20 + ((20 - out) * BASE_CURVE * 0.15)
        pred_supply = base_supply + offset
        
        supply_down = min(pred_supply, shunt_limit)
        
        if action == "RUN":
            cop = calculate_cop(out, pred_supply)
            cost = COMPRESSOR_POWER * p
            total_cost += cost
            
            gain_down = max(0, (supply_down - t_down) * slab_eff)
            gain_dex = max(0, (pred_supply - t_dex) * rad_eff)
            
            t_down += gain_down
            t_dex += gain_dex
            
        # Losses
        loss_d = (t_down - out) * leak_down
        loss_x = (t_dex - out) * leak_dex
        trans = (t_down - t_dex) * trans_coeff
        
        t_down += -loss_d - trans
        t_dex += -loss_x + trans
        
    return total_cost, t_down, t_dex

if __name__ == "__main__":
    ws = SMHIWeatherService()
    ps = PriceService()
    forecast = ws.get_forecast(24)
    prices = ps.get_prices_today() + ps.get_prices_tomorrow()
    prices = prices[:24]
    
    if not forecast: exit()

    print("\n=== SHUNT OPTIMIZATION (24h Simulation) ===")
    print(f"Outdoor Temp: {forecast[0].temperature}°C")
    print("-" * 45)
    print(f"{ 'Shunt Limit':<12} | {'Cost (SEK)':<10} | {'End Temp Down':<15}")
    print("-" * 45)
    
    best_cost = 999.0
    best_shunt = 0
    
    for shunt in range(25, 41):
        cost, end_down, end_dex = run_simulation(float(shunt), forecast, prices)
        print(f"{shunt:.1f}°C       | {cost:.2f}       | {end_down:.2f}°C")
        
        if cost < best_cost and end_down > 20.5 and end_dex > 19.5:
            best_cost = cost
            best_shunt = shunt
            
    print("-" * 45)
    if best_shunt > 0:
        print(f"OPTIMAL SETTING: {best_shunt}°C")
        print(f"Potential Savings: {(44.94 - best_cost):.2f} SEK/day vs Baseline")
    else:
        print("No setting satisfied comfort requirements.")
