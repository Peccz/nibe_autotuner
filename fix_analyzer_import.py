with open('analyzer_broken_import.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "from data.models import (" in line:
        new_lines.append(line)
        # Assuming OptimizationOpportunity is on the next line within the parenthesis
        for j in range(lines.index(line) + 1, len(lines)):
            if "OptimizationOpportunity" in lines[j]:
                pass # Skip this line
            elif ")" in lines[j]: # End of import block
                new_lines.append(lines[j])
                break
            else:
                new_lines.append(lines[j])
        break # Done with this part
    else:
        new_lines.append(line)

with open('analyzer_fixed_import.py', 'w') as f:
    f.writelines(new_lines)