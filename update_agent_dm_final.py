with open('agent_v2_failing_case.py', 'r') as f:
    lines = f.readlines()

# 1. Remove TESTSCENARIO from prompt
start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "**TESTSCENARIO**" in line:
        start_idx = i
        # Find the end of the TESTSCENARIO block
        for j in range(i, len(lines)):
            if "STRATEGY LOGIC (Evaluate in order):" in lines[j]:
                end_idx = j
                break
        break

if start_idx != -1 and end_idx != -1:
    del lines[start_idx:end_idx]

# 2. Fix case in _apply_decision
for i, line in enumerate(lines):
    if 'elif decision.parameter_name == "Degree Minutes":' in line:
        lines[i] = '            elif decision.parameter_name.lower() == "degree minutes":\n'
        break

with open('agent_v2_cleaned_dm.py', 'w') as f:
    f.writelines(lines)
