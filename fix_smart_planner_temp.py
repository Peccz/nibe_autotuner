with open('src/services/smart_planner.py', 'r') as f:
    lines = f.readlines()

# Hitta där vi hämtar metrics
insert_idx = -1
for i, line in enumerate(lines):
    if "current_indoor_temp = current_metrics.avg_indoor_temp" in line:
        insert_idx = i + 1
        break

if insert_idx != -1:
    fallback_logic = """        
        # Fallback 1: Latest known value from DB (if metrics is None or avg is None)
        if current_indoor_temp is None:
            latest = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_INDOOR_TEMP)
            if latest is not None:
                current_indoor_temp = latest
                logger.warning(f"Using latest known indoor temp (older than 1h): {latest}°C")
"""
    lines.insert(insert_idx, fallback_logic)

with open('src/services/smart_planner.py', 'w') as f:
    f.writelines(lines)