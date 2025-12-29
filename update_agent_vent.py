with open('agent_v2_latest.py', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "5. HOT WATER STRATEGY" in line:
        # Find end of section
        for j in range(i, len(lines)):
            if "Output JSON only" in lines[j]:
                insert_idx = j
                break
        break

if insert_idx != -1:
    vent_rules = [
        "6. VENTILATION STRATEGY:\n",
        "   - IF Outdoor Temp < -10°C -> Consider reducing ventilation (Target Speed 1) to save heat.\n",
        "   - IF Electricity Price > 3.00 SEK/kWh -> Consider reducing ventilation (Target Speed 1).\n",
        "   - Otherwise: Maintain Normal (Target Speed 2/Normal).\n",
        "\n"
    ]
    lines.insert(insert_idx, "".join(vent_rules))

with open('agent_v2_vent.py', 'w') as f:
    f.writelines(lines)
