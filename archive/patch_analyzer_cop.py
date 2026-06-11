with open('temp_analyzer.py', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "def calculate_cost_analysis" in line: # Insert before this method
        insert_idx = i
        break

if insert_idx != -1:
    new_method = """    def get_cop_timeseries(
        self,
        device: Device,
        start_time: datetime,
        end_time: datetime
    ) -> List[Tuple[datetime, float]]:
        """
        Calculate estimated COP over time for plotting.
        Returns a list of (timestamp, cop_value) tuples.
        """
        readings = self.get_readings(device, self.PARAM_SUPPLY_TEMP, start_time, end_time)
        
        cop_data = []
        for supply_ts, supply_temp in readings:
            # Get closest outdoor and return temps
            outdoor_temp = self._find_closest_reading(self.get_readings(device, self.PARAM_OUTDOOR_TEMP, start_time, end_time), supply_ts, timedelta(minutes=5))
            return_temp = self._find_closest_reading(self.get_readings(device, self.PARAM_RETURN_TEMP, start_time, end_time), supply_ts, timedelta(minutes=5))
            
            if outdoor_temp is not None and return_temp is not None:
                cop = self._estimate_cop(outdoor_temp, supply_temp, return_temp)
                if cop is not None:
                    cop_data.append((supply_ts, cop))
        return cop_data
"""
    lines.insert(insert_idx, new_method + "\n")

with open('analyzer_with_cop_timeseries.py', 'w') as f:
    f.writelines(lines)
