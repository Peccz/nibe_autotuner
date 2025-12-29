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
    client = MyUplinkClient(auth)
    
    systems = client.get_systems()
    system = systems[0]
    devices = system.get('devices', [])
    device_id = devices[0]['id']
    
    points = client.get_device_points(device_id)
    
    print(f"Found {len(points)} points.")
    for p in points:
        name = p.get('parameterName', '').lower()
        pid = p.get('parameterId')
        val = p.get('value')
        
        # Filter for interesting params
        if 'degree' in name or 'grad' in name or pid in ['40009', '40940', '40033']:
            print(f"ID: {pid} | Name: {p.get('parameterName')} | Value: {val} | Writable: {p.get('writable')}")

if __name__ == "__main__":
    main()
