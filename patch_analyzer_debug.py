with open('temp_analyzer_debug.py', 'r') as f:
    lines = f.readlines()

# 1. Add debug prints to get_latest_value
for i, line in enumerate(lines):
    if "def get_latest_value" in line:
        # Insert debug print at start of method
        lines.insert(i+1, "        print(f\"DEBUG: get_latest_value for {parameter_id_str}\")\n")
        
        # Find where param is queried
        for j in range(i, len(lines)):
            if "if not param:" in lines[j]:
                lines.insert(j, "            print(f\"DEBUG: Found param: {param}\")\n")
                break
        
        # Find return reading.value
        for j in range(i, len(lines)):
            if "return reading.value" in lines[j]:
                lines.insert(j, "                print(f\"DEBUG: Found reading: {reading.value}\")\n")
                break
        break

# 2. Remove fallback
for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # DISABLED FALLBACK\n"
        print("Disabled fallback")

with open('analyzer_debugged.py', 'w') as f:
    f.writelines(lines)
