"""
Data Logger - Continuously fetch and store heat pump data
"""
import time
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc

from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient
from core.config import settings
from data.models import (
    System,
    Device,
    Parameter,
    ParameterReading
)
from data.database import init_db, get_session


class DataLogger:
    """Continuously logs heat pump data to database"""

    def __init__(self, database_url: str = None):
        init_db()
        self.session = get_session()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)

    def initialize_metadata(self):
        logger.info("Initializing metadata...")
        systems_data = self.client.get_systems()

        for sys_data in systems_data:
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
            devices_list = sys_data.get('devices', [])
            for dev_data in devices_list:
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

                points = self.client.get_device_points(dev_data['id'])
                logger.info(f"    Processing {len(points)} parameters...")

                for point in points:
                    param_id = str(point['parameterId'])
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
        try:
            devices = self.session.query(Device).all()
            if not devices:
                logger.warning("No devices found in database. Run initialize_metadata() first.")
                return 0

            total_readings = 0

            for device in devices:
                points = self.client.get_device_points(device.device_id)

                for point in points:
                    parameter = self.session.query(Parameter).filter_by(
                        parameter_id=str(point['parameterId'])
                    ).first()

                    if not parameter:
                        continue

                    # Parse timestamp from API
                    api_ts_str = point.get('timestamp')
                    if api_ts_str:
                        try:
                            # Handle ISO format
                            if api_ts_str.endswith('Z'):
                                api_ts_str = api_ts_str[:-1] + '+00:00'
                            
                            dt = datetime.fromisoformat(api_ts_str)
                            if dt.tzinfo:
                                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            timestamp = dt
                        except ValueError:
                            timestamp = datetime.utcnow()
                    else:
                        timestamp = datetime.utcnow()

                    # Check duplicate/stale
                    # Check duplicate/stale
                    last_reading = self.session.query(ParameterReading).filter_by(
                        device_id=device.id,
                        parameter_id=parameter.id
                    ).order_by(desc(ParameterReading.timestamp)).first()

                    # Smart Stale Detection:
                    if last_reading:
                        if timestamp > last_reading.timestamp:
                            pass # New data, proceed
                        elif abs(point['value'] - last_reading.value) > 0.001:
                            # Timestamp is old/same, BUT value changed! API/Firmware bug?
                            # Force log with current time to capture the value change
                            logger.warning(f"Stuck timestamp for {parameter.parameter_id} ({timestamp}) but value changed {last_reading.value}->{point['value']}. Forcing log.")
                            timestamp = datetime.utcnow()
                        else:
                            # Same timestamp, same value. Skip.
                            continue

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

            if total_readings > 0:
                logger.info(f"✓ Logged {total_readings} new readings")
            else:
                logger.info("No new data points from API (all stale)")
                
            return total_readings

        except Exception as e:
            logger.error(f"Error logging readings: {e}")
            self.session.rollback()
            return 0

    def run_continuous(self, interval_seconds=300):
        logger.info(f"Starting continuous data logging (interval: {interval_seconds}s)")
        logger.info(f"Press Ctrl+C to stop\n")
        iteration = 0
        try:
            while True:
                iteration += 1
                logger.info(f"[Iteration {iteration}]")
                self.log_reading()
                logger.info(f"  Sleeping for {interval_seconds} seconds...\n")
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("\n\nStopping data logger...")

    def get_stats(self):
        stats = {
            'systems': self.session.query(System).count(),
            'devices': self.session.query(Device).count(),
            'parameters': self.session.query(Parameter).count(),
            'readings': self.session.query(ParameterReading).count(),
        }
        return stats


def main():
    import sys
    logger.info("="*80)
    logger.info("NIBE AUTOTUNER - Data Logger")
    logger.info("="*80 + "\n")

    logger_service = DataLogger()
    stats = logger_service.get_stats()

    if stats['systems'] == 0:
        logger.info("No metadata found. Initializing...")
        logger_service.initialize_metadata()

    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        logger_service.log_reading()
    elif len(sys.argv) > 1 and sys.argv[1] == '--interval':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        logger_service.run_continuous(interval_seconds=interval)
    else:
        logger_service.run_continuous()

if __name__ == '__main__':
    main()
