"""
Test if myUplink API provides historical data
"""
import requests
from datetime import datetime, timedelta
from loguru import logger
from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def test_historical_endpoints():
    """Test various endpoints for historical data"""

    auth = MyUplinkAuth()
    auth.load_tokens()
    client = MyUplinkClient(auth)

    # Get system and device info
    systems = client.get_systems()
    system_id = systems[0]['systemId']
    device_id = systems[0]['devices'][0]['id']

    logger.info("="*80)
    logger.info("Testing myUplink API for Historical Data")
    logger.info("="*80 + "\n")

    logger.info(f"System ID: {system_id}")
    logger.info(f"Device ID: {device_id}\n")

    # Common API patterns for historical data
    headers = client._get_headers()
    base_url = "https://api.myuplink.com"

    # Calculate time range (last 24 hours)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=24)

    # Format timestamps (try different formats)
    timestamps = {
        'iso8601': {
            'start': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'end': end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        },
        'unix': {
            'start': int(start_time.timestamp()),
            'end': int(end_time.timestamp())
        }
    }

    # Test parameter
    test_param = "40004"  # Outdoor temperature

    logger.info(f"Testing with parameter: {test_param} (Outdoor temperature)")
    logger.info(f"Time range: {start_time} to {end_time}\n")

    # List of endpoint patterns to try
    endpoints_to_test = [
        # Pattern 1: Points with time range
        f"/v2/devices/{device_id}/points/{test_param}?startTime={timestamps['iso8601']['start']}&endTime={timestamps['iso8601']['end']}",

        # Pattern 2: Historical endpoint
        f"/v2/devices/{device_id}/points/{test_param}/history?startTime={timestamps['iso8601']['start']}&endTime={timestamps['iso8601']['end']}",

        # Pattern 3: Data endpoint
        f"/v2/devices/{device_id}/data?parameterId={test_param}&startTime={timestamps['iso8601']['start']}&endTime={timestamps['iso8601']['end']}",

        # Pattern 4: System-level
        f"/v2/systems/{system_id}/data?parameterId={test_param}&startTime={timestamps['iso8601']['start']}&endTime={timestamps['iso8601']['end']}",

        # Pattern 5: Measurements
        f"/v2/devices/{device_id}/measurements/{test_param}?from={timestamps['iso8601']['start']}&to={timestamps['iso8601']['end']}",

        # Pattern 6: Time series
        f"/v2/devices/{device_id}/points/{test_param}/timeseries?start={timestamps['unix']['start']}&end={timestamps['unix']['end']}",

        # Pattern 7: Simple history
        f"/v2/devices/{device_id}/history?parameterId={test_param}",

        # Pattern 8: Points list with history
        f"/v2/devices/{device_id}/points?includeHistory=true",
    ]

    successful_endpoints = []

    for i, endpoint in enumerate(endpoints_to_test, 1):
        logger.info(f"[{i}/{len(endpoints_to_test)}] Testing: {endpoint[:100]}...")

        try:
            response = requests.get(base_url + endpoint, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                logger.info(f"  ✅ SUCCESS! Status: {response.status_code}")
                logger.info(f"  Response type: {type(data)}")

                if isinstance(data, list):
                    logger.info(f"  Data points: {len(data)}")
                    if len(data) > 0:
                        logger.info(f"  First item keys: {list(data[0].keys())}")
                        logger.info(f"  Sample: {str(data[0])[:200]}...")
                elif isinstance(data, dict):
                    logger.info(f"  Keys: {list(data.keys())}")
                    logger.info(f"  Sample: {str(data)[:200]}...")

                successful_endpoints.append(endpoint)
                logger.info("")

            elif response.status_code == 404:
                logger.info(f"  ❌ 404 Not Found")
            elif response.status_code == 403:
                logger.info(f"  ❌ 403 Forbidden")
            elif response.status_code == 400:
                logger.info(f"  ❌ 400 Bad Request: {response.text[:100]}")
            else:
                logger.info(f"  ❌ Status: {response.status_code}")

        except Exception as e:
            logger.error(f"  ❌ Error: {e}")

        logger.info("")

    # Summary
    logger.info("="*80)
    logger.info("SUMMARY")
    logger.info("="*80 + "\n")

    if successful_endpoints:
        logger.info(f"✅ Found {len(successful_endpoints)} working endpoint(s) for historical data!")
        for endpoint in successful_endpoints:
            logger.info(f"  - {endpoint}")
        logger.info("")
        logger.info("🎉 GOOD NEWS: Historical data IS available!")
        logger.info("   You can fetch historical data instead of continuous logging.")
        logger.info("   This means:")
        logger.info("   - No need to run logger 24/7")
        logger.info("   - Can backfill historical data")
        logger.info("   - Fetch on-demand when needed")
        logger.info("   - More flexible architecture")
    else:
        logger.info("❌ No historical data endpoints found.")
        logger.info("")
        logger.info("This means:")
        logger.info("   - API only provides current/real-time data")
        logger.info("   - Must run continuous data logger")
        logger.info("   - Cannot backfill historical data")
        logger.info("   - Current architecture is correct")
        logger.info("")
        logger.info("💡 ALTERNATIVE:")
        logger.info("   Check if myUplink web interface has CSV export functionality")
        logger.info("   You mentioned CSV import as a feature - this would be the way")
        logger.info("   to get historical data.")

if __name__ == '__main__':
    test_historical_endpoints()
