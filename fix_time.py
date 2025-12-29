with open('mobile_app_time.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "'timestamp': decision.timestamp.isoformat()" in line:
        # Check if Z is already there? No.
        # Replace line to append Z
        lines[i] = "                'timestamp': decision.timestamp.isoformat() + 'Z',\n"

with open('mobile_app_time_fixed.py', 'w') as f:
    f.writelines(lines)
