with open('analyzer_final_patch_clean.py', 'r') as f: # Use the last uploaded file
    lines = f.readlines()

# Check if desc is imported
has_desc = False
for line in lines:
    if "from sqlalchemy import" in line and "desc" in line:
        has_desc = True
        break

if not has_desc:
    for i, line in enumerate(lines):
        if "from sqlalchemy import" in line:
            lines[i] = line.strip() + ", desc\n"
            break

with open('analyzer_fixed_desc.py', 'w') as f:
    f.writelines(lines)
