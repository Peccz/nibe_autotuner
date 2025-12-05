"""
myUplink API Client for data retrieval
"""
from typing import Dict, List, Optional
import requests
from loguru import logger

from integrations.auth import MyUplinkAuth
from core.config import settings

API_BASE_URL = settings.MYUPLINK_API_BASE_URL


class MyUplinkClient:
    """Client for interacting with myUplink API"""

    def __init__(self, auth: Optional[MyUplinkAuth] = None):
        """
        Initialize the client

        Args:
            auth: MyUplinkAuth instance. If None, will create a new one.
        """
        self.auth = auth or MyUplinkAuth()
        self.base_url = API_BASE_URL
        self.session = requests.Session()

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication"""
        access_token = self.auth.get_access_token()
        return {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """
        Make an authenticated request to the API

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON data
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                # Token might be expired, try to refresh
                logger.warning("Access token expired, refreshing...")
                self.auth.refresh_access_token()
                # Retry the request
                headers = self._get_headers()
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs
                )
                response.raise_for_status()
                return response.json()
            else:
                logger.error(f"HTTP error: {e}")
                logger.error(f"Response: {e.response.text}")
                raise

    def get_systems(self) -> List[Dict]:
        """
        Get all systems associated with the account

        Returns:
            List of system dictionaries
        """
        logger.info("Fetching systems...")
        data = self._make_request('GET', '/v2/systems/me')
        systems = data.get('systems', [])
        logger.info(f"Found {len(systems)} system(s)")
        return systems

    def get_system_details(self, system_id: str) -> Dict:
        """
        Get detailed information about a specific system

        Args:
            system_id: System ID

        Returns:
            System details dictionary
        """
        logger.info(f"Fetching details for system {system_id}...")
        return self._make_request('GET', f'/v2/systems/{system_id}')

    def get_devices(self, system_id: str) -> List[Dict]:
        """
        Get all devices for a system

        Args:
            system_id: System ID

        Returns:
            List of device dictionaries
        """
        logger.info(f"Fetching devices for system {system_id}...")
        data = self._make_request('GET', f'/v2/systems/{system_id}/devices')
        devices = data.get('devices', [])
        logger.info(f"Found {len(devices)} device(s)")
        return devices

    def get_device_points(self, device_id: str) -> List[Dict]:
        """
        Get all data points for a device

        Args:
            device_id: Device ID

        Returns:
            List of data point dictionaries
        """
        logger.info(f"Fetching data points for device {device_id}...")
        data = self._make_request('GET', f'/v2/devices/{device_id}/points')
        # API returns a list directly, not a dict with 'points' key
        if isinstance(data, list):
            points = data
        else:
            points = data.get('points', [])
        logger.info(f"Found {len(points)} data point(s)")
        return points

    def get_point_data(self, device_id: str, point_id: str) -> Dict:
        """
        Get specific data point value

        Args:
            device_id: Device ID
            point_id: Point ID (parameter ID)

        Returns:
            Data point dictionary with current value
        """
        logger.info(f"Fetching data for point {point_id} on device {device_id}...")

        # MyUplink API v2 doesn't support individual point GET, so fetch all and filter
        all_points = self.get_device_points(device_id)
        matching_points = [p for p in all_points if str(p.get('parameterId')) == str(point_id)]

        if not matching_points:
            logger.error(f"Point {point_id} not found in device points")
            raise ValueError(f"Point {point_id} not found")

        return matching_points[0]

    def set_point_value(self, device_id: str, point_id: str, value: float) -> Dict:
        """
        Set a data point value (requires WRITESYSTEM permission and Premium Manage subscription)

        Args:
            device_id: Device ID
            point_id: Point ID (parameter ID)
            value: New value to set

        Returns:
            Response dictionary like {"47011": "modified"}
        """
        logger.info(f"Setting point {point_id} on device {device_id} to {value}...")

        # Premium Manage uses PATCH /v2/devices/{device_id}/points with format {parameter_id: value}
        payload = {point_id: value}

        return self._make_request(
            'PATCH',
            f'/v2/devices/{device_id}/points',
            json=payload
        )

    def get_notifications(self, system_id: str) -> List[Dict]:
        """
        Get notifications/alarms for a system

        Args:
            system_id: System ID

        Returns:
            List of notification dictionaries
        """
        logger.info(f"Fetching notifications for system {system_id}...")
        data = self._make_request('GET', f'/v2/systems/{system_id}/notifications')
        notifications = data.get('notifications', [])
        logger.info(f"Found {len(notifications)} notification(s)")
        return notifications


def main():
    """Test the API client"""
    logger.info("Starting myUplink API client test...")

    try:
        # Initialize authentication
        auth = MyUplinkAuth()

        # Load existing tokens or authenticate
        if not auth.load_tokens():
            logger.info("No saved tokens found. Please authenticate first.")
            logger.info("Run: python src/auth.py")
            return

        # Initialize client
        client = MyUplinkClient(auth)

        # Get systems
        systems = client.get_systems()
        if not systems:
            logger.warning("No systems found!")
            return

        # Display system information
        for system in systems:
            system_id = system.get('systemId')
            logger.info(f"\nSystem ID: {system_id}")
            logger.info(f"Name: {system.get('name')}")
            logger.info(f"Country: {system.get('country')}")

            # Get devices for this system
            devices = client.get_devices(system_id)

            for device in devices:
                device_id = device.get('id')
                logger.info(f"\n  Device ID: {device_id}")
                logger.info(f"  Product: {device.get('product', {}).get('name')}")
                logger.info(f"  Serial: {device.get('product', {}).get('serialNumber')}")

                # Get data points
                points = client.get_device_points(device_id)

                # Display first 10 points as examples
                logger.info(f"\n  Sample data points (showing first 10 of {len(points)}):")
                for point in points[:10]:
                    point_id = point.get('parameterId')
                    point_name = point.get('parameterName')
                    value = point.get('value')
                    unit = point.get('parameterUnit', '')

                    logger.info(f"    {point_id}: {point_name} = {value} {unit}")

        logger.info("\nAPI client test completed successfully!")

    except Exception as e:
        logger.error(f"API client test failed: {e}")
        raise


if __name__ == '__main__':
    main()
