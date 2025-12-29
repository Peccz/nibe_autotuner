with open('temp_analyzer_debug.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "def get_latest_value" in line:
        # Insert extensive debug
        debug_code = [
            "        print(f\"DEBUG: get_latest_value for '{parameter_id_str}' type={type(parameter_id_str)}\")\n",
            "        # Debug: list params\n",
            "        # all_params = self.session.query(Parameter).all()\n",
            "        # for p in all_params:\n",
            "        #    if str(p.parameter_id) == str(parameter_id_str):\n",
            "        #        print(f\"DEBUG: Found MATCH in loop: {p.id} {p.parameter_id}\")\n"
        ]
        lines.insert(i+1, "".join(debug_code))
        
        # Find where param is queried
        for j in range(i, len(lines)):
            if "param =" in lines[j] and "self.session.query" in lines[j]:
                # After query
                lines.insert(j+3, "            print(f\"DEBUG: Param query result: {param}\")\n")
                break
        break

# Remove fallback
for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # DISABLED FALLBACK\n"

with open('analyzer_debug_deep.py', 'w') as f:
    f.writelines(lines)
