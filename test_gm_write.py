import time
import sys
import os
from loguru import logger

sys.path.insert(0, os.path.abspath('src'))
from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def main():
    auth = MyUplinkAuth()
    client = MyUplinkClient(auth)
    
    systems = client.get_systems()
    devices = systems[0].get('devices', [])
    if not devices:
        logger.error("No devices found")
        return
        
    device_id = devices[0]['id']
    
    # Check current value
    current_gm_value = client.get_point_data(device_id, '40940')['value']
    logger.info(f"Current 40940: {current_gm_value}")
    
    # Test 1: Write +100
    try:
        logger.info("Attempting to write 100 to 40940...")
        client.set_point_value(device_id, '40940', 100)
        time.sleep(5)
        new_val = client.get_point_data(device_id, '40940')['value']
        logger.info(f"After writing 100, 40940 is: {new_val}")
    except Exception as e:
        logger.error(f"Failed to write 100: {e}")
        
    # Test 2: Write -100
    try:
        logger.info("Attempting to write -100 to 40940...")
        client.set_point_value(device_id, '40940', -100)
        time.sleep(5)
        new_val = client.get_point_data(device_id, '40940')['value']
        logger.info(f"After writing -100, 40940 is: {new_val}")
    except Exception as e:
        logger.error(f"Failed to write -100: {e}")

    # Test 3: Write -350 (our safety limit)
    try:
        logger.info("Attempting to write -350 to 40940...")
        client.set_point_value(device_id, '40940', -350)
        time.sleep(5)
        new_val = client.get_point_data(device_id, '40940')['value']
        logger.info(f"After writing -350, 40940 is: {new_val}")
    except Exception as e:
        logger.error(f"Failed to write -350: {e}")

    # Reset (if it works)
    logger.info(f"Resetting 40940 to 0 (Previous: {current_gm_value})...")
    client.set_point_value(device_id, '40940', 0)
    time.sleep(5)
    new_val = client.get_point_data(device_id, '40940')['value']
    logger.info(f"After resetting, 40940 is: {new_val}")

if __name__ == "__main__":
    main()
