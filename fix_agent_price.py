with open('agent_v2_to_fix_price.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "Current Electricity Price: {self.price_service.get_current_price().price_per_kwh:.2f} SEK/kWh" in line:
        lines[i] = line.replace(".price_per_kwh", "")
        break

with open('agent_v2_final_price_fix.py', 'w') as f:
    f.writelines(lines)