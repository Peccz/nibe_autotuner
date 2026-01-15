"""
Ventilation Manager 4.0: Adaptive Environment Control
Features: Rapid shower detection, Frost Guard, and Humidity preservation.
"""
from datetime import datetime, timedelta
from loguru import logger
import sqlite3
import os

from core.config import settings
from services.home_assistant_service import HomeAssistantService
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth

class VentilationManager:
    BOOST_THRESHOLD_RH = 60.0
    SHOWER_DERIVATIVE_THRESHOLD = 4.0
    DRY_THRESHOLD = 32.0
    EXTREME_DRY_THRESHOLD = 25.0
    
    SPEED_MIN = 20.0
    SPEED_LOW = 30.0
    SPEED_NORMAL = 50.0
    
    PARAM_NORMAL_SPEED = '47273'
    PARAM_BOOST_SWITCH = '50005'
    PARAM_EVAPORATOR_TEMP = '40020'
    PARAM_COMPRESSOR_HZ = '41778'

    def __init__(self, api_client=None):
        self.ha_service = HomeAssistantService()
        self.auth = MyUplinkAuth()
        self.api_client = api_client or MyUplinkClient(self.auth)
        self.device_id = None

    def _get_device_id(self):
        if not self.device_id:
            systems = self.api_client.get_systems()
            if systems and systems[0]['devices']:
                self.device_id = systems[0]['devices'][0]['id']
        return self.device_id

    def check_and_adjust(self):
        logger.info("Executing Adaptive Ventilation Control (V4.0)...")
        device_id = self._get_device_id()
        if not device_id: return

        sensors = self.ha_service.get_all_sensors()
        rh_down = sensors.get('downstairs_humidity')
        
        if rh_down is None: return

        # Fetch Pump state
        evap_temp = float(self.api_client.get_point_data(device_id, self.PARAM_EVAPORATOR_TEMP).get('value', 0.0))
        comp_hz = float(self.api_client.get_point_data(device_id, self.PARAM_COMPRESSOR_HZ).get('value', 0.0))

        target_speed = self.SPEED_NORMAL
        reason = "Normal operation"

        # 1. Shower Detection (Derivative)
        try:
            db_path = settings.DATABASE_URL.replace('sqlite:///', '')
            if not os.path.isabs(db_path):
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                db_path = os.path.join(project_root, db_path.replace('./', ''))
            
            conn = sqlite3.connect(db_path)
            res_id = conn.execute("SELECT id FROM parameters WHERE parameter_id = 'HA_HUMIDITY_DOWNSTAIRS'").fetchone()
            if res_id:
                p_id = res_id[0]
                res = conn.execute("SELECT value FROM parameter_readings WHERE parameter_id = ? ORDER BY timestamp DESC LIMIT 1", (p_id,)).fetchone()
                if res:
                    last_rh = res[0]
                    derivative = rh_down - last_rh
                    if derivative > self.SHOWER_DERIVATIVE_THRESHOLD:
                        target_speed = 80.0
                        reason = f"Shower detected (RH jump: +{derivative:.1f}%)"
            conn.close()
        except Exception as e:
            logger.error(f"Failed to check shower derivative: {e}")
        
        # 2. Humidity Preservation (If not showering)
        if target_speed < 80.0:
            if rh_down < self.DRY_THRESHOLD:
                target_speed = self.SPEED_LOW
                reason = "Dry air - conserving moisture"
                if rh_down < self.EXTREME_DRY_THRESHOLD:
                    target_speed = self.SPEED_MIN
                    reason = "Extremely dry air - minimum ventilation"

        # 3. Frost Guard Override (Prioritize pump health)
        if comp_hz > 45.0 and target_speed < 45.0:
            target_speed = 45.0
            reason = "Frost Guard: High compressor load override"
        
        if evap_temp < -14.0 and target_speed < 55.0:
            target_speed = 55.0
            reason = "Frost Guard: Critical evaporator temp override"

        # Apply with Memory Guard
        current_speed = float(self.api_client.get_point_data(device_id, self.PARAM_NORMAL_SPEED).get('value', 50.0))
        if abs(target_speed - current_speed) > 1.0:
            logger.warning(f"Adjusting fan to {target_speed}%: {reason}")
            self.api_client.set_point_value(device_id, self.PARAM_NORMAL_SPEED, target_speed)
        else:
            logger.info(f"Ventilation stable at {current_speed}%")

if __name__ == "__main__":
    manager = VentilationManager()
    manager.check_and_adjust()
