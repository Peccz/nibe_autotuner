with open('analyzer_to_clean.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    # Remove specific debug prints
    if "logger.debug(f\"[Analyzer.get_latest_value]" in line:
        continue
    # Remove specific warning (we want to keep the error log, but remove our specific warning)
    if "logger.warning(f\"[Analyzer.get_latest_value] Parameter '" in line:
        continue
    if "logger.warning(f\"[Analyzer.get_latest_value] No reading found for device" in line:
        continue
    
    new_lines.append(line)

with open('analyzer_cleaned.py', 'w') as f:
    f.writelines(new_lines)
