with open('data_logger_current.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "elif abs(point['value'] - last_reading.value) > 0.001:" in line:
        # Insert keep-alive check before else
        new_lines = """                        elif (datetime.utcnow() - last_reading.timestamp).total_seconds() > 1800:
                            # Keep-alive: Force log every 30 mins even if no change, so we know sensor is alive
                            timestamp = datetime.utcnow()
"""
        lines.insert(i + 4, new_lines) # Insert after the value change block
        break

with open('data_logger_keepalive.py', 'w') as f:
    f.writelines(lines)