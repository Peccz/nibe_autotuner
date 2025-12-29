with open('analyzer_check.py', 'r') as f: # Use downloaded file
    lines = f.readlines()

for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # REMOVED FALLBACK\n"
        break

with open('analyzer_no_fallback.py', 'w') as f:
    f.writelines(lines)
