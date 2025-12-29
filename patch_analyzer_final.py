with open('analyzer_clean_github.py', 'r') as f:
    lines = f.readlines()

# 1. Add debug prints to get_latest_value
# Find def get_latest_value
start_idx = -1
for i, line in enumerate(lines):
    if "def get_latest_value(self, device: Device, parameter_id_str: str) -> Optional[float]:" in line:
        start_idx = i
        break

if start_idx != -1:
    # Insert debug print at start of method
    lines.insert(start_idx + 1, "        logger.debug(f\"[Analyzer.get_latest_value] Device ID: {device.id}, Param ID Str: '{parameter_id_str}'\")\n")
    
    # After param query
    for i in range(start_idx, len(lines)):
        if "param = self.session.query(Parameter).filter_by(" in lines[i]:
            lines.insert(i + 3, "            logger.debug(f\"[Analyzer.get_latest_value] Param query result: {param}\")\n")
            break
            
    # If not param branch
    for i in range(start_idx, len(lines)):
        if "if not param:" in lines[i]:
            lines.insert(i + 1, "            logger.warning(f\"[Analyzer.get_latest_value] Parameter '{parameter_id_str}' NOT FOUND in self.session!\")\n")
            break

    # If param found branch
    for i in range(start_idx, len(lines)):
        if "if reading:" in lines[i]:
            lines.insert(i + 1, "            logger.debug(f\"[Analyzer.get_latest_value] Found param ORM: {param.id} ('{param.parameter_name}')\")\n")
            lines.insert(i + 2, "            logger.debug(f\"[Analyzer.get_latest_value] Found reading: {reading.value} @ {reading.timestamp}\")\n")
            break
            
    # No reading found branch
    for i in range(start_idx, len(lines)):
        if "return None" in lines[i] and "logger.warning(f\"[Analyzer.get_latest_value] No reading found" not in lines[i-1]: # To avoid double insert if already there
            # Find the return None inside get_latest_value
            # This is complex. Let's make it simpler.
            # Insert before the last return None of the try block
            for j in range(i, len(lines)):
                if "except Exception as e:" in lines[j]: # find end of try block
                    lines.insert(j-1, "            logger.warning(f\"[Analyzer.get_latest_value] No reading found for device {device.id} param {param.id}\")\n")
                    break
            break


# 2. Remove fallback (this has been problematic. Find it precisely and comment out)
for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # REMOVED FALLBACK\n"
        break

with open('analyzer_debugged_and_fixed.py', 'w') as f:
    f.writelines(lines)
