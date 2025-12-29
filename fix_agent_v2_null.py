with open('agent_v2_to_fix_null.py', 'r') as f:
    lines = f.readlines()

# Hitta _log_decision
start_idx = -1
for i, line in enumerate(lines):
    if "def _log_decision(self, decision: AIDecision, applied: bool):" in line:
        start_idx = i
        break

if start_idx != -1:
    # Hitta där log_entry skapas
    insert_idx = -1
    for i in range(start_idx, len(lines)):
        if "log_entry = AIDecisionLog(" in line: # Finns inte exakt så, det är uppdelat
            pass
        if "hot_water_demand=decision.hot_water_demand" in lines[i]:
            insert_idx = i
            break
    
    if insert_idx != -1:
        # Infoga logik FÖRE log_entry skapas
        # Vi måste backa upp till "log_entry ="
        log_entry_idx = -1
        for i in range(insert_idx, start_idx, -1):
            if "log_entry = AIDecisionLog(" in lines[i]:
                log_entry_idx = i
                break
        
        if log_entry_idx != -1:
            # Infoga logik
            code = "        # Resolve HW demand for logging (if not set by AI)\n        hw_val = decision.hot_water_demand\n        if hw_val is None:\n            try:\n                from data.models import Device
                device = self.db.query(Device).filter(Device.device_id == self.device_id).first()
                if device:
                    # 47041 = Hot water demand
                    hw_val = self.analyzer.get_latest_value(device, '47041')
            except Exception:
                pass\n\n"
            lines.insert(log_entry_idx, code)
            
            # Uppdatera själva anropet
            # hot_water_demand=decision.hot_water_demand if ...
            # Ersätt med: hot_water_demand=int(hw_val) if hw_val is not None else None
            
            # Vi måste hitta raden igen eftersom indexen förskjutits
            for j in range(log_entry_idx + len(code.splitlines()), len(lines)):
                if "hot_water_demand=" in lines[j]:
                    lines[j] = "            hot_water_demand=int(hw_val) if hw_val is not None else None\n"
                    break

with open('agent_v2_hw_fixed.py', 'w') as f:
    f.writelines(lines)
