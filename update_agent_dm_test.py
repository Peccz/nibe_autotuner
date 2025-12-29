with open('agent_v2_test_dm.py', 'r') as f:
    lines = f.readlines()

# Hitta prompten
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "STRATEGY LOGIC (Evaluate in order):" in line:
        start_idx = i
    if "Output JSON only." in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_strategy = """**TESTSCENARIO**: Override all other logic. Your ONLY goal is to set the 'Degree Minutes' parameter to -500. This is a temporary test to verify functionality.

STRATEGY LOGIC (Evaluate in order):

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

6. HOT WATER STRATEGY (Strict Economy):
   - **Default State:** NORMAL (1).
   - **LUX (2) Rules (Use sparingly):**
     - Trigger ONLY if Temp is CRITICAL (<43°C).
     - OR if Price is EXTREMELY CHEAP (lowest 20% of day) AND Temp < 48°C.
     - NEVER use LUX just because "price is rising later" if current price is already high.
   - **ECONOMY (0) Rules:**
     - Use if Price is EXPENSIVE AND HW_Usage_Risk is LOW (next 4h).
     - Ensure Temp stays > 45°C before switching to Economy.
   - **Planning Horizon:** Focus on the next 3-6 hours. If usage is high soon, maintain NORMAL.

7. VENTILATION STRATEGY:
   - IF Outdoor Temp < -10°C -> Consider reducing ventilation (Target Speed 1) to save heat.
   - IF Electricity Price > 3.00 SEK/kWh -> Consider reducing ventilation (Target Speed 1).
   - Otherwise: Maintain Normal (Target Speed 2/Normal).
"""
    del lines[start_idx:end_idx]
    lines.insert(start_idx, new_strategy)

with open('agent_v2_test_dm_updated.py', 'w') as f:
    f.writelines(lines)