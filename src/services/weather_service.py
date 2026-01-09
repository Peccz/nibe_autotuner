"""
SMHI Weather Service Integration
Provides weather forecasts and historical data for optimization
"""
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from loguru import logger


@dataclass
class WeatherForecast:
    """Weather forecast data point"""
    timestamp: datetime
    temperature: float  # °C
    precipitation: float  # mm/h
    wind_speed: float  # m/s
    wind_direction: int # Degrees (0-360)
    humidity: int  # %
    cloud_cover: int = 8 # Octas (0-8), default cloudy


class SMHIWeatherService:
    """
    SMHI Open Data API integration
    API Docs: https://opendata.smhi.se/apidocs/metfcst/index.html
    """

    BASE_URL = "https://opendata-download-metfcst.smhi.se/api"
    DEFAULT_LAT = 59.5176  # Upplands Väsby
    DEFAULT_LON = 17.9114

    def __init__(self, lat: float = None, lon: float = None):
        self.lat = lat or self.DEFAULT_LAT
        self.lon = lon or self.DEFAULT_LON

    def get_forecast(self, hours_ahead: int = 48) -> List[WeatherForecast]:
        try:
            url = f"{self.BASE_URL}/category/pmp3g/version/2/geotype/point/lon/{self.lon}/lat/{self.lat}/data.json"
            logger.info(f"Fetching weather forecast for lat={self.lat}, lon={self.lon}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            forecasts = []
            cutoff_time = datetime.now(timezone.utc) + timedelta(hours=hours_ahead)

            for time_series in data.get('timeSeries', []):
                timestamp = datetime.fromisoformat(time_series['validTime'].replace('Z', '+00:00'))
                if timestamp > cutoff_time:
                    break

                params = {p['name']: p['values'][0] for p in time_series.get('parameters', [])}
                forecast = WeatherForecast(
                    timestamp=timestamp,
                    temperature=params.get('t', 0.0),
                    precipitation=params.get('pmin', 0.0),
                    wind_speed=params.get('ws', 0.0),
                    wind_direction=int(params.get('wd', 0)),
                    humidity=int(params.get('r', 50)),
                    cloud_cover=int(params.get('tcc_mean', 8))
                )
                forecasts.append(forecast)

            logger.info(f"Retrieved {len(forecasts)} forecast data points")
            return forecasts
        except Exception as e:
            logger.error(f"Failed to fetch weather forecast: {e}")
            return []

    def get_temperature_forecast(self, hours_ahead: int = 48) -> List[Tuple[datetime, float]]:
        forecasts = self.get_forecast(hours_ahead)
        return [(f.timestamp, f.temperature) for f in forecasts]

    def get_average_temperature_forecast(self, hours_ahead: int = 48) -> float:
        temps = self.get_temperature_forecast(hours_ahead)
        if not temps: return None
        return sum(t for _, t in temps) / len(temps)