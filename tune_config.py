with open('config_current.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "K_GM_PER_DELTA_T_PER_H: float =" in line:
        lines[i] = "    K_GM_PER_DELTA_T_PER_H: float = 3.0 # GM lost per degree-hour difference (Lowered from 4.0)\n"
        break

with open('config_tuned.py', 'w') as f:
    f.writelines(lines)
