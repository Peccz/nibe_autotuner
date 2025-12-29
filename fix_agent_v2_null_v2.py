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
            code_lines = [
                "        # Resolve HW demand for logging\n",
                "        hw_val = decision.hot_water_demand\n",
                "        if hw_val is None:\n",
                "            try:\n",
                "                from data.models import Device\n",
                "                device = self.db.query(Device).filter(Device.device_id == self.device_id).first()\n",
                "                if device:\n",
                "                    hw_val = self.analyzer.get_latest_value(device, '47041')\n",
                "            except Exception:\n",
                "                pass\n",
                "\n"
            ]
            
            for k, line in enumerate(code_lines):
                lines.insert(log_entry_idx + k, line)
            
            # Uppdatera själva anropet
            # Vi måste hitta raden igen eftersom indexen förskjutits
            # insert_idx var raden med "hot_water_demand=". Den har flyttats ner med len(code_lines).
            target_idx = insert_idx + len(code_lines)
            
            # Verify we are on the right line (it might have shifted slightly differently if comments exist)
            # Search forward from log_entry_idx
            for j in range(log_entry_idx + len(code_lines), len(lines)):
                if "hot_water_demand=" in lines[j]:
                    lines[j] = "            hot_water_demand=int(hw_val) if hw_val is not None else None\n"
                    break

with open('agent_v2_hw_fixed.py', 'w') as f:
    f.writelines(lines)
