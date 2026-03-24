with open('temp_analyzer_debug.py', 'r') as f:
    lines = f.readlines()

# 1. Add debug prints to get_latest_value
for i, line in enumerate(lines):
    if "def get_latest_value" in line:
        # Insert debug print at start of method
        lines.insert(i+1, "        print(f\"DEBUG: get_latest_value for {parameter_id_str}\")\n")
        
        # Find where param is queried
        # Look for "if not param:"
        for j in range(i, len(lines)):
            if "if not param:" in lines[j]:
                # Insert before "if not param:" means we found it? No, insert after query.
                # Query is before.
                # Insert inside the if not param block? No.
                # Insert after if not param block (which returns).
                # Find the next line after return None
                pass
            
            if "if reading:" in lines[j]:
                 lines.insert(j+1, "                print(f\"DEBUG: Found reading: {reading.value}\")\n")
                 break
        break

# 2. Remove fallback
for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # DISABLED FALLBACK\n"

with open('analyzer_debugged.py', 'w') as f:
    f.writelines(lines)
