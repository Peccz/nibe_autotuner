with open('analyzer_to_update.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "PARAM_DM_CURRENT =" in line:
        lines.insert(i + 1, "    PARAM_DM_WRITE = '40940'     # Degree Minutes Writeable (current value for writing)\n")
        break

with open('analyzer_updated_dm.py', 'w') as f:
    f.writelines(lines)
