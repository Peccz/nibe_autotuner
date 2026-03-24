with open('src/data/data_logger.py', 'r') as f:
    lines = f.readlines()

# Hitta loopen
start_idx = -1
for i, line in enumerate(lines):
    if "Check duplicate/stale" in line:
        start_idx = i
        break

if start_idx != -1:
    # Vi ska ersätta if-satsen
    # Hitta slutet av if-satsen (continue)
    end_idx = -1
    for i in range(start_idx, len(lines)):
        if "continue" in lines[i]:
            end_idx = i
            break
    
    if end_idx != -1:
        # Ta bort den gamla logiken
        # if last_reading and last_reading.timestamp >= timestamp:
        #    continue
        
        # Vi måste vara försiktiga så vi inte tar bort för mycket eller för lite indentering
        
        new_logic = """                    # Check duplicate/stale
                    last_reading = self.session.query(ParameterReading).filter_by(
                        device_id=device.id,
                        parameter_id=parameter.id
                    ).order_by(desc(ParameterReading.timestamp)).first()

                    # Smart Stale Detection:
                    if last_reading:
                        if timestamp > last_reading.timestamp:
                            pass # New data, proceed
                        elif abs(point['value'] - last_reading.value) > 0.001:
                            # Timestamp is old/same, BUT value changed! API/Firmware bug?
                            # Force log with current time to capture the value change
                            logger.warning(f"Stuck timestamp for {parameter.parameter_id} ({timestamp}) but value changed {last_reading.value}->{point['value']}. Forcing log.")
                            timestamp = datetime.utcnow()
                        else:
                            # Same timestamp, same value. Skip.
                            continue
"""
        # Hitta raderna att ersätta.
        # Vi söker efter "last_reading =" och ersätter till och med "continue"
        
        replace_start = -1
        for i in range(start_idx, len(lines)):
            if "last_reading =" in lines[i]:
                replace_start = i
                break
        
        if replace_start != -1:
            del lines[replace_start:end_idx+1]
            lines.insert(replace_start, new_logic)

with open('data_logger_stale_fix.py', 'w') as f:
    f.writelines(lines)