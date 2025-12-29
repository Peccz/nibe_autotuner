with open('agent_v2_failing_dm_test.py', 'r') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "**TESTSCENARIO**" in line:
        start_idx = i
        break
for i in range(start_idx, len(lines)):
    if "STRATEGY LOGIC (Evaluate in order):" in line: # Find start of next section
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    new_test_scenario = """**TESTSCENARIO**: Override all other logic. Your ONLY goal is to change parameter ID 40940 (named 'Degree Minutes') to a new value of -500. Respond with ACTION: "adjust", parameter_name: "Degree Minutes", new_value: -500.

STRATEGY LOGIC (Evaluate in order):
"""
    del lines[start_idx:end_idx]
    lines.insert(start_idx, new_test_scenario)

with open('agent_v2_dm_test_updated.py', 'w') as f:
    f.writelines(lines)