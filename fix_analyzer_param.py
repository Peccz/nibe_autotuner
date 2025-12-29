with open('src/services/analyzer.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "PARAM_DM_CURRENT = '40009'" in line:
        lines[i] = "    PARAM_DM_CURRENT = '40941'   # Degree Minutes Current (Read Only)\n"
        break

with open('analyzer_fixed_param.py', 'w') as f:
    f.writelines(lines)
