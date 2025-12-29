with open('src/services/analyzer.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "def get_latest_value(self, device: Device, parameter_id_str: str) -> Optional[float]:" in line:
        lines.insert(i + 1, "        self.session.expire_all() # Force refresh from DB\n")
        break

for i, line in enumerate(lines):
    if "def calculate_metrics(" in line:
        lines.insert(i + 1, "        self.session.expire_all() # Force refresh from DB\n")
        break

with open('analyzer_fixed_session.py', 'w') as f:
    f.writelines(lines)
