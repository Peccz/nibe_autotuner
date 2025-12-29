import time
import sys
import os
sys.path.insert(0, os.path.abspath('src'))
from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient
from loguru import logger

def main():
    auth = MyUplinkAuth()
    client = MyUplinkClient(auth)
    
    systems = client.get_systems()
    # Handle list of devices properly
    devices = systems[0].get('devices', [])
    if not devices:
        logger.error("No devices found")
        return
        
    device_id = devices[0]['id']
    
    # 42782: Air velocity BS1
    # 50221: Fan speed exhaust air
    # 50005: Increased ventilation setting
    # 47274: Speed 1 setting (just to check)
    params_to_read = ['42782', '50221', '50005']
    
    def read_status(label):
        points = client.get_device_points(device_id)
        logger.info(f"--- {label} ---")
        for p in points:
            if str(p['parameterId']) in params_to_read:
                print(f"{p['parameterId']} ({p['parameterName']}): {p['value']} {p.get('parameterUnit','')}")

    # 1. Normal (0)
    logger.info("Setting Ventilation to 0 (Normal)...")
    client.set_point_value(device_id, '50005', 0)
    time.sleep(20) # Wait for ramp up/down
    read_status("Mode 0 (Normal)")
    
    # 2. Increased 1 (1)
    logger.info("Setting Ventilation to 1 (Increased 1)...")
    client.set_point_value(device_id, '50005', 1)
    time.sleep(20)
    read_status("Mode 1 (Increased 1)")
    
    # 3. Increased 2 (2)
    logger.info("Setting Ventilation to 2 (Increased 2)...")
    try:
        client.set_point_value(device_id, '50005', 2)
        time.sleep(20)
        read_status("Mode 2 (Increased 2)")
    except Exception as e:
        logger.warning(f"Mode 2 failed: {e}")

    # 4. Increased 3 (3)
    logger.info("Setting Ventilation to 3 (Increased 3)...")
    try:
        client.set_point_value(device_id, '50005', 3)
        time.sleep(20)
        read_status("Mode 3 (Increased 3)")
    except Exception as e:
        logger.warning(f"Mode 3 failed: {e}")

    # Reset
    logger.info("Resetting to 0 (Normal)...")
    client.set_point_value(device_id, '50005', 0)
    time.sleep(5)
    read_status("Final State")

if __name__ == "__main__":
    main()
