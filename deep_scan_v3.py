import sys
import os
import json
import requests

sys.path.insert(0, os.path.abspath('src'))
from auth import MyUplinkAuth
from models import init_db, Device
from sqlalchemy.orm import sessionmaker

def deep_scan_v3():
    print("Deep Scan V3 - Trying alternative endpoints...")
    
    auth = MyUplinkAuth()
    token = auth.get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    
    engine = init_db('sqlite:///data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()
    if not device: return
    
    did = device.device_id
    print(f"Target: {did}")

    # Strategy 1: Get ALL points directly
    # Note: Pagination might be needed?
    url = f"https://api.myuplink.com/v2/devices/{did}/points"
    print(f"Trying direct fetch: {url}")
    
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            points = resp.json()
            print(f"SUCCESS! Got {len(points)} points directly.")
            save_and_print(points)
            return
        else:
            print(f"Failed direct fetch: {resp.status_code}")
    except Exception as e:
        print(f"Error direct fetch: {e}")

    # Strategy 2: Use correct 'v2' endpoint structure?
    # Sometimes it's /v2/devices/{id}/smart-home-categories ? (Just guessing common patterns)
    # Let's try to inspect what endpoints ARE working in your current system.
    # The 'data_logger.py' works. How does IT get data?
    
    print("Fallback: Analyzing how 'data_logger.py' works...")
    # We will try a brute-force list of common parameters to check writability
    # This is less elegant but guaranteed to find SOMETHING.
    
    common_ids = [
        "47011", "47007", "47015", "47206", "50005", "48132", "47394", 
        "47041", "47212", "47209", "47538", "47539"
    ]
    
    # Fetch them individually to check metadata
    print(f"Checking metadata for {len(common_ids)} known control parameters...")
    url = f"https://api.myuplink.com/v2/devices/{did}/points"
    # Often you can pass IDs: ?parameters=1,2,3
    params_str = ",".join(common_ids)
    url_params = f"{url}?parameters={params_str}"
    
    try:
        resp = requests.get(url_params, headers=headers)
        if resp.status_code == 200:
            points = resp.json()
            save_and_print(points)
        else:
            print(f"Failed bulk fetch: {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(e)

def save_and_print(points):
    writables = []
    for p in points:
        # Aggressive writable check
        is_writable = p.get('writable') or p.get('isWritable')
        
        # If undefined, verify if range exists
        if not is_writable and ('minVal' in p or 'enumValues' in p):
            is_writable = True
            
        if is_writable:
            r_str = f"{p.get('minVal')}..{p.get('maxVal')}" if 'minVal' in p else "Enum"
            writables.append({
                'id': p['parameterId'],
                'name': p['parameterName'],
                'value': p['value'],
                'range': r_str,
                'unit': p.get('parameterUnit', '')
            })
            
    print(f"\nFOUND {len(writables)} WRITABLE PARAMETERS:")
    print("-" * 80)
    for w in writables:
        print(f"{w['id']:<8} | {str(w['value']):<8} | {w['range']:<12} | {w['name']}")
        
    with open('premium_params_dump.json', 'w') as f:
        json.dump(writables, f, indent=2)

if __name__ == "__main__":
    deep_scan_v3()
