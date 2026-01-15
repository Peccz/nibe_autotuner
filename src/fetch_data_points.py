"""
Fetch data points from Nibe heat pump
"""
import json
from loguru import logger
from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient

def fetch_all_data_points():
    """Fetch and display all data points from the heat pump"""
    auth = MyUplinkAuth()
    auth.load_tokens()

    client = MyUplinkClient(auth)

    # Get systems
    systems = client.get_systems()

    if not systems:
        logger.error("No systems found!")
        return

    system = systems[0]
    devices = system.get('devices', [])

    if not devices:
        logger.error("No devices found in system!")
        return

    device = devices[0]
    device_id = device.get('id')

    logger.info(f"\n{'='*60}")
    logger.info(f"Fetching data from: {device.get('product', {}).get('name')}")
    logger.info(f"Device ID: {device_id}")
    logger.info(f"{'='*60}\n")

    try:
        # Get all data points
        points = client.get_device_points(device_id)

        logger.info(f"Found {len(points)} data points!\n")

        # Categorize points
        temperatures = []
        statuses = []
        energy = []
        other = []

        for point in points:
            param_id = point.get('parameterId')
            param_name = point.get('parameterName')
            value = point.get('value')
            unit = point.get('parameterUnit', '')
            category = point.get('category', '')

            point_info = {
                'id': param_id,
                'name': param_name,
                'value': value,
                'unit': unit,
                'category': category
            }

            # Categorize by unit or name
            if '°C' in unit or 'temp' in param_name.lower():
                temperatures.append(point_info)
            elif 'kW' in unit or 'A' in unit or 'energy' in param_name.lower():
                energy.append(point_info)
            elif 'status' in param_name.lower() or 'mode' in param_name.lower():
                statuses.append(point_info)
            else:
                other.append(point_info)

        # Display temperatures
        if temperatures:
            logger.info(f"{'='*60}")
            logger.info(f"TEMPERATURES ({len(temperatures)})")
            logger.info(f"{'='*60}")
            for p in temperatures[:20]:  # Show first 20
                logger.info(f"{p['id']:>6} | {p['name']:<40} | {p['value']:>8} {p['unit']}")

        # Display energy/power
        if energy:
            logger.info(f"\n{'='*60}")
            logger.info(f"ENERGY/POWER ({len(energy)})")
            logger.info(f"{'='*60}")
            for p in energy[:20]:  # Show first 20
                logger.info(f"{p['id']:>6} | {p['name']:<40} | {p['value']:>8} {p['unit']}")

        # Display status
        if statuses:
            logger.info(f"\n{'='*60}")
            logger.info(f"STATUS/MODE ({len(statuses)})")
            logger.info(f"{'='*60}")
            for p in statuses[:20]:  # Show first 20
                logger.info(f"{p['id']:>6} | {p['name']:<40} | {p['value']:>8} {p['unit']}")

        # Save all points to JSON file
        output_file = 'data/all_data_points.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(points, f, indent=2, ensure_ascii=False)

        logger.info(f"\n{'='*60}")
        logger.info(f"✓ All {len(points)} data points saved to: {output_file}")
        logger.info(f"{'='*60}")

    except Exception as e:
        logger.error(f"Failed to fetch data points: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    fetch_all_data_points()

