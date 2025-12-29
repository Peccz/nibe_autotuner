with open('agent_v2_to_optimize.py', 'r') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

# Hitta prompten
for i, line in enumerate(lines):
    if "STRATEGY LOGIC (Evaluate in order):" in line:
        start_idx = i
    if "Output JSON only." in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_strategy = """STRATEGY LOGIC (Evaluate in order):

1. COMFORT PROTECTION (The Law):
   - IF Indoor > {target_max}: REDUCE heating (Target -4 or -5).
   - IF Indoor < {min_temp}: INCREASE heating (Target -1 or 0).

2. WEATHER ANTICIPATION (Proactive):
   - IF Forecast implies drop >3C next 4h: PRE-HEAT (Increase +1 step from current).
   - IF Forecast implies rise >3C next 4h: COAST (Decrease -1 step from current).

3. PRICE TREND STRATEGY (If comfort is OK):
   - **Scenario A: Price is DROPPING soon** (Cheap later):
     ACTION: COASTING. Reduce heating to save energy.
     Target: -4 IF Indoor > 21.0C (Buffer exists).
     Target: -3 IF Indoor < 21.0C (Don't risk comfort).
   
   - **Scenario B: Price is RISING soon** (Expensive later):
     ACTION: PRE-HEATING. Increase heating to buffer heat.
     Target: -2 or -1 (Only if Indoor < 22).

   - **Scenario C: Stable Price**:
     - If Expensive: Target -4 (only if Indoor > 20.8C).
     - If Cheap: Target -2 (to build buffer).

4. STABILITY (Override):
   - IF Indoor is PERFECT ({target_min} - {target_max}) AND Price is Unknown/Stable:
     ACTION: HOLD or gentle move to Baseline (-3). Do NOT make drastic changes (>1 step) if comfort is good.

5. EXECUTION:
   - Determine target based on above.
   - Max change: +/- 3 steps allowed (if needed).
   - Explain reasoning clearly.

6. HOT WATER STRATEGY (Comfort Priority):
   - IF Predicted HW Usage (based on historical data) is HIGH (e.g., morning/evening) -> Ensure hot_water_demand is at least NORMAL (1).
   - IF Hot Water Temp is LOW (<45°C) -> Boost to LUX (2) immediately.
   - IF Electricity Price is CHEAP -> Boost hot_water_demand to LUX (2) to buffer heat.
   - ONLY reduce hot_water_demand to SMALL (0) if Predicted HW Usage is LOW AND Electricity Price is EXPENSIVE AND Hot Water Temp is >45°C.

7. VENTILATION STRATEGY:
   - IF Outdoor Temp < -10°C -> Consider reducing ventilation (Target Speed 1) to save heat.
   - IF Electricity Price > 3.00 SEK/kWh -> Consider reducing ventilation (Target Speed 1).
   - Otherwise: Maintain Normal (Target Speed 2/Normal).

"""
    del lines[start_idx:end_idx]
    lines.insert(start_idx, new_strategy)

with open('agent_v2_optimized.py', 'w') as f:
    f.writelines(lines)