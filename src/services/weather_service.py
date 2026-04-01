"""
Weather Service — Open-Meteo integration
Replaces SMHI pmp3g (discontinued/404 for these coordinates).
Open-Meteo is free, no API key required, covers Scandinavia.
"""
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class WeatherForecast:
    """Weather forecast data point"""
    timestamp: datetime
    temperature: float      # °C
    precipitation: float    # mm/h
    wind_speed: float       # m/s
    wind_direction: int     # Degrees (0-360)
    humidity: int           # %
    cloud_cover: int = 8    # Octas (0-8), default cloudy


class SMHIWeatherService:
    """
    Weather forecast via Open-Meteo API (free, no key needed).
    Class name kept for backwards compatibility.
    API: https://open-meteo.com/en/docs
    """

    OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
    DEFAULT_LAT = 59.5176   # Upplands Väsby
    DEFAULT_LON = 17.9114

    def __init__(self, lat: float = None, lon: float = None):
        self.lat = lat or self.DEFAULT_LAT
        self.lon = lon or self.DEFAULT_LON

    def get_forecast(self, hours_ahead: int = 48) -> List[WeatherForecast]:
        try:
            params = {
                "latitude": self.lat,
                "longitude": self.lon,
                "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,relative_humidity_2m,cloud_cover",
                "forecast_days": 3,
                "timezone": "UTC",
            }
            logger.info(f"Fetching weather forecast (Open-Meteo) for lat={self.lat}, lon={self.lon}")
            response = requests.get(self.OPEN_METEO_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            hourly = data["hourly"]
            times    = hourly["time"]
            temps    = hourly["temperature_2m"]
            precips  = hourly["precipitation"]
            winds    = hourly["wind_speed_10m"]       # km/h
            dirs     = hourly["wind_direction_10m"]
            hums     = hourly["relative_humidity_2m"]
            clouds   = hourly["cloud_cover"]          # %

            cutoff = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)
            forecasts = []

            for i, t in enumerate(times):
                dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
                if dt > cutoff:
                    break
                forecasts.append(WeatherForecast(
                    timestamp=dt,
                    temperature=temps[i],
                    precipitation=precips[i],
                    wind_speed=winds[i] / 3.6,          # km/h → m/s
                    wind_direction=int(dirs[i]),
                    humidity=int(hums[i]),
                    cloud_cover=int(clouds[i] / 12.5),  # % → octas (0-8)
                ))

            logger.info(f"Retrieved {len(forecasts)} forecast points from Open-Meteo")
            return forecasts

        except Exception as e:
            logger.error(f"Failed to fetch weather forecast: {e}")
            return []

    def get_temperature_forecast(self, hours_ahead: int = 48) -> List[Tuple[datetime, float]]:
        forecasts = self.get_forecast(hours_ahead)
        return [(f.timestamp, f.temperature) for f in forecasts]

    def get_average_temperature_forecast(self, hours_ahead: int = 48) -> Optional[float]:
        temps = self.get_temperature_forecast(hours_ahead)
        if not temps:
            return None
        return sum(t for _, t in temps) / len(temps)
