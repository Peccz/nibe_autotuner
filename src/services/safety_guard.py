from typing import Optional, Tuple
from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy import desc
from data.models import Device, ParameterReading
from api.schemas import AIDecisionSchema

class SafetyGuard:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.INDOOR_TEMP_PARAM_ID = '13'
        self.ABSOLUTE_MIN_TEMP_HARD_LIMIT = 5.0 # Degrees C, to prevent pipes from freezing

    def validate_decision(self, decision: AIDecisionSchema, device_id: str) -> Tuple[bool, str, Optional[float]]:
        # 1. Hämta inställt gränsvärde
        device = self.db.query(Device).filter(Device.device_id == device_id).first()
        if not device:
            return False, "Device not found", None
        
        # Override user setting if it's below absolute hard limit
        if user_min_temp < self.ABSOLUTE_MIN_TEMP_HARD_LIMIT:
            user_min_temp = self.ABSOLUTE_MIN_TEMP_HARD_LIMIT
            logger.warning(f"SafetyGuard: User min temp ({device.min_indoor_temp_user_setting}) overridden to hard limit ({self.ABSOLUTE_MIN_TEMP_HARD_LIMIT}) for device {device_id}")
        user_min_temp = device.min_indoor_temp_user_setting

        # 2. Hämta FAKTISK innetemperatur
        # Vi letar efter '13' (sträng) eller 13 (int) beroende på hur DB sparar det
        latest_reading = self.db.query(ParameterReading)\
            .filter(ParameterReading.parameter_id == self.INDOOR_TEMP_PARAM_ID)\
            .order_by(desc(ParameterReading.timestamp))\
            .first()

        current_indoor_temp = latest_reading.value if latest_reading else None
        
        if current_indoor_temp is None:
            logger.warning(f"SafetyGuard: Could not read indoor temp (Param {self.INDOOR_TEMP_PARAM_ID})")
            # Om vi inte vet temp, blockera för säkerhets skull om det är en sänkning
            if decision.action == 'adjust' and decision.suggested_value < decision.current_value:
                return False, "Unknown indoor temp - Safety block", None
            return True, "Unknown indoor temp - Proceeding with caution", None

        # --- REGEL 1: Frysskydd ---
        if current_indoor_temp < user_min_temp:
            # Blockera sänkning
            if decision.action == 'adjust' and decision.suggested_value < decision.current_value:
                msg = f"SAFETY BLOCK: Indoor ({current_indoor_temp}) < Limit ({user_min_temp}). Lowering heat FORBIDDEN."
                logger.warning(msg)
                return False, msg, None
            
            # Tvinga höjning vid 'hold'
            if decision.action == 'hold':
                new_val = decision.current_value + 1.0
                msg = f"SAFETY OVERRIDE: Indoor ({current_indoor_temp}) < Limit. Forcing +1 increase."
                logger.warning(msg)
                return True, msg, new_val

        # --- REGEL 2: Gränser ---
        if decision.parameter == "curve_offset":
            MAX_OFFSET = 9.0
            MIN_OFFSET = -9.0
            if decision.suggested_value > MAX_OFFSET:
                return True, f"Capped to max {MAX_OFFSET}", MAX_OFFSET
            if decision.suggested_value < MIN_OFFSET:
                return True, f"Raised to min {MIN_OFFSET}", MIN_OFFSET

        # --- REGEL 3: Dämpning ---
        if decision.parameter == "curve_offset" and decision.current_value is not None:
            diff = decision.suggested_value - decision.current_value
            if abs(diff) > 3.0:
                step = 3.0 if diff > 0 else -3.0
                new_val = decision.current_value + step
                return True, f"Dampened change {diff} to {step}", new_val

        return True, "Decision validates safe", None
