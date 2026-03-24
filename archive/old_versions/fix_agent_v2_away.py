with open('agent_v2_after_away.py', 'r') as f:
    lines = f.readlines()

# 1. Update analyze_and_decide call to _build_optimized_context
for i, line in enumerate(lines):
    if "context = self._build_optimized_context(metrics)" in line:
        lines[i] = line.replace("context = self._build_optimized_context(metrics)", "        context = self._build_optimized_context(metrics, device)\n")
        break

# 2. Update _build_optimized_context signature
for i, line in enumerate(lines):
    if "def _build_optimized_context(self, metrics) -> str:" in line:
        lines[i] = line.replace("def _build_optimized_context(self, metrics) -> str:", "    def _build_optimized_context(self, metrics, device) -> str:\n")
        break

# 3. Add away_mode_str definition inside _build_optimized_context
# Find where hw_str is defined
hw_str_def_idx = -1
for i, line in enumerate(lines):
    if "hw_str =" in line:
        hw_str_def_idx = i
        break

if hw_str_def_idx != -1:
    away_mode_str_def = [
        "        away_mode_str = \"\"\n",
        "        if device and device.away_mode_enabled:\n",
        "            away_mode_str = \"AWAY_MODE_ACTIVE: Target indoor 16-17C, hot water demand MUST be 0.\"\n",
        "            if device.away_mode_end_date: away_mode_str += \" Until: \" + device.away_mode_end_date.strftime('%Y-%m-%d %H:%M')\n"
    ]
    lines.insert(hw_str_def_idx + 4, "".join(away_mode_str_def)) # Insert after hw_str definition

# 4. Update the return f""" block to include away_mode_str
for i, line in enumerate(lines):
    if line.strip().startswith("return f\"\"\"DT:"):
        # Look for {hw_str} and insert after it
        for j in range(i, len(lines)):
            if "{hw_str}" in lines[j]:
                lines.insert(j + 1, "{away_mode_str}\n")
                break
        break

with open('agent_v2_away_fixed.py', 'w') as f:
    f.writelines(lines)
