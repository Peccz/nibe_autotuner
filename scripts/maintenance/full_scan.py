import sys
import os
import json
import requests

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))
from integrations.auth import MyUplinkAuth
from data.database import init_db, SessionLocal
from data.models import Device
from sqlalchemy.orm import sessionmaker
from core.config import settings

def full_scan():
    print("STARTING FULL PARAMETER SCAN...")
    
    # Auth
    try:
        auth = MyUplinkAuth()
        token = auth.get_access_token()
    except Exception as e:
        print(f"Auth failed: {e}")
        return

    headers = {'Authorization': f'Bearer {token}'}
    
    # Database
    init_db()
    session = SessionLocal()
    device = session.query(Device).first()
    
    if not device:
        print("No device found in DB.")
        return
    
    did = device.device_id
    print(f"Scanning Device ID: {did}")

    # Fetch ALL points
    url = f"https://api.myuplink.com/v2/devices/{did}/points"
    print(f"Fetching from: {url}")
    
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            points = resp.json()
            print(f"Successfully fetched {len(points)} data points.")
            
            # Save raw dump
            with open('data/all_params_raw.json', 'w') as f:
                json.dump(points, f, indent=2)
            print("Saved to data/all_params_raw.json")
            
            # Analyze
            analyze_and_list(points)
        else:
            print(f"Failed to fetch: {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"Error: {e}")

def analyze_and_list(points):
    readables = []
    writables = []
    
    for p in points:
        pid = p.get('parameterId')
        name = p.get('parameterName')
        val = p.get('value')
        unit = p.get('parameterUnit', '')
        
        # Check writable
        is_writable = p.get('writable') or p.get('isWritable')
        
        # Some might be writable but false in 'writable' flag?
        # Use ranges as hint
        has_range = 'minVal' in p or 'maxVal' in p
        has_enum = 'enumValues' in p and len(p['enumValues']) > 0
        
        # In myUplink, 'writable' flag is usually accurate for "can be changed via API".
        # But 'smartHomeCategories' might also indicate control.
        
        item = {
            'id': pid,
            'name': name,
            'value': val,
            'unit': unit,
            'min': p.get('minVal'),
            'max': p.get('maxVal'),
            'enums': [e['text'] for e in p.get('enumValues', [])] if 'enumValues' in p else []
        }
        
        if is_writable:
            writables.append(item)
        else:
            readables.append(item)
            
    print("\n" + "="*50)
    print(f"WRITABLE PARAMETERS ({len(writables)})")
    print("="*50)
    for i in writables:
        print(f"{i['id']:<8} {i['name']} (Current: {i['value']} {i['unit']})")

    print("\n" + "="*50)
    print(f"READABLE ONLY ({len(readables)})")
    print("="*50)
    for i in readables:
        print(f"{i['id']:<8} {i['name']} (Current: {i['value']} {i['unit']})")

if __name__ == "__main__":
    full_scan()
