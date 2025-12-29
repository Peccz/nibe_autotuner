with open('analyzer_clean_github.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # REMOVED FALLBACK\n"
        break

with open('analyzer_no_fallback_fixed.py', 'w') as f:
    f.writelines(lines)
