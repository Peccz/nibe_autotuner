"""
Home Assistant Integration Service
Fetches high-precision sensor data from Home Assistant API.
"""
import requests
from typing import Dict, Optional, Any
from loguru import logger
from core.config import settings

class HomeAssistantService:
    def __init__(self):
        self.base_url = settings.HA_URL
        self.token = settings.HA_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the full state object for an entity"""
        if not self.base_url or not self.token:
            logger.warning("Home Assistant URL or Token not configured.")
            return None

        url = f"{self.base_url}/api/states/{entity_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch state for {entity_id} from HA: {e}")
            return None

    def get_temperature(self, entity_id: str) -> Optional[float]:
        """Convenience method to get a numeric temperature value"""
        state_data = self.get_state(entity_id)
        if not state_data:
            return None
        
        try:
            state = state_data.get("state")
            if state in (None, "unknown", "unavailable"):
                return None
            return float(state)
        except (ValueError, TypeError):
            logger.error(f"Invalid temperature value from HA for {entity_id}: {state}")
            return None

    def get_all_sensors(self) -> Dict[str, Optional[float]]:
        """Fetch all configured IKEA sensors at once"""
        return {
            "downstairs_temp": self.get_temperature(settings.HA_SENSOR_DOWNSTAIRS),
            "dexter_temp": self.get_temperature(settings.HA_SENSOR_DEXTER),
            "downstairs_humidity": self.get_temperature("sensor.timmerflotte_temp_hmd_sensor_humidity_2"),
            "dexter_humidity": self.get_temperature("sensor.timmerflotte_temp_hmd_sensor_humidity")
        }

if __name__ == "__main__":
    # Quick test
    service = HomeAssistantService()
    print(f"Testing HA Connection to {settings.HA_URL}...")
    sensors = service.get_all_sensors()
    print(f"Sensor Values: {sensors}")
