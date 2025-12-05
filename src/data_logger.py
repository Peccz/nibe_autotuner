"""
Data Logger - Continuously fetch and store heat pump data
"""
import time
from datetime import datetime
from loguru import logger
from sqlalchemy.exc import IntegrityError

from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient
from core.config import settings
from data.models import (get_session, System, Device, Parameter, ParameterReading)
from data.database import init_db


class DataLogger:
    """Continuously logs heat pump data to database"""

    def __init__(self, database_url: str = None):
        """
        Initialize DataLogger

        Args:
            database_url: Database connection URL. If None, uses settings.DATABASE_URL
        """
        db_url = database_url or settings.DATABASE_URL
        self.engine = init_db(db_url)
        self.session = get_session(self.engine)
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)

    def initialize_metadata(self):
        """
        Initialize database with system, device, and parameter metadata
        This should be run once at startup
        """
        logger.info("Initializing metadata...")

        # Get systems from API
        systems_data = self.client.get_systems()

        for sys_data in systems_data:
            # Create or update system
            system = self.session.query(System).filter_by(
                system_id=sys_data['systemId']
            ).first()

            if not system:
                system = System(
                    system_id=sys_data['systemId'],
                    name=sys_data.get('name'),
                    country=sys_data.get('country'),
                    security_level=sys_data.get('securityLevel')
                )
                self.session.add(system)
                logger.info(f"  + Created system: {system.name}")
            else:
                system.updated_at = datetime.utcnow()
                logger.info(f"  ✓ System exists: {system.name}")

            self.session.commit()

            # Process devices
            for dev_data in sys_data.get('devices', []):
                device = self.session.query(Device).filter_by(
                    device_id=dev_data['id']
                ).first()

                if not device:
                    device = Device(
                        device_id=dev_data['id'],
                        system_id=system.id,
                        product_name=dev_data.get('product', {}).get('name'),
                        serial_number=dev_data.get('product', {}).get('serialNumber'),
                        firmware_version=dev_data.get('currentFwVersion'),
                        connection_state=dev_data.get('connectionState')
                    )
                    self.session.add(device)
                    logger.info(f"    + Created device: {device.product_name}")
                else:
                    device.connection_state = dev_data.get('connectionState')
                    device.updated_at = datetime.utcnow()
                    logger.info(f"    ✓ Device exists: {device.product_name}")

                self.session.commit()

                # Get all parameters for this device
                points = self.client.get_device_points(dev_data['id'])

                logger.info(f"    Processing {len(points)} parameters...")

                for point in points:
                    param_id = point['parameterId']

                    parameter = self.session.query(Parameter).filter_by(
                        parameter_id=param_id
                    ).first()

                    if not parameter:
                        parameter = Parameter(
                            parameter_id=param_id,
                            parameter_name=point.get('parameterName'),
                            parameter_unit=point.get('parameterUnit'),
                            category=point.get('category'),
                            writable=point.get('writable', False),
                            min_value=point.get('minValue'),
                            max_value=point.get('maxValue'),
                            step_value=point.get('stepValue')
                        )
                        self.session.add(parameter)

                self.session.commit()
                logger.info(f"    ✓ Parameters synced")

        logger.info("✓ Metadata initialization complete!\n")

    def log_reading(self):
        """
        Fetch current readings from API and store in database
        Returns number of readings stored
        """
        try:
            # Get all devices
            devices = self.session.query(Device).all()

            if not devices:
                logger.warning("No devices found in database. Run initialize_metadata() first.")
                return 0

            total_readings = 0
            timestamp = datetime.utcnow()

            for device in devices:
                # Fetch current data points from API
                points = self.client.get_device_points(device.device_id)

                for point in points:
                    # Find parameter in database
                    parameter = self.session.query(Parameter).filter_by(
                        parameter_id=point['parameterId']
                    ).first()

                    if not parameter:
                        logger.warning(f"Parameter {point['parameterId']} not found in database")
                        continue

                    # Create reading
                    reading = ParameterReading(
                        device_id=device.id,
                        parameter_id=parameter.id,
                        timestamp=timestamp,
                        value=point['value'],
                        str_value=point.get('strVal')
                    )

                    self.session.add(reading)
                    total_readings += 1

                self.session.commit()

            logger.info(f"✓ Logged {total_readings} readings at {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            return total_readings

        except Exception as e:
            logger.error(f"Error logging readings: {e}")
            self.session.rollback()
            return 0

    def run_continuous(self, interval_seconds=300):
        """
        Run continuous data logging

        Args:
            interval_seconds: Time between readings (default 300 = 5 minutes)
        """
        logger.info(f"Starting continuous data logging (interval: {interval_seconds}s)")
        logger.info(f"Press Ctrl+C to stop\n")

        iteration = 0

        try:
            while True:
                iteration += 1
                logger.info(f"[Iteration {iteration}]")

                count = self.log_reading()

                if count > 0:
                    logger.info(f"  Sleeping for {interval_seconds} seconds...\n")
                    time.sleep(interval_seconds)
                else:
                    logger.warning("  No readings logged, retrying in 60 seconds...\n")
                    time.sleep(60)

        except KeyboardInterrupt:
            logger.info("\n\nStopping data logger...")
            logger.info("✓ Data logger stopped gracefully")

    def get_stats(self):
        """Get database statistics"""
        stats = {
            'systems': self.session.query(System).count(),
            'devices': self.session.query(Device).count(),
            'parameters': self.session.query(Parameter).count(),
            'readings': self.session.query(ParameterReading).count(),
        }

        # Get first and last reading timestamps
        first_reading = self.session.query(ParameterReading).order_by(
            ParameterReading.timestamp
        ).first()

        last_reading = self.session.query(ParameterReading).order_by(
            ParameterReading.timestamp.desc()
        ).first()

        if first_reading:
            stats['first_reading'] = first_reading.timestamp
        if last_reading:
            stats['last_reading'] = last_reading.timestamp

        return stats


def main():
    """Main entry point"""
    import sys

    logger.info("="*80)
    logger.info("NIBE AUTOTUNER - Data Logger")
    logger.info("="*80 + "\n")

    # Initialize logger
    logger_service = DataLogger()

    # Check if we need to initialize
    stats = logger_service.get_stats()

    if stats['systems'] == 0:
        logger.info("No metadata found. Initializing...")
        logger_service.initialize_metadata()
        stats = logger_service.get_stats()

    # Show stats
    logger.info("Current database status:")
    logger.info(f"  Systems: {stats['systems']}")
    logger.info(f"  Devices: {stats['devices']}")
    logger.info(f"  Parameters: {stats['parameters']}")
    logger.info(f"  Readings: {stats['readings']:,}")

    if stats.get('first_reading'):
        logger.info(f"  First reading: {stats['first_reading']}")
    if stats.get('last_reading'):
        logger.info(f"  Last reading: {stats['last_reading']}")

    logger.info("")

    # Ask user what to do
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        logger.info("Running single data collection...")
        logger_service.log_reading()
    elif len(sys.argv) > 1 and sys.argv[1] == '--interval':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        logger_service.run_continuous(interval_seconds=interval)
    else:
        logger.info("Usage:")
        logger.info("  python src/data_logger.py --once              # Single reading")
        logger.info("  python src/data_logger.py --interval 300      # Continuous (5 min)")
        logger.info("  python src/data_logger.py --interval 60       # Continuous (1 min)")


if __name__ == '__main__':
    main()
