with open('agent_v2_latest.py', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "target_max = device.target_indoor_temp_max + offset" in line:
        insert_idx = i + 1
        break

if insert_idx != -1:
    away_mode_logic = [
        "            # Check Away Mode\n",
        "            if device and device.away_mode_enabled:\n",
        "                # If away mode end date is passed, disable it\n",
        "                if device.away_mode_end_date and datetime.utcnow() > device.away_mode_end_date:\n",
        "                    device.away_mode_enabled = False\n",
        "                    device.away_mode_end_date = None\n",
        "                    session.add(device)\n",
        "                    session.commit()\n",
        "                    logger.info(\"Away mode end date passed. Disabling away mode.\")\n",
        "                else:\n",
        "                    # Override all settings for away mode\n",
        "                    min_temp = 16.0\n",
        "                    target_min = 16.0\n",
        "                    target_max = 17.0 # Small buffer to prevent constant heating\n",
        "                    logger.info(\"Away mode active. Overriding temp targets to 16-17C.\")\n",
        "            # End Away Mode logic\n"
    ]
    lines.insert(insert_idx, "".join(away_mode_logic))

# Update context builder with away mode status
# Find the return f""" block
return_f_string_idx = -1
for i, line in enumerate(lines):
    if line.strip().startswith("return f\"\"\"DT:"): # Find the start of the multiline f-string
        return_f_string_idx = i
        break

if return_f_string_idx != -1:
    # Add {away_mode_str} after {hw_str}
    # Find hw_str line and insert before
    hw_str_insert_idx = -1
    for i in range(return_f_string_idx, len(lines)):
        if "{hw_str}" in lines[i]:
            hw_str_insert_idx = i
            break
    if hw_str_insert_idx != -1:
        lines.insert(hw_str_insert_idx + 1, "{away_mode_str}\n")


# Add away_mode_str definition
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
        "            if device.away_mode_end_date: away_mode_str += \" Until: \" + device.away_mode_end_date.strftime('%Y-%m-%d %H:%M')\n" # FIX F-STRING IN F-STRING
    ]
    lines.insert(hw_str_def_idx + 4, "".join(away_mode_str_def)) # Insert after hw_str definition

with open('agent_v2_away.py', 'w') as f:
    f.writelines(lines)
