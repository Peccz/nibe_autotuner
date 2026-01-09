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
from services.home_assistant_service import HomeAssistantService
from services.weather_service import SMHIWeatherService
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
        self.ha_service = HomeAssistantService()
        self.weather_service = SMHIWeatherService()

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
                # Fetch data points from API
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
                    last_reading = self.session.query(ParameterReading).filter_by(
                        device_id=device.id,
                        parameter_id=parameter.id
                    ).order_by(desc(ParameterReading.timestamp)).first()

                    # QM IMPROVEMENT: Robust handling of stuck Nibe timestamps
                    if last_reading and last_reading.timestamp >= timestamp:
                        # Calculate age of the last record in our DB
                        db_age_seconds = (datetime.utcnow() - last_reading.timestamp).total_seconds()
                        
                        if last_reading.value == point['value']:
                            # Value is same. Should we force a heartbeat log anyway?
                            if db_age_seconds < 3600: # 1 hour heartbeat
                                # Truly stale and recently logged - skip
                                continue
                            else:
                                # Force heartbeat log to show system is alive
                                logger.info(f"Heartbeat log for {parameter.parameter_id} (Value {point['value']} unchanged for 1h)")
                                timestamp = datetime.utcnow()
                        else:
                            # Stuck timestamp but value CHANGED! 
                            # We use current time to capture the change and avoid data loss.
                            logger.info(f"Stuck timestamp for {parameter.parameter_id} ({timestamp}) but value changed {last_reading.value}->{point['value']}. Forcing log.")
                            timestamp = datetime.utcnow()

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
                logger.info(f"✓ Logged {total_readings} new readings from MyUplink")
            else:
                logger.info("No new data points from MyUplink (all stale)")

            # QM ADDITION: Log Home Assistant Sensors (High Precision)
            try:
                ha_sensors = self.ha_service.get_all_sensors()
                ha_timestamp = datetime.utcnow()
                
                # Fetch device for mapping (we use the first available device as anchor)
                device = self.session.query(Device).first()
                
                if device and any(ha_sensors.values()):
                    ha_logged = 0
                    mapping = {
                        'HA_TEMP_DOWNSTAIRS': ha_sensors.get('downstairs_temp'),
                        'HA_TEMP_DEXTER': ha_sensors.get('dexter_temp'),
                        'HA_HUMIDITY_DOWNSTAIRS': ha_sensors.get('downstairs_humidity'),
                        'HA_HUMIDITY_DEXTER': ha_sensors.get('dexter_humidity')
                    }
                    
                    for p_id, val in mapping.items():
                        if val is not None:
                            parameter = self.session.query(Parameter).filter_by(parameter_id=p_id).first()
                            if parameter:
                                reading = ParameterReading(
                                    device_id=device.id,
                                    parameter_id=parameter.id,
                                    timestamp=ha_timestamp,
                                    value=val
                                )
                                self.session.add(reading)
                                ha_logged += 1
                    
                    if ha_logged > 0:
                        self.session.commit()
                        logger.info(f"✓ Logged {ha_logged} high-precision readings from Home Assistant")
            except Exception as e:
                logger.error(f"Error logging HA readings: {e}")
                self.session.rollback()

            # QM ADDITION: Log External Weather Data (For Physics Learning)
            try:
                forecasts = self.weather_service.get_forecast(hours_ahead=1)
                if forecasts and device:
                    weather = forecasts[0]
                    w_timestamp = datetime.utcnow()
                    w_logged = 0
                    
                    mapping = {
                        'EXT_WIND_SPEED': weather.wind_speed,
                        'EXT_WIND_DIRECTION': weather.wind_direction
                    }
                    
                    for p_id, val in mapping.items():
                        parameter = self.session.query(Parameter).filter_by(parameter_id=p_id).first()
                        if parameter:
                            reading = ParameterReading(
                                device_id=device.id,
                                parameter_id=parameter.id,
                                timestamp=w_timestamp,
                                value=float(val)
                            )
                            self.session.add(reading)
                            w_logged += 1
                    
                    if w_logged > 0:
                        self.session.commit()
                        logger.info(f"✓ Logged {w_logged} external weather readings")
            except Exception as e:
                logger.error(f"Error logging weather readings: {e}")
                self.session.rollback()
                
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
    logger.info("NIBE AUTOTUNER - Data Logger (QM Optimized)")
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