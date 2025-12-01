"""
SMHI Weather Service Integration
Provides weather forecasts and historical data for optimization
"""
import requests
from datetime import datetime, timedelta
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
    humidity: int  # %


class SMHIWeatherService:
    """
    SMHI Open Data API integration

    API Docs: https://opendata.smhi.se/apidocs/metfcst/index.html
    Free, no API key required!
    """

    BASE_URL = "https://opendata-download-metfcst.smhi.se/api"

    # Default location (can be configured)
    # You should update these to your actual location!
    DEFAULT_LAT = 57.7089  # Example: Gothenburg
    DEFAULT_LON = 11.9746

    def __init__(self, lat: float = None, lon: float = None):
        """
        Initialize weather service

        Args:
            lat: Latitude (default: Gothenburg)
            lon: Longitude (default: Gothenburg)
        """
        self.lat = lat or self.DEFAULT_LAT
        self.lon = lon or self.DEFAULT_LON

    def get_forecast(self, hours_ahead: int = 48) -> List[WeatherForecast]:
        """
        Get weather forecast

        Args:
            hours_ahead: How many hours ahead to forecast (max 240)

        Returns:
            List of WeatherForecast objects
        """
        try:
            # SMHI API endpoint for forecasts
            url = f"{self.BASE_URL}/category/pmp3g/version/2/geotype/point/lon/{self.lon}/lat/{self.lat}/data.json"

            logger.info(f"Fetching weather forecast for lat={self.lat}, lon={self.lon}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            forecasts = []
            cutoff_time = datetime.utcnow() + timedelta(hours=hours_ahead)

            for time_series in data.get('timeSeries', []):
                timestamp = datetime.fromisoformat(time_series['validTime'].replace('Z', '+00:00'))

                if timestamp > cutoff_time:
                    break

                # Extract parameters
                params = {p['name']: p['values'][0] for p in time_series.get('parameters', [])}

                forecast = WeatherForecast(
                    timestamp=timestamp,
                    temperature=params.get('t', 0.0),  # Air temperature
                    precipitation=params.get('pmin', 0.0),  # Min precipitation
                    wind_speed=params.get('ws', 0.0),  # Wind speed
                    humidity=int(params.get('r', 50))  # Relative humidity
                )

                forecasts.append(forecast)

            logger.info(f"Retrieved {len(forecasts)} forecast data points")
            return forecasts

        except Exception as e:
            logger.error(f"Failed to fetch weather forecast: {e}")
            return []

    def get_temperature_forecast(self, hours_ahead: int = 48) -> List[Tuple[datetime, float]]:
        """
        Get simplified temperature forecast

        Returns:
            List of (timestamp, temperature) tuples
        """
        forecasts = self.get_forecast(hours_ahead)
        return [(f.timestamp, f.temperature) for f in forecasts]

    def get_average_temperature_forecast(self, hours_ahead: int = 48) -> float:
        """
        Get average forecasted temperature

        Args:
            hours_ahead: Hours to average over

        Returns:
            Average temperature (°C)
        """
        temps = self.get_temperature_forecast(hours_ahead)
        if not temps:
            return None
        return sum(t for _, t in temps) / len(temps)

    def detect_cold_front(self, hours_ahead: int = 72, temp_drop_threshold: float = 5.0) -> Optional[Dict]:
        """
        Detect incoming cold fronts

        Args:
            hours_ahead: How far ahead to look
            temp_drop_threshold: Minimum temperature drop to detect (°C)

        Returns:
            Dict with cold front info or None
        """
        forecasts = self.get_forecast(hours_ahead)

        if len(forecasts) < 2:
            return None

        max_drop = 0
        drop_time = None
        before_temp = forecasts[0].temperature

        for i in range(1, len(forecasts)):
            current_temp = forecasts[i].temperature
            drop = before_temp - current_temp

            if drop > max_drop:
                max_drop = drop
                drop_time = forecasts[i].timestamp

            before_temp = current_temp

        if max_drop >= temp_drop_threshold:
            return {
                'detected': True,
                'temperature_drop': max_drop,
                'arrival_time': drop_time,
                'hours_until': (drop_time - datetime.now(drop_time.tzinfo)).total_seconds() / 3600
            }

        return None

    def detect_warm_period(self, hours_ahead: int = 72, temp_rise_threshold: float = 5.0) -> Optional[Dict]:
        """
        Detect incoming warm periods

        Args:
            hours_ahead: How far ahead to look
            temp_rise_threshold: Minimum temperature rise to detect (°C)

        Returns:
            Dict with warm period info or None
        """
        forecasts = self.get_forecast(hours_ahead)

        if len(forecasts) < 2:
            return None

        max_rise = 0
        rise_time = None
        before_temp = forecasts[0].temperature

        for i in range(1, len(forecasts)):
            current_temp = forecasts[i].temperature
            rise = current_temp - before_temp

            if rise > max_rise:
                max_rise = rise
                rise_time = forecasts[i].timestamp

            before_temp = current_temp

        if max_rise >= temp_rise_threshold:
            return {
                'detected': True,
                'temperature_rise': max_rise,
                'arrival_time': rise_time,
                'hours_until': (rise_time - datetime.now(rise_time.tzinfo)).total_seconds() / 3600
            }

        return None

    def should_adjust_for_weather(self) -> Dict:
        """
        Analyze forecast and suggest if parameter adjustments are needed

        Returns:
            Dict with recommendations
        """
        cold_front = self.detect_cold_front()
        warm_period = self.detect_warm_period()
        avg_temp_48h = self.get_average_temperature_forecast(48)

        recommendations = {
            'needs_adjustment': False,
            'reason': None,
            'suggested_action': None,
            'urgency': 'none'  # 'none', 'low', 'medium', 'high'
        }

        if cold_front and cold_front['hours_until'] < 24:
            recommendations.update({
                'needs_adjustment': True,
                'reason': f"Kallfront på väg: {cold_front['temperature_drop']:.1f}°C drop om {cold_front['hours_until']:.0f}h",
                'suggested_action': 'increase_heating_curve',
                'urgency': 'high' if cold_front['hours_until'] < 12 else 'medium'
            })
        elif warm_period and warm_period['hours_until'] < 24:
            recommendations.update({
                'needs_adjustment': True,
                'reason': f"Värmevåg på väg: {warm_period['temperature_rise']:.1f}°C ökning om {warm_period['hours_until']:.0f}h",
                'suggested_action': 'decrease_heating_curve',
                'urgency': 'medium'
            })
        elif avg_temp_48h is not None:
            # Compare to current season baseline
            if avg_temp_48h < -5:
                recommendations.update({
                    'needs_adjustment': True,
                    'reason': f"Ihållande kyla väntas: {avg_temp_48h:.1f}°C genomsnitt nästa 48h",
                    'suggested_action': 'ensure_adequate_heating',
                    'urgency': 'low'
                })
            elif avg_temp_48h > 15:
                recommendations.update({
                    'needs_adjustment': True,
                    'reason': f"Ihållande värme väntas: {avg_temp_48h:.1f}°C genomsnitt nästa 48h",
                    'suggested_action': 'reduce_heating',
                    'urgency': 'low'
                })

        return recommendations


def main():
    """Test weather service"""
    # You should update these coordinates to your actual location!
    # Find your coordinates: https://www.google.com/maps (right-click -> coordinates)
    service = SMHIWeatherService(lat=57.7089, lon=11.9746)

    print("=== SMHI Weather Forecast Test ===\n")

    # Get forecast
    forecasts = service.get_forecast(hours_ahead=72)
    print(f"Retrieved {len(forecasts)} forecast points")
    print("\nNext 24 hours:")
    for f in forecasts[:24]:
        print(f"  {f.timestamp.strftime('%Y-%m-%d %H:%M')}: {f.temperature:5.1f}°C, "
              f"Precip: {f.precipitation:.1f}mm/h, Wind: {f.wind_speed:.1f}m/s")

    # Average
    avg_temp = service.get_average_temperature_forecast(48)
    print(f"\nAverage temperature next 48h: {avg_temp:.1f}°C")

    # Detect fronts
    cold_front = service.detect_cold_front()
    if cold_front:
        print(f"\n⚠️  KALLFRONT DETEKTERAD!")
        print(f"   Temperaturdrop: {cold_front['temperature_drop']:.1f}°C")
        print(f"   Ankomst: {cold_front['arrival_time']}")
        print(f"   Om: {cold_front['hours_until']:.0f} timmar")

    warm_period = service.detect_warm_period()
    if warm_period:
        print(f"\n☀️  VÄRMEVÅG DETEKTERAD!")
        print(f"   Temperaturökning: {warm_period['temperature_rise']:.1f}°C")
        print(f"   Ankomst: {warm_period['arrival_time']}")
        print(f"   Om: {warm_period['hours_until']:.0f} timmar")

    # Recommendations
    rec = service.should_adjust_for_weather()
    print(f"\n=== Rekommendationer ===")
    print(f"Behöver justering: {rec['needs_adjustment']}")
    if rec['needs_adjustment']:
        print(f"Anledning: {rec['reason']}")
        print(f"Föreslagen åtgärd: {rec['suggested_action']}")
        print(f"Brådskande: {rec['urgency']}")


if __name__ == '__main__':
    main()
