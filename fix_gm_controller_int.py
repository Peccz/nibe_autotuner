with open('gm_controller_broken.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "self.client.set_point_value(device_id, self.PARAM_GM_WRITE, value)" in line:
        lines[i] = "                self.client.set_point_value(device_id, self.PARAM_GM_WRITE, int(round(value)))\n"
        break

with open('gm_controller_int_fix.py', 'w') as f:
    f.writelines(lines)
