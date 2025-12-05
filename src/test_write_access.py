"""
Test write access to myUplink API
"""
import time
from loguru import logger
from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def test_write_access():
    """Test writing to a safe parameter"""

    auth = MyUplinkAuth()
    auth.load_tokens()

    client = MyUplinkClient(auth)

    # Get systems and device
    systems = client.get_systems()
    if not systems:
        logger.error("No systems found!")
        return

    system = systems[0]
    devices = system.get('devices', [])

    if not devices:
        logger.error("No devices found!")
        return

    device = devices[0]
    device_id = device.get('id')
    device_name = device.get('product', {}).get('name')

    logger.info(f"\n{'='*80}")
    logger.info(f"Testing Write Access to myUplink API")
    logger.info(f"{'='*80}\n")
    logger.info(f"Device: {device_name}")
    logger.info(f"Device ID: {device_id}\n")

    # Test with a safe parameter: Hot water boost (48132)
    # This is a temporary setting that won't harm the system
    test_param_id = "48132"  # Hot water boost
    test_param_name = "Hot water boost"

    logger.info(f"Test Parameter: {test_param_name} (ID: {test_param_id})")
    logger.info(f"This is a safe, temporary setting for testing.\n")

    try:
        # 1. Read current value
        logger.info("Step 1: Reading current value...")
        current_data = client.get_point_data(device_id, test_param_id)
        current_value = current_data.get('value')
        logger.info(f"  Current value: {current_value} ({current_data.get('strVal')})\n")

        # 2. Try to write a new value
        # Hot water boost values: 0=Off, 1=3hr, 2=6hr, 3=12hr, 4=One-time incr.
        new_value = 4  # One-time increase (safest option)

        logger.info(f"Step 2: Attempting to write new value...")
        logger.info(f"  Setting {test_param_name} to: {new_value} (One-time increase)")

        result = client.set_point_value(device_id, test_param_id, new_value)

        logger.info(f"  ✓ Write successful!")
        logger.info(f"  Response: {result}\n")

        # 3. Wait a moment for the change to propagate
        logger.info("Step 3: Waiting 3 seconds for change to propagate...")
        time.sleep(3)

        # 4. Read back to verify
        logger.info("\nStep 4: Reading value again to verify...")
        new_data = client.get_point_data(device_id, test_param_id)
        new_read_value = new_data.get('value')
        logger.info(f"  New value: {new_read_value} ({new_data.get('strVal')})\n")

        # 5. Restore original value
        logger.info(f"Step 5: Restoring original value ({current_value})...")
        restore_result = client.set_point_value(device_id, test_param_id, current_value)
        logger.info(f"  ✓ Restored!\n")

        # Summary
        logger.info(f"{'='*80}")
        logger.info(f"TEST RESULT SUMMARY")
        logger.info(f"{'='*80}\n")

        if new_read_value == new_value:
            logger.info("✅ WRITE ACCESS CONFIRMED!")
            logger.info("   - Successfully wrote new value")
            logger.info("   - Change was verified")
            logger.info("   - Original value restored\n")
            logger.info("🎉 You have FULL write access to the myUplink API!")
            logger.info("   This means automatic optimization is POSSIBLE!\n")
            return True
        else:
            logger.warning("⚠️  PARTIAL SUCCESS")
            logger.warning(f"   - Write command accepted")
            logger.warning(f"   - But value didn't change as expected")
            logger.warning(f"   - Expected: {new_value}, Got: {new_read_value}\n")
            logger.info("This might mean:")
            logger.info("   - Premium subscription required for writes")
            logger.info("   - Some parameters are read-only despite 'writable' flag")
            logger.info("   - Delayed propagation (try checking later)\n")
            return False

    except Exception as e:
        logger.error(f"\n{'='*80}")
        logger.error(f"❌ WRITE ACCESS FAILED")
        logger.error(f"{'='*80}\n")
        logger.error(f"Error: {e}\n")

        if "403" in str(e):
            logger.error("HTTP 403 Forbidden - This means:")
            logger.error("   - Write access is BLOCKED")
            logger.error("   - May require Premium myUplink subscription")
            logger.error("   - Or this parameter cannot be changed via API\n")
        elif "401" in str(e):
            logger.error("HTTP 401 Unauthorized - This means:")
            logger.error("   - Authentication issue")
            logger.error("   - Token may have expired\n")
        elif "404" in str(e):
            logger.error("HTTP 404 Not Found - This means:")
            logger.error("   - Parameter ID doesn't exist or wrong endpoint\n")

        logger.info("📝 RECOMMENDATION:")
        logger.info("   Since write access failed, the autotuner will need to work in")
        logger.info("   MANUAL MODE where you:")
        logger.info("   1. Apply recommended settings manually")
        logger.info("   2. Report changes back to the app")
        logger.info("   3. App monitors and learns from the effects\n")

        return False

if __name__ == '__main__':
    success = test_write_access()

    if success:
        logger.info("Next steps:")
        logger.info("  - Start logging data continuously")
        logger.info("  - Build optimization algorithms")
        logger.info("  - Test automated parameter adjustments")
    else:
        logger.info("Next steps:")
        logger.info("  - Implement manual mode UI")
        logger.info("  - Build recommendation engine")
        logger.info("  - Create feedback loop for manual changes")
