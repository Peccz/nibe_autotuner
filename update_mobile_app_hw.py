with open('agent_v2_to_optimize.py', 'r') as f:
    lines = f.readlines()

# 1. Update Code Logic for HW Horizon (Look ahead 4 hours)
for i, line in enumerate(lines):
    if "hw_prob = self.hw_analyzer.get_usage_probability(datetime.now())" in line:
        # Replace with loop for max probability next 4h
        new_code = """            # Look ahead 4 hours for HW risk
            probs = [self.hw_analyzer.get_usage_probability(datetime.now() + timedelta(hours=h)) for h in range(5)]
            hw_prob = max(probs) if probs else 0.0
"""
        lines[i] = new_code
        break

# 2. Update Prompt Logic
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "6. HOT WATER STRATEGY" in line:
        start_idx = i
    if "7. VENTILATION STRATEGY" in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_strategy = """6. HOT WATER STRATEGY (Strict Economy):
   - **Default State:** NORMAL (1).
   - **LUX (2) Rules (Use sparingly):**
     - Trigger ONLY if Temp is CRITICAL (<43°C).
     - OR if Price is EXTREMELY CHEAP (lowest 20% of day) AND Temp < 48°C.
     - NEVER use LUX just because "price is rising later" if current price is already high.
   - **ECONOMY (0) Rules:**
     - Use if Price is EXPENSIVE AND HW_Usage_Risk is LOW (next 4h).
     - Ensure Temp stays > 45°C before switching to Economy.
   - **Planning Horizon:** Focus on the next 3-6 hours. If usage is high soon, maintain NORMAL.

"""
    del lines[start_idx:end_idx]
    lines.insert(start_idx, new_strategy)

# Ensure timedelta import
has_timedelta = False
for line in lines:
    if "from datetime import" in line and "timedelta" in line:
        has_timedelta = True
        break

if not has_timedelta:
    for i, line in enumerate(lines):
        if "from datetime import" in line:
            lines[i] = line.strip() + ", timedelta\n"
            break

with open('agent_v2_hw_optimized.py', 'w') as f:
    f.writelines(lines)