import sys
import os
import json
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def main():
    logger.info("Connecting to myUplink API...")
    auth = MyUplinkAuth()
    if not auth.load_tokens():
        logger.error("No tokens found. Authenticate first.")
        return

    client = MyUplinkClient(auth)
    
    # Get system and device
    systems = client.get_systems()
    if not systems:
        logger.error("No systems found")
        return
        
    system_id = systems[0]['systemId']
    devices = client.get_devices(system_id)
    if not devices:
        logger.error("No devices found")
        return
        
    device_id = devices[0]['id']
    logger.info(f"Inspecting Device: {device_id}")

    # Fetch all points
    points = client.get_device_points(device_id)
    
    # Find 40033
    target_id = "40033"
    
    for point in points:
        if str(point['parameterId']) == target_id:
            logger.info(f"FOUND PARAMETER {target_id}:")
            print(json.dumps(point, indent=2))
            return

    logger.warning(f"Parameter {target_id} not found in API response.")

if __name__ == "__main__":
    main()
