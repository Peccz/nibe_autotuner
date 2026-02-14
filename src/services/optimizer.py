"""
Deterministic Optimizer V12.0
Simulates future indoor temperature and optimizes heating schedule based on price and COP.
"""
import math
from datetime import datetime, timedelta
from typing import List, Tuple
from loguru import logger

# Physics Constants (Calibrated 2026-02-14)
K_LEAK = 0.002
K_GAIN = 0.15
TARGET_TEMP = 21.0
MIN_TEMP = 20.0 # Never allow below this

def predict_temperatures(
    start_temp: float,
    outdoor_temps: List[float],
    offsets: List[float]
) -> List[float]:
    """
    Simulates indoor temperature for 24 hours given a schedule.
    """
    temps = []
    current_temp = start_temp
    
    for i in range(len(offsets)):
        outdoor = outdoor_temps[i]
        offset = offsets[i]
        
        # Physics Model
        delta_t = current_temp - outdoor
        loss = K_LEAK * delta_t
        gain = K_GAIN * offset
        
        # New temp
        current_temp = current_temp - loss + gain
        temps.append(current_temp)
        
    return temps

def optimize_24h_plan(
    current_temp: float,
    outdoor_temps: List[float],
    prices: List[float]
) -> List[float]:
    """
    Finds the cheapest Offset Schedule to keep temp >= TARGET_TEMP.
    Uses a Greedy Algorithm with Lookahead.
    """
    hours = min(len(outdoor_temps), len(prices))
    offsets = [0.0] * hours
    
    # Iteratively improve the plan until constraints are met
    max_iterations = 100
    
    for _ in range(max_iterations):
        # 1. Simulate current plan
        temps = predict_temperatures(current_temp, outdoor_temps, offsets)
        
        # 2. Find worst violation
        min_val = 999.0
        min_idx = -1
        
        for i in range(hours):
            # We want to be above TARGET, but absolutely above MIN_TEMP
            # We prioritize the deepest dip below TARGET.
            if temps[i] < min_val:
                min_val = temps[i]
                min_idx = i
        
        # 3. Check if we are satisfied
        # If the lowest point is above Target, we are done.
        # OR if we can't improve anymore.
        if min_val >= TARGET_TEMP:
            break
            
        # 4. Find best hour to boost BEFORE the dip
        # We need to add heat at time t <= min_idx.
        # Score = Effect / Cost
        # Effect: Heat added at 't' decays over time, but for simple physics (linear leak),
        # a degree added now persists nicely.
        # Cost: Price at time 't'.
        # COP Bonus: Warmer outdoor temp = Better COP = Cheaper heat.
        
        best_score = -999.0
        best_hour = -1
        
        for h in range(min_idx + 1):
            if offsets[h] >= 5.0: continue # Max offset constraint
            
            # COP Factor (Approx: 3% better per degree warmer)
            # COP ~ 3.0 + 0.1 * Outdoor
            cop_factor = 3.0 + (0.1 * outdoor_temps[h])
            if cop_factor < 1.0: cop_factor = 1.0
            
            # Price (Avoid division by zero)
            price = max(0.01, prices[h])
            
            # Decay factor (Value of heat decreases slightly over time due to higher leak)
            # Future hours are less valuable if we lose the heat before we need it.
            # (Time to dip) = min_idx - h
            decay = (1.0 - K_LEAK) ** (min_idx - h)
            
            # Score formula: (COP * Decay) / Price
            score = (cop_factor * decay) / price
            
            if score > best_score:
                best_score = score
                best_hour = h
        
        # 5. Apply Boost
        if best_hour != -1:
            offsets[best_hour] += 1.0
        else:
            # Cannot improve further (Maxed out)
            break
            
    return offsets
