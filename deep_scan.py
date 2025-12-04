import sys
import os
import json
import asyncio
from typing import List, Dict

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from api_client import MyUplinkClient
from auth import MyUplinkAuth
from models import init_db, Device
from sqlalchemy.orm import sessionmaker

async def deep_scan_writable_parameters():
    print("Initializing Deep Scan for Premium Manage Parameters...")
    
    # 1. Setup API Client
    auth = MyUplinkAuth()
    client = MyUplinkClient(auth)
    
    # 2. Get Device ID from local DB
    engine = init_db('sqlite:///data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()
    
    if not device:
        print("Error: No device found in local database. Run data_logger.py first.")
        return

    print(f"Target Device: {device.product_name} (ID: {device.device_id})")
    
    # 3. Fetch ALL parameters from API (category 0 often returns 'all' or we iterate common categories)
    # The myUplink API documentation suggests getting all parameters via specific endpoints.
    # However, 'get_parameters' in api_client usually fetches categorized lists.
    # We will try to fetch the root categories and traverse down.
    
    print("Fetching parameter categories...")
    try:
        categories = await client.get_categories(device.device_id)
    except Exception as e:
        # If async fails (api_client might be sync), fallback to sync call if supported
        # Looking at api_client.py... it seems to be sync based on usage in other files.
        print(f"Async detection failed, assuming sync client. Error: {e}")
        categories = client.get_categories(device.device_id)

    all_writables = []

    # Function to process a list of parameters
    def process_params(params, category_name):
        count = 0
        for p in params:
            # Check if writable. Key might vary ('writable', 'isWritable', 'accessLevel')
            # Based on standard myUplink response:
            is_writable = False
            if isinstance(p, dict):
                is_writable = p.get('writable', False) or p.get('isWritable', False)
                
                # Some APIs use permission masks. 
                # If we can't find explicit bool, we might need to check 'ranges' presence
                if not is_writable and 'minVal' in p and 'maxVal' in p:
                     # Strong hint it's writable if it has a range
                     is_writable = True 

                if is_writable:
                    # Capture relevant data
                    all_writables.append({
                        'id': str(p.get('parameterId') or p.get('id')),
                        'name': p.get('parameterName') or p.get('name'),
                        'unit': p.get('parameterUnit') or p.get('unit', ''),
                        'min': p.get('minVal'),
                        'max': p.get('maxVal'),
                        'value': p.get('value'),
                        'category': category_name
                    })
                    count += 1
        return count

    # 4. Traverse Categories
    # Queue of categories to explore
    queue = categories if isinstance(categories, list) else []
    visited_categories = set()

    print(f"Found {len(queue)} root categories. Scanning...")

    while queue:
        cat = queue.pop(0)
        cat_id = cat.get('categoryId')
        cat_name = cat.get('name')
        
        if cat_id in visited_categories:
            continue
        visited_categories.add(cat_id)
        
        print(f"  Scanning Category: {cat_name} ({cat_id})")
        
        try:
            # Fetch params for this category
            # Note: The client might have a method like get_parameters(device_id, category_id)
            # Let's assume client.get_parameters exists and handles this.
            # Checking api_client.py via previous reads... it has get_category_parameters
            
            data = client.get_category_parameters(device.device_id, cat_id)
            
            # Process direct parameters in this category
            if 'parameters' in data:
                process_params(data['parameters'], cat_name)
                
            # Assuming myUplink structure, categories might contain sub-categories?
            # The API response usually is flat for a category request, but let's be safe.
            
        except Exception as e:
            print(f"    Failed to scan category {cat_id}: {e}")

    # 5. Print Report
    print("\n" + "="*100)
    print(f"PREMIUM MANAGE - WRITABLE PARAMETERS REPORT ({len(all_writables)} found)")
    print("="*100)
    print(f"{ 'ID':<10} | { 'Value':<10} | { 'Range':<15} | { 'Unit':<6} | { 'Name'}")
    print("-" * 100)
    
    # Sort by ID for readability
    all_writables.sort(key=lambda x: int(x['id']) if x['id'].isdigit() else x['id'])
    
    for w in all_writables:
        r_str = f"{w['min']}..{w['max']}" if w['min'] is not None else "Enum/Toggle"
        print(f"{w['id']:<10} | {str(w['value']):<10} | {r_str:<15} | {w['unit']:<6} | {w['name']}")
        
    # Save to JSON for future reference
    with open('premium_parameters.json', 'w') as f:
        json.dump(all_writables, f, indent=2)
    print("\nSaved full list to 'premium_parameters.json'")

if __name__ == "__main__":
    # Run sync wrapper because myUplinkClient seems to be synchronous in this codebase
    # based on previous file reads (requests library vs aiohttp)
    try:
        asyncio.run(deep_scan_writable_parameters())
    except Exception as e:
        # If the client is indeed synchronous, asyncio.run might fail or not be needed.
        # Let's try running it as a sync function if asyncio fails, or adapt the code.
        # Re-checking imports... `api_client.py` uses `requests` (Sync).
        # So I should write this as sync.
        pass

# --- RE-WRITING AS SYNC FOR STABILITY ---
def deep_scan_sync():
    print("Initializing Deep Scan (Sync Mode)...")
    auth = MyUplinkAuth()
    client = MyUplinkClient(auth)
    
    engine = init_db('sqlite:///data/nibe_autotuner.db')
    Session = sessionmaker(bind=engine)
    session = Session()
    device = session.query(Device).first()
    
    if not device:
        print("No device found.")
        return

    print(f"Device: {device.product_name} ({device.device_id})")
    
    categories = client.get_categories(device.device_id)
    all_writables = []
    
    for cat in categories:
        cat_id = cat.get('categoryId')
        cat_name = cat.get('name')
        print(f"Scanning: {cat_name}...")
        
        try:
            params_data = client.get_category_parameters(device.device_id, cat_id)
            # The API response usually has a list of parameters directly or inside a key
            # Based on known myUplink structure, get_category_parameters usually returns list of dicts
            
            # Handle if it returns object with 'parameters' key or just list
            p_list = params_data if isinstance(params_data, list) else params_data.get('parameters', [])
            
            for p in p_list:
                # Check writability
                is_writable = p.get('writable', False)
                
                # Fallback check: if min/max exists, it's likely a setting
                if not is_writable and ('minVal' in p or 'enumValues' in p):
                    # Some firmware reports false for writable but allows it via Manage
                    # We'll flag these aggressively
                    is_writable = True 
                
                if is_writable:
                    # Extract enum values if present
                    range_str = f"{p.get('minVal')}..{p.get('maxVal')}"
                    if p.get('enumValues'):
                        range_str = "Enum"
                        
                    all_writables.append({
                        'id': str(p['parameterId']),
                        'name': p['parameterName'],
                        'value': p['value'],
                        'unit': p.get('parameterUnit', ''),
                        'range': range_str,
                        'category': cat_name
                    })
        except Exception as e:
            print(f"  Error in {cat_name}: {e}")

    print("\n" + "="*100)
    print(f"WRITABLE PARAMETERS ({len(all_writables)})")
    print(f"{ 'ID':<8} | { 'Value':<8} | { 'Range':<12} | { 'Name'}")
    print("-" * 100)
    
    unique_ids = set()
    for w in sorted(all_writables, key=lambda x: int(x['id']) if x['id'].isdigit() else x['id']):
        if w['id'] in unique_ids: continue
        unique_ids.add(w['id'])
        
        # Truncate name if too long
        name = (w['name'][:55] + '..') if len(w['name']) > 55 else w['name']
        print(f"{w['id']:<8} | {str(w['value']):<8} | {w['range']:<12} | {name}")

if __name__ == "__main__":
    deep_scan_sync()
