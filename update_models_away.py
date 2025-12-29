with open('models_latest.py', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "comfort_adjustment_offset =" in line:
        insert_idx = i + 1
        break

if insert_idx != -1:
    new_cols = [
        "\n",
        "    # Away Mode\n",
        "    away_mode_enabled = Column(Boolean, default=False)\n",
        "    away_mode_end_date = Column(DateTime, nullable=True)\n"
    ]
    lines.insert(insert_idx, "".join(new_cols))

with open('models_away.py', 'w') as f:
    f.writelines(lines)
