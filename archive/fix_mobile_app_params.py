with open('temp_mobile_app_v6.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "'outdoor': 40004," in line:
        lines[i] = "            'outdoor': '40004',\n"
    if "'indoor': 40033," in line:
        lines[i] = "            'indoor': '40033',\n"
    if "'supply': 40008," in line:
        lines[i] = "            'supply': '40008',\n"
    if "'return': 40012," in line:
        lines[i] = "            'return': '40012',\n"
    if "'compressor': 41778," in line:
        lines[i] = "            'compressor': '41778',\n"
    if "'hot_water': 40013," in line:
        lines[i] = "            'hot_water': '40013',\n"
    if "'pump_speed': 43437" in line:
        lines[i] = "            'pump_speed': '43437'\n"

with open('mobile_app_params_fixed.py', 'w') as f:
    f.writelines(lines)