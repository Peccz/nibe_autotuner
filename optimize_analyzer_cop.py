with open('analyzer_slow.py', 'r') as f:
    lines = f.readlines()

# Find the inefficient method
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if "def get_cop_timeseries" in line:
        start_idx = i
    if start_idx != -1 and "def calculate_cost_analysis" in line: # Next method
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    del lines[start_idx:end_idx]
    
    optimized_method = """    def get_cop_timeseries(self, device: Device, start_time: datetime, end_time: datetime) -> List[Tuple[datetime, float]]:
        supply_readings = self.get_readings(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        outdoor_readings = self.get_readings(device, self.PARAM_OUTDOOR_TEMP, start_time, end_time)
        return_readings = self.get_readings(device, self.PARAM_RETURN_TEMP, start_time, end_time)
        
        cop_data = []
        time_tolerance = timedelta(minutes=5)
        
        for supply_ts, supply_temp in supply_readings:
            outdoor_temp = self._find_closest_reading(outdoor_readings, supply_ts, time_tolerance)
            return_temp = self._find_closest_reading(return_readings, supply_ts, time_tolerance)
            
            if outdoor_temp is not None and return_temp is not None:
                cop = self._estimate_cop(outdoor_temp, supply_temp, return_temp)
                if cop is not None:
                    cop_data.append((supply_ts, cop))
        return cop_data

"""
    lines.insert(start_idx, optimized_method)

with open('analyzer_optimized.py', 'w') as f:
    f.writelines(lines)