import sys
import os
import json
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def main():
    auth = MyUplinkAuth()
    auth.load_tokens()
    client = MyUplinkClient(auth)
    
    systems = client.get_systems()
    system = systems[0]
    # Handle missing devices list gracefully
    devices = system.get('devices', [])
    if not devices:
        logger.error("No devices found in system object")
        return

    device_id = devices[0]['id']
    logger.info(f"Scanning Device: {device_id}")

    points = client.get_device_points(device_id)
    
    writable_count = 0
    for point in points:
        if point.get('writable'):
            writable_count += 1
            print(f"ID: {point['parameterId']} | Name: {point['parameterName']} | Value: {point['value']} | Unit: {point.get('parameterUnit')}")

    logger.info(f"Found {writable_count} writable parameters.")

if __name__ == "__main__":
    main()
