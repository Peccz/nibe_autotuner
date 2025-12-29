with open('config_old.py', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "class Config:" in line:
        insert_idx = i -1 # Insert before Config class
        break

if insert_idx != -1:
    new_settings = """
    # SmartPlanner settings
    K_GM_PER_DELTA_T_PER_H: float = 4.0 # GM lost per degree-hour difference
    COMPRESSOR_HEAT_OUTPUT_C_PER_H: float = 0.5 # Degrees Celsius gain per hour when compressor is running
    GM_PRODUCTION_PER_HOUR_RUNNING: float = 60.0 # GM produced per hour when compressor is running
"""
    lines.insert(insert_idx, new_settings)

with open('config_new.py', 'w') as f:
    f.writelines(lines)