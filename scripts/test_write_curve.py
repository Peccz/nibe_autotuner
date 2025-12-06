import sys
import os
import time
# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient
from loguru import logger

def main():
    logger.info("Testing write to curve offset (47011)")
    auth = MyUplinkAuth()
    # auth.load_tokens() # Should be loaded automatically
    client = MyUplinkClient(auth)
    
    systems = client.get_systems()
    if not systems:
        logger.error("No systems found")
        return

    device_id = systems[0]['devices'][0]['id']
    logger.info(f"Using device: {device_id}")
    
    # Read current
    try:
        current = client.get_point_data(device_id, "47011")
        logger.info(f"Current value: {current['value']}")
        
        # Determine new value (toggle between -1 and -2)
        # Assuming current value is float
        curr_val = float(current['value'])
        new_val = -2.0 if curr_val != -2.0 else -1.0
        
        logger.info(f"Attempting to set to: {new_val}")
        
        resp = client.set_point_value(device_id, "47011", new_val)
        logger.info(f"Response: {resp}")
        
        # Wait a bit for propagation?
        logger.info("Waiting 5 seconds...")
        time.sleep(5)
        
        # Read back
        updated = client.get_point_data(device_id, "47011")
        logger.info(f"Value after write: {updated['value']}")
        
        if float(updated['value']) == new_val:
            logger.info("SUCCESS: Value changed!")
        else:
            logger.error("FAILURE: Value did not change.")
            
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
