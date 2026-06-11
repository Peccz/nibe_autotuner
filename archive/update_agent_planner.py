with open('agent_v2_original.py', 'r') as f: # Use the newly downloaded file
    lines = f.readlines()

# 1. Add SmartPlanner import and initialization
for i, line in enumerate(lines):
    if "from integrations.autonomous_ai_agent import AIDecision, AutonomousAIAgent" in line:
        lines.insert(i, "from services.smart_planner import SmartPlanner\n")
        break

for i, line in enumerate(lines):
    if "self.learning_service = LearningService(self.db, self.analyzer)" in line:
        lines.insert(i + 1, "        self.planner = SmartPlanner()\n")
        break

# 2. Call planner.plan_next_24h() and update AI's role
start_analyze_decide_idx = -1
for i, line in enumerate(lines):
    if "def analyze_and_decide(self) -> AIDecision:" in line:
        start_analyze_decide_idx = i
        break

if start_analyze_decide_idx != -1:
    # Insert planner call at the beginning of analyze_and_decide
    insert_idx = start_analyze_decide_idx + 2 # After def line
    lines.insert(insert_idx, "        self.planner.plan_next_24h() # Generate/Update the 24h plan\n")
    lines.insert(insert_idx + 1, "\n")
    
    # Get GM Account
    lines.insert(insert_idx + 2, "        gm_account = self.session.query(GMAccount).first()\n")
    lines.insert(insert_idx + 3, "        current_gm_balance = gm_account.balance if gm_account else 0.0\n")
    lines.insert(insert_idx + 4, "        gm_mode = gm_account.mode if gm_account else 'NORMAL'\n")
    lines.insert(insert_idx + 5, "\n")

    # Update the prompt text for the AI's new role
    prompt_start_idx = -1
    prompt_end_idx = -1
    for i in range(start_analyze_decide_idx, len(lines)):
        if "You are an autonomous AI agent controlling a Nibe heat pump" in lines[i]:
            prompt_start_idx = i
        if "Output JSON only." in lines[i]:
            prompt_end_idx = i
            break

    if prompt_start_idx != -1 and prompt_end_idx != -1:
        new_prompt_text = """        prompt = f'''\n"
        new_prompt_text += "You are an autonomous AI agent controlling a Nibe heat pump. Your primary role is to set the strategy for the 'Gradminut Banken' (Degree Minute Bank) by updating the 'gm_account.mode' in the database to 'SAVE', 'SPEND', or 'NORMAL', and to adjust the 'Heating Curve Offset' (47011) to control the rate of GM accumulation/consumption. The 'gm_controller' service will execute the minute-by-minute GM adjustments to the pump based on your mode decision and the current heating plan.\n"
        new_prompt_text += "\n"
        new_prompt_text += "**System State:**\n"
        new_prompt_text += "Current Time: {current_time}\n"
        new_prompt_text += "Outdoor Temp: {outdoor_temp:.1f}°C\n"
        new_prompt_text += "Indoor Temp: {indoor_temp:.1f}°C (Target: {target_min}-{target_max}°C, Min Safety: {min_temp}°C)\n"
        new_prompt_text += "Heating Curve: {current_curve:.1f}, Offset: {current_offset:.1f}\n"
        new_prompt_text += "Current Electricity Price: {current_price:.2f} SEK/kWh (Low: {low_price:.2f}, High: {high_price:.2f}, Avg: {avg_price:.2f})\n"
        new_prompt_text += "Next 6 Hours Price Trend: {price_trend}\n"
        new_prompt_text += "Weather Forecast (next 6h): {weather_trend}\n"
        new_prompt_text += "HW Usage Risk (next 4h): {hw_str}\n"
        new_prompt_text += "House DNA (Thermal Inertia): {dna_str}\n"
        new_prompt_text += "Away Mode: {away_mode_str}\n"
        new_prompt_text += "GM Bank Balance: {current_gm_balance:.1f} (Mode: {gm_mode})\n"
        new_prompt_text += "\n"
        new_prompt_text += "**Adjustable Parameters (Your Direct Control):**\n"
        new_prompt_text += "- Heating Curve Offset (47011): Current={current_offset}, Range=[-10 to 10], Step=0.5\n"
        new_prompt_text += "- Heating Curve (47007): Current={current_curve}, Range=[1 to 15], Step=0.5\n"
        new_prompt_text += "- GM Bank Mode (DB: gm_account.mode): Current='{gm_mode}', Options=['SAVE', 'SPEND', 'NORMAL']\n"
        new_prompt_text += "\n"
        new_prompt_text += "**Goal:** Optimize comfort and economy.\n"
        new_prompt_text += "- Keep indoor temperature within target range.\n"
        new_prompt_text += "- Utilize cheap electricity for heating.\n"
        new_prompt_text += "- Avoid peak prices.\n"
        new_prompt_text += "- Prioritize long, efficient compressor runs.\n"
        new_prompt_text += "\n"
        new_prompt_text += "**STRATEGY LOGIC (Evaluate in order):**\n"
        new_prompt_text += "\n"
        new_prompt_text += "1. COMFORT PROTECTION (Hard Limits):\n"
        new_prompt_text += "   - IF Indoor < {min_safety_temp} (absolute minimum):\n"
        new_prompt_text += "     ACTION: 'adjust', parameter_name: 'gm_account.mode', new_value: 'SPEND', reasoning: 'Emergency comfort. Indoor temp below safety limit.'\n"
        new_prompt_text += "   - IF Indoor > {target_max} + 0.5 (excessive heat):\n"
        new_prompt_text += "     ACTION: 'adjust', parameter_name: 'gm_account.mode', new_value: 'SAVE', reasoning: 'Emergency cooling. Indoor temp above target.'\n"
        new_prompt_text += "\n"
        new_prompt_text += "2. PRICE OPTIMIZATION & GM BANK MANAGEMENT:\n"
        new_prompt_text += "   - IF current price is VERY CHEAP (e.g., lowest 10% of day) AND GM Bank Balance < {MAX_BALANCE - 200} (room for more):\n"
        new_prompt_text += "     ACTION: 'adjust', parameter_name: 'gm_account.mode', new_value: 'SPEND', reasoning: 'Maximize heat production during very cheap hours.'\n"
        new_prompt_text += "   - IF current price is VERY EXPENSIVE (e.g., highest 10% of day) AND GM Bank Balance > {MIN_BALANCE + 200} (not in danger of freezing):\n"
        new_prompt_text += "     ACTION: 'adjust', parameter_name: 'gm_account.mode', new_value: 'SAVE', reasoning: 'Minimize heat production during very expensive hours.'\n"
        new_prompt_text += "   - IF current price is MODERATE AND GM Bank Balance < {target_min_gm_balance} (e.g., -200):\n"
        new_prompt_text += "     ACTION: 'adjust', parameter_name: 'gm_account.mode', new_value: 'SPEND', reasoning: 'Replenish GM balance to ensure comfort.'\n"
        new_prompt_text += "   - IF current price is MODERATE AND GM Bank Balance > {target_max_gm_balance} (e.g., 0):\n"
        new_prompt_text += "     ACTION: 'adjust', parameter_name: 'gm_account.mode', new_value: 'SAVE', reasoning: 'Accumulate GM savings to utilize future cheap periods.'\n"
        new_prompt_text += "\n"
        new_prompt_text += "3. DEFAULT / STABILITY:\n"
        new_prompt_text += "   - ACTION: 'hold', reasoning: 'Maintain current GM bank mode as no strong imperative for change.'\n"
        new_prompt_text += "\n"
        new_prompt_text += "**IMPORTANT:** Respond ONLY with a valid JSON object. Do not include any other text.\n"
        new_prompt_text += "'''\n"
        # Replace the entire prompt block
        del lines[prompt_start_idx : prompt_end_idx]
        lines.insert(prompt_start_idx, new_prompt_text)

    # Add GMAccount import to autonomous_ai_agent_v2.py
    for i, line in enumerate(lines):
        if "from data.models import AIDecisionLog, Parameter, ParameterChange, PlannedTest, ABTestResult" in line:
            lines[i] = "from data.models import AIDecisionLog, Parameter, ParameterChange, PlannedTest, ABTestResult, GMAccount\n"
            break

with open('agent_v2_gm_planner_integrated.py', 'w') as f:
    f.writelines(lines)
