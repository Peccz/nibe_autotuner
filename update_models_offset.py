with open('models_latest_v2.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "planned_gm_value = Column(Float)" in line:
        lines.insert(i + 1, "    planned_offset = Column(Float, default=0.0)\n")
        break

with open('models_with_offset.py', 'w') as f:
    f.writelines(lines)
