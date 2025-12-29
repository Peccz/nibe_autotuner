with open('agent_v2_clean_base.py', 'r') as f:
    lines = f.readlines()

# --- 1. Modify analyze_and_decide: Pass 'device' object to context builders ---
# Modify analyze_and_decide's call to _build_optimized_context
for i, line in enumerate(lines):
    if "context = self._build_optimized_context(metrics)" in line:
        lines[i] = "        context = self._build_optimized_context(metrics, device) # Pass device\n"
        break

# Modify analyze_and_decide's call to _create_optimized_prompt
for i, line in enumerate(lines):
    if "prompt = self._create_optimized_prompt(context, min_temp, target_min, target_max, mode, metrics)" in line:
        lines[i] = "        prompt = self._create_optimized_prompt(context, min_temp, target_min, target_max, mode, metrics, device) # Pass device\n"
        break

# --- 2. Modify _build_optimized_context: Add 'device' to signature and away_mode logic ---
for i, line in enumerate(lines):
    if "def _build_optimized_context(self, metrics) -> str:" in line:
        lines[i] = "    def _build_optimized_context(self, metrics, device) -> str: # Added device\n"
        break

# Add away_mode_str definition and usage in _build_optimized_context's return f-string
for i, line in enumerate(lines):
    if line.strip().startswith("hw_str = f\"HW_Usage_Risk"):
        lines.insert(i + 1, "        away_mode_str = \"\"\n")
        lines.insert(i + 2, "        if device and device.away_mode_enabled:\n")
        lines.insert(i + 3, "            away_mode_str = \"AWAY_MODE_ACTIVE: Target indoor 16-17C, hot water demand MUST be 0.\"\n")
        lines.insert(i + 4, "            if device.away_mode_end_date: away_mode_str += f\" Until: {device.away_mode_end_date.strftime('%Y-%m-%d %H:%M')}\"\n")
        break

for i, line in enumerate(lines):
    if line.strip().startswith("return f\"\""DT:"):
        # Find {hw_str} and insert {away_mode_str} after it
        for j in range(i, len(lines)):
            if "{hw_str}" in lines[j]:
                lines.insert(j + 1, "{away_mode_str}\n")
                break
        break

# --- 3. Modify _create_optimized_prompt: Add 'device' to signature and away_mode override ---
for i, line in enumerate(lines):
    if "def _create_optimized_prompt(self, context: str, min_temp: float, target_min: float, target_max: float, mode: str = \"tactical\", metrics=None) -> str:" in line:
        lines[i] = "    def _create_optimized_prompt(self, context: str, min_temp: float, target_min: float, target_max: float, mode: str = \"tactical\", metrics=None, device=None) -> str: # Added device\n"
        break

# --- 4. Add away mode override logic ---
# Insert just before the "Metrics & Context" section's min_temp, target_min/max calculation
for i, line in enumerate(lines):
    if line.strip().startswith("min_temp = device.min_indoor_temp_user_setting"): # This line needs to be updated. This is wrong target.
        # find device = session.query(Device).filter(Device.device_id == self.device_id).first()
        for j in range(i, len(lines)): # Search from where device is defined
            if "device = session.query(Device).filter(Device.device_id == self.device_id).first()" in lines[j]:
                # Insert away mode logic right after device is defined.
                insert_away_logic_idx = j + 1
                
                away_logic = [
                    "            # Override settings for Away Mode\n",
                    "            if device and device.away_mode_enabled:\n",
                    "                # If away mode end date is passed, disable it\n",
                    "                if device.away_mode_end_date and datetime.utcnow() > device.away_mode_end_date:\n",
                    "                    device.away_mode_enabled = False\n",
                    "                    device.away_mode_end_date = None\n",
                    "                    session.add(device)\n",
                    "                    session.commit()\n",
                    "                    logger.info(\"Away mode end date passed. Disabling away mode.\")\n",
                    "                else:\n",
                    "                    logger.info(\"Away mode active. Overriding temp targets to 16-17C.\")\n",
                    "                    min_temp = 16.0\n",
                    "                    target_min = 16.0\n",
                    "                    target_max = 17.0\n",
                    "                    # No other rules apply, return a specific decision to set HW to 0.0\n",
                    "                    # This decision should be taken by the AI in the prompt, not hardcoded here.\n",
                    "                    # But we can override if it's critical.\n",
                    "                    # For now, let the prompt handle it using the AWAY_MODE_ACTIVE context.\n"
                ]
                lines.insert(insert_away_logic_idx, "".join(away_logic))
                break
        break

# --- 5. Fix the original min_temp, target_min/max calculation ---
# This needs to be outside the away mode logic, and use the overridden values
for i, line in enumerate(lines):
    if "min_temp = device.min_indoor_temp_user_setting + offset" in line:
        # Check if the line is inside the original calculation, not my new away logic
        for j in range(i, 0, -1):
            if "if device:" in lines[j]: # Found the start of the original if device block
                # Insert a check whether min_temp etc was ALREADY defined by away mode
                lines.insert(i, "                if 'min_temp' not in locals(): # Only calculate if not overridden by away mode\n")
                lines.insert(i+1, "                    min_temp = device.min_indoor_temp_user_setting + offset\n")
                lines.insert(i+2, "                    target_min = device.target_indoor_temp_min + offset\n")
                lines.insert(i+3, "                    target_max = device.target_indoor_temp_max + offset\n")
                # Delete the original lines
                del lines[i+4:i+7]
                break
        break

with open('agent_v2_away_final.py', 'w') as f:
    f.writelines(lines)
