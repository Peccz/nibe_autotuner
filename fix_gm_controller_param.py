with open('src/services/gm_controller.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "PARAM_GM_READ = '40009'" in line:
        lines[i] = "    PARAM_GM_READ = '40941' # FIXED: Correct ID for Degree Minutes (Read Only)\n"
        break

with open('gm_controller_fixed.py', 'w') as f:
    f.writelines(lines)
