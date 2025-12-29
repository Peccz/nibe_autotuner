with open('smart_planner_old.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "from services.weather_service import WeatherService" in line:
        lines[i] = "from services.weather_service import SMHIWeatherService\n"
        break

for i, line in enumerate(lines):
    if "self.weather_service = WeatherService()" in line:
        lines[i] = "        self.weather_service = SMHIWeatherService()\n"
        break

with open('smart_planner_fixed.py', 'w') as f:
    f.writelines(lines)
