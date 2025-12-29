with open('analyzer_clean_github.py', 'r') as f:
    lines = f.readlines()

# 1. Ersätt get_latest_value med en komplett ny version (för att garantera indentering)
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "def get_latest_value(self, device: Device, parameter_id_str: str) -> Optional[float]:" in line:
        start_idx = i
    if start_idx != -1 and "def " in line and i > start_idx: # Nästa metod
        end_idx = i
        break

if start_idx != -1:
    if end_idx == -1: end_idx = len(lines)
    
    del lines[start_idx:end_idx]
    
    new_method = """    def get_latest_value(self, device: Device, parameter_id_str: str) -> Optional[float]:
        try:
            logger.debug(f"[Analyzer.get_latest_value] Device ID: {device.id}, Param ID Str: '{parameter_id_str}'")
            # Find parameter first
            param = self.session.query(Parameter).filter_by(
                parameter_id=parameter_id_str
            ).first()
            
            if not param:
                logger.warning(f"[Analyzer.get_latest_value] Parameter '{parameter_id_str}' NOT FOUND in self.session!")
                return None
            
            logger.debug(f"[Analyzer.get_latest_value] Found param ORM: {param.id} ('{param.parameter_name}')")

            # Get latest reading
            reading = self.session.query(ParameterReading).filter_by(
                device_id=device.id,
                parameter_id=param.id
            ).order_by(desc(ParameterReading.timestamp)).first()
            
            if reading:
                logger.debug(f"[Analyzer.get_latest_value] Found reading: {reading.value} @ {reading.timestamp}")
                return reading.value
            
            logger.warning(f"[Analyzer.get_latest_value] No reading found for device {device.id} param {param.id}")
            return None
        except Exception as e:
            logger.error(f"[Analyzer.get_latest_value] Error for '{parameter_id_str}': {e}")
            return None

"""
    lines.insert(start_idx, new_method)

# 2. Ta bort fallback
for i, line in enumerate(lines):
    if "if curve_offset is None: curve_offset = 1.0" in line:
        lines[i] = "        # if curve_offset is None: curve_offset = 1.0 # REMOVED FALLBACK\n"
        break

with open('analyzer_final_patch_clean.py', 'w') as f:
    f.writelines(lines)