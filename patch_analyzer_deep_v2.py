with open('analyzer_to_debug.py', 'r') as f:
    lines = f.readlines()

# Remove fallback
for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # REMOVED FALLBACK\n"
        break

# Add debug prints to get_latest_value
start_idx = -1
for i, line in enumerate(lines):
    if "def get_latest_value(self, device: Device, parameter_id_str: str)" in line:
        start_idx = i
        break

if start_idx != -1:
    # Insert at start of method
    lines.insert(start_idx + 1, "        logger.debug(f\"[Analyzer.get_latest_value] Device ID: {device.id}, Param ID Str: '{parameter_id_str}'\")\n")
    
    # After param query
    for i in range(start_idx, len(lines)):
        if "if not param:" in lines[i]: # Insert before this line
            lines.insert(i, "            logger.debug(f\"[Analyzer.get_latest_value] Query result for param '{parameter_id_str}': {param}\")\n")
            break
            
    # If not param branch
    for i in range(start_idx, len(lines)):
        if "return None" in lines[i] and "if not param" in lines[i-1]:
            lines.insert(i, "            logger.warning(f\"[Analyzer.get_latest_value] Parameter '{parameter_id_str}' NOT FOUND in self.session!\")\n")
            break

    # If param found branch
    for i in range(start_idx, len(lines)):
        if "if reading:" in lines[i]:
            lines.insert(i, "            logger.debug(f\"[Analyzer.get_latest_value] Found param ORM: {param.id} ('{param.parameter_name}')\")\n")
            lines.insert(i + 2, "            logger.debug(f\"[Analyzer.get_latest_value] Found reading: {reading.value} @ {reading.timestamp}\")\n")
            break

    # No reading found branch
    for i in range(start_idx, len(lines)):
        if "return None" in lines[i] and "No reading found" not in lines[i-1]: # To avoid double insert
            lines.insert(i, "            logger.warning(f\"[Analyzer.get_latest_value] No reading found for device {device.id} param {param.id}\")\n")
            break


with open('analyzer_patched_debug.py', 'w') as f:
    f.writelines(lines)
