import sys
import os
import json
import requests

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from auth import MyUplinkAuth
from models import init_db, Device
from sqlalchemy.orm import sessionmaker

def deep_scan_direct():
    print("Initializing Direct Deep Scan (Bypassing Client)...")
    
    # 1. Auth & Device
    auth = MyUplinkAuth()
    token = auth.get_access_token()
    headers = {'Authorization': f'Bearer {token}'}
    
    engine = init_db('sqlite:///data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()
    
    if not device:
        print("No device found.")
        return

    device_id = device.device_id
    print(f"Target: {device_id}")

    # 2. Get Categories (Direct API Call)
    # Endpoint: /v2/devices/{deviceId}/points/categories
    url = f"https://api.myuplink.com/v2/devices/{device_id}/points/categories"
    
    print(f"Requesting categories from {url}...")
    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        categories = resp.json()
    except Exception as e:
        print(f"Failed to get categories: {e}")
        return

    print(f"Found {len(categories)} categories.")
    
    all_writables = []
    
    # 3. Iterate Categories
    for cat in categories:
        cat_id = cat.get('categoryId')
        cat_name = cat.get('name')
        
        print(f"Scanning Category: {cat_name}...")
        
        # Get Points for Category
        # Endpoint: /v2/devices/{deviceId}/points?categoryId={cat_id}
        # Note: API might use specific endpoints for service info, but let's try standard points
        cat_url = f"https://api.myuplink.com/v2/devices/{device_id}/points?categoryId={cat_id}"
        
        try:
            c_resp = requests.get(cat_url, headers=headers)
            if c_resp.status_code != 200:
                print(f"  Skipping {cat_name} (Status {c_resp.status_code})")
                continue
                
            points = c_resp.json()
            
            # Filter writable
            for p in points:
                # Logic to detect writable parameters for Premium users
                is_writable = False
                
                # Check 1: Explicit flag
                if p.get('writable'): 
                    is_writable = True
                
                # Check 2: Has a range (min/max) or Enums -> Likely a setting
                elif 'minVal' in p and 'maxVal' in p:
                    is_writable = True
                elif 'enumValues' in p and len(p['enumValues']) > 0:
                    is_writable = True
                    
                if is_writable:
                    val = p.get('value')
                    unit = p.get('parameterUnit', '')
                    
                    # Format range
                    if 'minVal' in p:
                        r_str = f"{p['minVal']}..{p['maxVal']}"
                    elif 'enumValues' in p:
                        r_str = f"Enum ({len(p['enumValues'])} opts)"
                    else:
                        r_str = "Unknown"
                        
                    all_writables.append({
                        'id': p['parameterId'],
                        'name': p['parameterName'],
                        'value': val,
                        'unit': unit,
                        'range': r_str,
                        'category': cat_name
                    })
                    
        except Exception as e:
            print(f"  Error scanning category: {e}")

    # 4. Output
    print("\n" + "="*100)
    print(f"PREMIUM MANAGE - WRITABLE PARAMETERS ({len(all_writables)} found)")
    print("="*100)
    print(f"{ 'ID':<10} | {'Value':<8} | {'Range':<15} | {'Unit':<6} | {'Name'}")
    print("-" * 100)
    
    # Sort by ID
    for w in sorted(all_writables, key=lambda x: int(x['id']) if str(x['id']).isdigit() else x['id']):
        name = (w['name'][:50] + '..') if len(w['name']) > 50 else w['name']
        print(f"{w['id']:<10} | {str(w['value']):<8} | {w['range']:<15} | {w['unit']:<6} | {name}")

    # Dump to file for Claude
    with open('premium_params_dump.json', 'w') as f:
        json.dump(all_writables, f, indent=2)
    print(f"\nSaved to premium_params_dump.json")

if __name__ == "__main__":
    deep_scan_direct()
