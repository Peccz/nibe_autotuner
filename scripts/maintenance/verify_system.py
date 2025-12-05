#!/usr/bin/env python3
"""System verification script"""
import json
import requests
import sqlite3
from datetime import datetime

print("=" * 60)
print("NIBE AUTOTUNER - SYSTEM VERIFICATION")
print("=" * 60)

# 1. Check token
print("\n✓ TOKENS:")
with open('/home/peccz/.myuplink_tokens.json') as f:
    tokens = json.load(f)
print(f"  Has refresh_token: {'refresh_token' in tokens}")
print(f"  Scope: {tokens.get('scope')}")
print(f"  Expires: {datetime.fromtimestamp(tokens.get('expires_at', 0)).strftime('%Y-%m-%d %H:%M:%S')}")

# 2. Check database
print("\n✓ DATABASE:")
conn = sqlite3.connect('/home/peccz/nibe_autotuner/data/nibe_autotuner.db')
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM parameter_readings")
total = cursor.fetchone()[0]
print(f"  Total readings: {total:,}")

cursor.execute("SELECT datetime(MAX(timestamp), 'localtime') FROM parameter_readings")
latest = cursor.fetchone()[0]
print(f"  Latest reading: {latest}")

cursor.execute("SELECT COUNT(*) FROM parameter_readings WHERE timestamp > datetime('now', '-1 hour')")
last_hour = cursor.fetchone()[0]
print(f"  Readings last hour: {last_hour}")

conn.close()

# 3. Check API
print("\n✓ API:")
try:
    resp = requests.get('http://localhost:8502/api/metrics?hours=1', timeout=5)
    data = resp.json()

    print(f"  Success: {data.get('success')}")
    print(f"  Has heating data: {'heating' in data.get('data', {})}")
    print(f"  Has hot_water data: {'hot_water' in data.get('data', {})}")

    opt_score = data.get('data', {}).get('optimization_score')
    if opt_score:
        print(f"  Optimization score: {opt_score.get('score')}/100 ({opt_score.get('tier')})")

    # Show heating/hot water metrics
    if 'heating' in data.get('data', {}):
        h = data['data']['heating']
        if h.get('cop'):
            print(f"\n  HEATING:")
            print(f"    COP: {h['cop']:.2f} ({h.get('cop_rating', {}).get('tier', 'N/A')})")
            print(f"    Runtime: {h.get('runtime_hours', 0):.1f}h")

    if 'hot_water' in data.get('data', {}):
        hw = data['data']['hot_water']
        if hw.get('cop'):
            print(f"\n  HOT WATER:")
            print(f"    COP: {hw['cop']:.2f} ({hw.get('cop_rating', {}).get('tier', 'N/A')})")
            print(f"    Runtime: {hw.get('runtime_hours', 0):.1f}h")

except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("✓ VERIFICATION COMPLETE")
print("=" * 60)
