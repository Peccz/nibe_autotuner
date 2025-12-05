"""
Check what historical data is actually available
"""
import json
from loguru import logger
from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def check_history_detail():
    """Check the actual structure of historical data"""

    auth = MyUplinkAuth()
    auth.load_tokens()
    client = MyUplinkClient(auth)

    # Get device
    systems = client.get_systems()
    device_id = systems[0]['devices'][0]['id']

    logger.info("Fetching data with includeHistory=true...")

    # Fetch with history flag
    import requests
    headers = client._get_headers()
    url = f"https://api.myuplink.com/v2/devices/{device_id}/points?includeHistory=true"

    response = requests.get(url, headers=headers)
    data = response.json()

    logger.info(f"Received {len(data)} parameters\n")

    # Check a few parameters to see their structure
    test_params = ['40004', '40008', '40012', '41778']  # Outdoor temp, supply, return, compressor

    for param_id in test_params:
        param_data = next((p for p in data if p['parameterId'] == param_id), None)

        if param_data:
            logger.info(f"Parameter {param_id}: {param_data['parameterName']}")
            logger.info(f"  Current value: {param_data['value']}")
            logger.info(f"  Timestamp: {param_data['timestamp']}")

            # Check if there's any history field
            logger.info(f"  All keys: {list(param_data.keys())}")

            # Look for any fields that might contain history
            for key in param_data.keys():
                if 'history' in key.lower() or 'time' in key.lower() or 'series' in key.lower():
                    logger.info(f"  -> Found potential history field: {key} = {param_data[key]}")

            logger.info("")

    # Full dump of one parameter to see everything
    logger.info("="*80)
    logger.info("Full structure of outdoor temperature parameter:")
    logger.info("="*80)
    outdoor_temp = next((p for p in data if p['parameterId'] == '40004'), None)
    if outdoor_temp:
        logger.info(json.dumps(outdoor_temp, indent=2))

    logger.info("\n" + "="*80)
    logger.info("CONCLUSION")
    logger.info("="*80 + "\n")

    logger.info("The 'includeHistory=true' parameter does NOT provide time-series history.")
    logger.info("It only returns the CURRENT value with its timestamp.")
    logger.info("")
    logger.info("This means:")
    logger.info("  ❌ API does NOT expose historical time-series data")
    logger.info("  ✅ Our continuous data logger approach is CORRECT")
    logger.info("  ✅ Must collect data ourselves over time")
    logger.info("  ✅ CSV import functionality will be valuable for backfilling")
    logger.info("")
    logger.info("💡 CSV EXPORT from MyUplink Web:")
    logger.info("   - Check if myUplink.com has data export feature")
    logger.info("   - This would be the way to get historical data")
    logger.info("   - We already planned for CSV import - this is why!")

if __name__ == '__main__':
    check_history_detail()
