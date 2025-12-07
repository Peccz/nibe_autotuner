import sys
import os
import json
from datetime import datetime

# Get the absolute path to the project root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
# Add the 'src' directory within the project root to sys.path
sys.path.insert(0, os.path.join(project_root, 'src'))

from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth
from data.database import SessionLocal, init_db
from data.models import Device, Parameter, ParameterChange, AIDecisionLog
from loguru import logger

# Configure logger
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("apply_room_sensor_change.log", level="DEBUG", rotation="1 MB")


def apply_room_sensor_change():
    logger.info("Starting immediate application of Room Sensor Change...")

    # Initialize DB and get device
    init_db()
    session = SessionLocal()
    device = session.query(Device).first()
    
    if not device:
        logger.error("No device found in the database. Cannot apply change.")
        session.close()
        return

    device_id = device.device_id
    PARAMETER_ID = "47394"
    NEW_VALUE = 2.0
    REASON = "Initial scientific test: Activate room sensor influence (factor 2)"

    try:
        # 1. Get current value from API for logging
        auth = MyUplinkAuth()
        client = MyUplinkClient(auth)
        
        current_param_data = client.get_point_data(device_id, PARAMETER_ID)
        current_value = current_param_data.get('value')
        parameter_name = current_param_data.get('parameterName', 'Unknown Parameter')

        logger.info(f"Current value of {parameter_name} ({PARAMETER_ID}) is: {current_value}")
        if current_value == NEW_VALUE:
            logger.info(f"Parameter {PARAMETER_ID} is already set to {NEW_VALUE}. No change needed.")
            session.close()
            return
            
        # 2. Apply the change via API
        logger.info(f"Attempting to set {parameter_name} ({PARAMETER_ID}) to {NEW_VALUE}...")
        api_response = client.set_point_value(device_id, PARAMETER_ID, NEW_VALUE)
        logger.info(f"API Response for setting parameter: {api_response}")

        # 3. Log the change in the local database
        param_obj = session.query(Parameter).filter_by(parameter_id=PARAMETER_ID).first()
        if not param_obj:
            logger.error(f"Parameter {PARAMETER_ID} not found in local DB. Cannot log change.")
            session.close()
            return

        param_change = ParameterChange(
            device_id=device.id,
            parameter_id=param_obj.id,
            timestamp=datetime.utcnow(),
            old_value=current_value,
            new_value=NEW_VALUE,
            reason=REASON,
            applied_by='system_agent',
            recommendation_id=None # This is a direct test, not from a specific recommendation
        )
        session.add(param_change)
        session.flush() # Get ID for AIDecisionLog

        # 4. Log the decision
        ai_decision_log = AIDecisionLog(
            timestamp=datetime.utcnow(),
            action='adjust',
            model_used='GeminiCLI',
            parameter_id=param_obj.id,
            current_value=current_value,
            suggested_value=NEW_VALUE,
            reasoning=REASON,
            confidence=1.0,
            expected_impact='Jämnare innetemperatur via rumsgivare.',
            applied=True,
            parameter_change_id=param_change.id
        )
        session.add(ai_decision_log)
        
        session.commit()
        logger.info(f"Successfully applied and logged change for {parameter_name} ({PARAMETER_ID}).")

    except Exception as e:
        logger.error(f"Failed to apply or log room sensor change: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    apply_room_sensor_change()
