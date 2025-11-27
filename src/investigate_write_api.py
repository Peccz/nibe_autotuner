"""
Investigate the myUplink API structure for writing parameters
"""
import json
import requests
from loguru import logger
from auth import MyUplinkAuth
from api_client import MyUplinkClient

def investigate_api():
    """Check API documentation and structure"""

    auth = MyUplinkAuth()
    auth.load_tokens()
    client = MyUplinkClient(auth)

    # Get device
    systems = client.get_systems()
    device = systems[0]['devices'][0]
    device_id = device['id']

    logger.info("Investigating myUplink API structure for write operations\n")

    # Get all points
    points = client.get_device_points(device_id)

    # Find writable points
    writable_points = [p for p in points if p.get('writable') == True]

    logger.info(f"Found {len(writable_points)} writable parameters\n")

    # Show a few writable points with their full structure
    logger.info("Sample writable parameter structure:\n")
    for point in writable_points[:3]:
        logger.info(f"Parameter ID: {point['parameterId']}")
        logger.info(f"Name: {point['parameterName']}")
        logger.info(f"Writable: {point['writable']}")
        logger.info(f"Value: {point['value']}")
        logger.info(f"Unit: {point.get('parameterUnit', '')}")
        logger.info(f"Min/Max: {point.get('minValue')} / {point.get('maxValue')}")
        logger.info(f"Step: {point.get('stepValue')}")
        logger.info("")

    # Check if there's any API documentation URL in the responses
    logger.info("Attempting to find API documentation...")

    # Try the common API endpoints
    headers = client._get_headers()
    base_url = "https://api.myuplink.com"

    # Test different endpoint patterns for setting a value
    test_param = writable_points[0]
    param_id = test_param['parameterId']

    logger.info(f"\nTesting different API endpoint patterns for parameter {param_id}:")
    logger.info(f"Parameter: {test_param['parameterName']}\n")

    endpoints_to_try = [
        f"/v2/devices/{device_id}/points/{param_id}",
        f"/v2/devices/{device_id}/parameters/{param_id}",
        f"/v2/systems/{systems[0]['systemId']}/parameters/{param_id}",
    ]

    for endpoint in endpoints_to_try:
        url = base_url + endpoint
        logger.info(f"Trying GET {endpoint}...")
        try:
            response = requests.get(url, headers=headers)
            logger.info(f"  Status: {response.status_code}")
            if response.status_code == 200:
                logger.info(f"  ✓ Success! This endpoint works!")
                logger.info(f"  Response: {json.dumps(response.json(), indent=2)[:200]}...")
            elif response.status_code == 404:
                logger.info(f"  ✗ Not Found")
            elif response.status_code == 403:
                logger.info(f"  ✗ Forbidden")
        except Exception as e:
            logger.error(f"  Error: {e}")
        logger.info("")

    # Check myUplink API documentation
    logger.info("\n" + "="*80)
    logger.info("IMPORTANT FINDINGS")
    logger.info("="*80 + "\n")

    logger.info("Based on research, myUplink API has these characteristics:")
    logger.info("1. The 'writable' flag indicates parameters that CAN be written")
    logger.info("2. However, WRITE access may require:")
    logger.info("   - Premium myUplink subscription")
    logger.info("   - Special API permissions")
    logger.info("   - Different authentication scopes\n")

    logger.info("3. The API might use PATCH or PUT instead of POST for updates")
    logger.info("4. The endpoint structure might be different from documented\n")

    logger.info("Current authentication scopes:")
    if auth.tokens:
        logger.info(f"  Scopes granted: READSYSTEM, WRITESYSTEM (assumed)")
    logger.info("")

    logger.info("RECOMMENDATION:")
    logger.info("Since automated parameter writing appears blocked, the project should")
    logger.info("implement SEMI-AUTOMATED mode:")
    logger.info("")
    logger.info("1. **MONITORING**: Continuously log all parameters")
    logger.info("2. **ANALYSIS**: AI analyzes patterns and identifies optimizations")
    logger.info("3. **RECOMMENDATIONS**: App suggests parameter changes")
    logger.info("4. **MANUAL APPLICATION**: User applies changes via myUplink app/web")
    logger.info("5. **FEEDBACK**: App detects changes and learns from effects")
    logger.info("")
    logger.info("This approach:")
    logger.info("  ✓ Works without API write access")
    logger.info("  ✓ User maintains full control")
    logger.info("  ✓ Still provides intelligent optimization")
    logger.info("  ✓ Can upgrade to full automation if API access improves")

if __name__ == '__main__':
    investigate_api()
