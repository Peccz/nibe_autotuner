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
    
    systems = client.get_systems()
    system = systems[0]
    devices = system.get('devices', [])
    device_id = devices[0]['id']
    
    points = client.get_device_points(device_id)
    
    targets = ["40033", "40004", "40013"] # Inne, Ute, Varmvatten
    
    for point in points:
        pid = str(point['parameterId'])
        if pid in targets:
            logger.info(f"PARAMETER {pid} ({point.get('parameterName')}):")
            print(json.dumps({
                'value': point.get('value'),
                'timestamp': point.get('timestamp')
            }, indent=2))

if __name__ == "__main__":
    main()
