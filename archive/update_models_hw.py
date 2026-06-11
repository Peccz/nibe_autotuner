with open('models_current.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "planned_offset = Column(Float, default=0.0)" in line:
        lines.insert(i + 1, "    planned_hot_water_mode = Column(Integer, default=1) # 0=Eco, 1=Normal, 2=Lux\n")
        break

with open('models_with_hw.py', 'w') as f:
    f.writelines(lines)
