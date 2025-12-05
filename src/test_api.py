"""
Test script to explore myUplink API endpoints
"""
from loguru import logger
from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def test_system_details():
    """Test fetching detailed system information"""
    auth = MyUplinkAuth()
    auth.load_tokens()

    client = MyUplinkClient(auth)

    # Get systems
    systems = client.get_systems()

    if not systems:
        logger.error("No systems found!")
        return

    system = systems[0]
    system_id = system.get('systemId')

    logger.info(f"\n{'='*60}")
    logger.info(f"System Information")
    logger.info(f"{'='*60}")
    logger.info(f"System ID: {system_id}")
    logger.info(f"Name: {system.get('name')}")
    logger.info(f"Country: {system.get('country')}")

    # Try to get system details
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Fetching System Details...")
        logger.info(f"{'='*60}")
        details = client.get_system_details(system_id)

        logger.info(f"\nSystem Details:")
        for key, value in details.items():
            logger.info(f"  {key}: {value}")

    except Exception as e:
        logger.error(f"Failed to get system details: {e}")

    # Print full system object to see what fields are available
    logger.info(f"\n{'='*60}")
    logger.info(f"Full System Object:")
    logger.info(f"{'='*60}")
    import json
    logger.info(json.dumps(system, indent=2))

if __name__ == '__main__':
    test_system_details()
