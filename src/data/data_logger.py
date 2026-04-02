"""
Data Logger - Continuously fetch and store heat pump data
"""
import time
from datetime import datetime, timezone, timedelta
from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc

from integrations.auth import MyUplinkAuth
from integrations.api_client import MyUplinkClient
from services.home_assistant_service import HomeAssistantService
from services.weather_service import SMHIWeatherService
from services.cop_model import COPModel
from core.config import settings
from data.models import (
    System,
    Device,
    Parameter,
    ParameterReading,
    PlannedHeatingSchedule,
    PredictionAccuracy,
    HotWaterUsage,
    CalibrationHistory,
)
from data.performance_model import DailyPerformance
from data.database import init_db, get_session


class DataLogger:
    """Continuously logs heat pump data to database"""

    SESSION_REFRESH_ITERATIONS = 12  # Refresh session every 12 iterations (~1h at 5min interval)

    def __init__(self, database_url: str = None):
        init_db()
        self.session = get_session()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)
        self.ha_service = HomeAssistantService()
        self.weather_service = SMHIWeatherService()
        self._last_aggregation_date = None

    def _refresh_session(self):
        """Refresh the database session to prevent stale connections."""
        try:
            self.session.close()
        except Exception:
            pass
        self.session = get_session()
        logger.debug("Database session refreshed")

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

    def investigate_system_mode(self):
        """Analyze readings to determine if pump is doing Heating or Hot Water"""
        try:
            device = self.session.query(Device).first()
            if not device: return

            def get_latest(pid_str):
                p = self.session.query(Parameter).filter_by(parameter_id=pid_str).first()
                if not p: return None
                r = self.session.query(ParameterReading).filter_by(parameter_id=p.id, device_id=device.id).order_by(desc(ParameterReading.timestamp)).first()
                return r.value if r else None

            supply = get_latest('40008')
            hw_top = get_latest('40013')
            comp_freq = get_latest('41778')
            defrost_active = get_latest('43066')

            mode = 0.0  # Off/Idle
            str_mode = "Idle"

            if defrost_active and defrost_active > 0:
                mode = 3.0  # Defrost
                str_mode = "Defrost"
            elif comp_freq and comp_freq > 5:
                if supply and hw_top and supply > (hw_top + 1.0) and supply > 42.0:
                    mode = 2.0  # Hot Water
                    str_mode = "Hot Water"
                else:
                    mode = 1.0  # Space Heating
                    str_mode = "Heating"
            
            param = self.session.query(Parameter).filter_by(parameter_id='VP_SYSTEM_MODE').first()
            if param:
                # Determine previous mode before writing new reading
                prev_reading = self.session.query(ParameterReading).filter_by(
                    parameter_id=param.id, device_id=device.id
                ).order_by(desc(ParameterReading.timestamp)).first()
                prev_mode = prev_reading.value if prev_reading else 0.0

                reading = ParameterReading(
                    device_id=device.id,
                    parameter_id=param.id,
                    timestamp=datetime.utcnow(),
                    value=mode,
                    str_value=str_mode
                )
                self.session.add(reading)

                # --- Hot Water usage tracking ---
                now = datetime.utcnow()
                if mode == 2.0 and prev_mode != 2.0:
                    # HW just started — open a new session
                    hw_event = HotWaterUsage(
                        start_time=now,
                        start_temp=hw_top,
                        weekday=now.weekday(),
                        hour=now.hour
                    )
                    self.session.add(hw_event)
                    logger.info(f"🚿 Hot Water started (top={hw_top}°C)")
                elif mode != 2.0 and prev_mode == 2.0:
                    # HW just ended — close the open session
                    open_hw = self.session.query(HotWaterUsage).filter(
                        HotWaterUsage.end_time.is_(None)
                    ).order_by(desc(HotWaterUsage.start_time)).first()
                    if open_hw:
                        open_hw.end_time = now
                        open_hw.end_temp = hw_top
                        open_hw.temp_drop = round((open_hw.start_temp or 0) - (hw_top or 0), 2)
                        duration = (now - open_hw.start_time).total_seconds() / 60
                        open_hw.duration_minutes = int(duration)
                        logger.info(f"🚿 Hot Water ended ({open_hw.duration_minutes} min, drop={open_hw.temp_drop}°C)")

                self.session.commit()
                logger.info(f"🔍 System Investigation: Pump is in {str_mode} mode")
        except Exception as e:
            logger.error(f"Failed system investigation: {e}")
            self.session.rollback()

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

                    if not parameter: continue

                    api_ts_str = point.get('timestamp')
                    if api_ts_str:
                        try:
                            if api_ts_str.endswith('Z'): api_ts_str = api_ts_str[:-1] + '+00:00'
                            dt = datetime.fromisoformat(api_ts_str)
                            if dt.tzinfo: dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                            timestamp = dt
                        except ValueError: timestamp = datetime.utcnow()
                    else: timestamp = datetime.utcnow()

                    last_reading = self.session.query(ParameterReading).filter_by(
                        device_id=device.id,
                        parameter_id=parameter.id
                    ).order_by(desc(ParameterReading.timestamp)).first()

                    if last_reading and last_reading.timestamp >= timestamp:
                        db_age_seconds = (datetime.utcnow() - last_reading.timestamp).total_seconds()
                        if last_reading.value == point['value']:
                            if db_age_seconds < 3600: continue
                            else: timestamp = datetime.utcnow()
                        else: timestamp = datetime.utcnow()

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
                self.investigate_system_mode() # NEW
            else:
                logger.info("No new data points from MyUplink (all stale)")

            # HA Sensors
            try:
                ha_sensors = self.ha_service.get_all_sensors()
                ha_timestamp = datetime.utcnow()
                device = self.session.query(Device).first()
                if device and any(ha_sensors.values()):
                    ha_logged = 0
                    mapping = {'HA_TEMP_DOWNSTAIRS': ha_sensors.get('downstairs_temp'), 'HA_TEMP_DEXTER': ha_sensors.get('dexter_temp'), 'HA_HUMIDITY_DOWNSTAIRS': ha_sensors.get('downstairs_humidity'), 'HA_HUMIDITY_DEXTER': ha_sensors.get('dexter_humidity')}
                    for p_id, val in mapping.items():
                        if val is not None:
                            parameter = self.session.query(Parameter).filter_by(parameter_id=p_id).first()
                            if parameter:
                                reading = ParameterReading(device_id=device.id, parameter_id=parameter.id, timestamp=ha_timestamp, value=val)
                                self.session.add(reading)
                                ha_logged += 1
                    if ha_logged > 0:
                        self.session.commit()
                        logger.info(f"✓ Logged {ha_logged} high-precision readings from Home Assistant")
            except (ConnectionError, TimeoutError, KeyError, ValueError) as e:
                logger.warning(f"HA sensor fetch failed (will retry next cycle): {e}")
                self.session.rollback()
            except Exception as e:
                logger.error(f"Unexpected error logging HA readings: {e}")
                self.session.rollback()

            # Weather
            try:
                forecasts = self.weather_service.get_forecast(hours_ahead=1)
                if forecasts and device:
                    weather = forecasts[0]
                    w_timestamp = datetime.utcnow()
                    w_logged = 0
                    mapping = {'EXT_WIND_SPEED': weather.wind_speed, 'EXT_WIND_DIRECTION': weather.wind_direction}
                    for p_id, val in mapping.items():
                        parameter = self.session.query(Parameter).filter_by(parameter_id=p_id).first()
                        if parameter:
                            reading = ParameterReading(device_id=device.id, parameter_id=parameter.id, timestamp=w_timestamp, value=float(val))
                            self.session.add(reading)
                            w_logged += 1
                    if w_logged > 0:
                        self.session.commit()
                        logger.info(f"✓ Logged {w_logged} external weather readings")
            except (ConnectionError, TimeoutError, AttributeError) as e:
                logger.warning(f"Weather fetch failed (will retry next cycle): {e}")
                self.session.rollback()
            except Exception as e:
                logger.error(f"Unexpected error logging weather readings: {e}")
                self.session.rollback()

            # Validate optimizer predictions (compare planned vs actual temps)
            self._validate_predictions()

            # Aggregate yesterday's performance once per day
            today = datetime.utcnow().date()
            if self._last_aggregation_date != today:
                yesterday = today - timedelta(days=1)
                self._aggregate_daily_performance(yesterday)
                self._last_aggregation_date = today

            return total_readings
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"API connection error, will retry next cycle: {e}")
            self.session.rollback()
            return 0
        except Exception as e:
            logger.error(f"Error logging readings: {e}")
            self.session.rollback()
            return 0

    def _validate_predictions(self):
        """Compare planned temps from completed hours against actual measurements."""
        try:
            now = datetime.utcnow()
            # Check plan rows that are 1–8h old (enough time for actual readings to exist)
            window_start = now - timedelta(hours=8)
            window_end = now - timedelta(hours=1)

            plans = self.session.query(PlannedHeatingSchedule).filter(
                PlannedHeatingSchedule.timestamp >= window_start,
                PlannedHeatingSchedule.timestamp <= window_end,
                PlannedHeatingSchedule.simulated_indoor_temp.isnot(None)
            ).all()

            if not plans:
                return

            # Get the best indoor sensor (HA first, BT50 fallback)
            indoor_param = None
            for pid in ('HA_TEMP_DOWNSTAIRS', '40033'):
                p = self.session.query(Parameter).filter_by(parameter_id=pid).first()
                if p:
                    indoor_param = p
                    break

            if not indoor_param:
                return

            validated = 0
            for plan in plans:
                # Skip if already validated
                exists = self.session.query(PredictionAccuracy).filter_by(
                    forecast_hour=plan.timestamp
                ).first()
                if exists:
                    continue

                # Find actual reading closest to plan.timestamp (±30 min)
                nearby = self.session.query(ParameterReading).filter(
                    ParameterReading.parameter_id == indoor_param.id,
                    ParameterReading.timestamp >= plan.timestamp - timedelta(minutes=30),
                    ParameterReading.timestamp <= plan.timestamp + timedelta(minutes=30)
                ).all()

                if not nearby:
                    continue

                closest = min(nearby, key=lambda r: abs((r.timestamp - plan.timestamp).total_seconds()))
                error = closest.value - plan.simulated_indoor_temp

                acc = PredictionAccuracy(
                    forecast_hour=plan.timestamp,
                    predicted_indoor=plan.simulated_indoor_temp,
                    actual_indoor=closest.value,
                    error_c=round(error, 3),
                    planned_offset=plan.planned_offset,
                    outdoor_temp=plan.outdoor_temp
                )
                self.session.add(acc)
                validated += 1

            if validated > 0:
                self.session.commit()
                logger.info(f"✓ Validated {validated} prediction(s)")
        except Exception as e:
            logger.error(f"Prediction validation failed: {e}")
            self.session.rollback()

    def _aggregate_daily_performance(self, date):
        """Calculate and store performance metrics for a completed day."""
        try:
            from datetime import date as date_type
            day_start = datetime.combine(date, datetime.min.time())
            day_end = day_start + timedelta(days=1)

            # Check if already done
            existing = self.session.query(DailyPerformance).filter(
                DailyPerformance.date == day_start
            ).first()
            if existing:
                return

            device = self.session.query(Device).first()
            if not device:
                return

            target_temp = float(device.target_indoor_temp_min) if device.target_indoor_temp_min else settings.OPTIMIZER_TARGET_TEMP

            def get_day_readings(pid_str):
                p = self.session.query(Parameter).filter_by(parameter_id=pid_str).first()
                if not p:
                    return []
                return self.session.query(ParameterReading).filter(
                    ParameterReading.parameter_id == p.id,
                    ParameterReading.device_id == device.id,
                    ParameterReading.timestamp >= day_start,
                    ParameterReading.timestamp < day_end
                ).all()

            # Indoor temp — HA sensor preferred
            indoor_readings = get_day_readings('HA_TEMP_DOWNSTAIRS') or get_day_readings('40033')
            if not indoor_readings:
                logger.info(f"No indoor readings for {date}, skipping daily aggregation")
                return

            indoor_vals = [r.value for r in indoor_readings]
            avg_indoor = round(sum(indoor_vals) / len(indoor_vals), 2)
            min_indoor = round(min(indoor_vals), 2)
            max_indoor = round(max(indoor_vals), 2)

            # Outdoor temp
            outdoor_vals = [r.value for r in get_day_readings('40004')]
            avg_outdoor = round(sum(outdoor_vals) / len(outdoor_vals), 2) if outdoor_vals else None

            # COP estimate (supply + return + outdoor)
            avg_cop = None
            supply_vals = [r.value for r in get_day_readings('40008')]
            return_vals = [r.value for r in get_day_readings('40012')]
            if supply_vals and return_vals and outdoor_vals:
                avg_supply = sum(supply_vals) / len(supply_vals)
                avg_return = sum(return_vals) / len(return_vals)
                avg_water = (avg_supply + avg_return) / 2.0
                avg_outdoor_f = sum(outdoor_vals) / len(outdoor_vals)
                cop = COPModel._interpolate_cop(avg_outdoor_f, avg_water)
                if cop:
                    avg_cop = round(cop, 2)

            # Compressor runtime and estimated cost
            comp_readings = get_day_readings('41778')
            actual_kwh = None
            actual_cost_sek = None
            if comp_readings:
                AVG_POWER_KW = 1.5
                INTERVAL_H = 5.0 / 60.0  # 5-minute readings → hours
                on_readings = [r for r in comp_readings if r.value > 5]
                actual_kwh = round(len(on_readings) * INTERVAL_H * AVG_POWER_KW, 2)

                # Match each on-hour to electricity price from plan
                cost = 0.0
                priced = 0
                for r in on_readings:
                    plan_row = self.session.query(PlannedHeatingSchedule).filter(
                        PlannedHeatingSchedule.timestamp <= r.timestamp,
                        PlannedHeatingSchedule.timestamp > r.timestamp - timedelta(hours=1),
                        PlannedHeatingSchedule.electricity_price != 1.0
                    ).order_by(PlannedHeatingSchedule.timestamp.desc()).first()
                    if plan_row:
                        cost += plan_row.electricity_price * INTERVAL_H * AVG_POWER_KW
                        priced += 1
                if priced > 0:
                    actual_cost_sek = round(cost, 2)

            dp = DailyPerformance(
                date=day_start,
                avg_indoor_temp=avg_indoor,
                min_indoor_temp=min_indoor,
                max_indoor_temp=max_indoor,
                target_temp=target_temp,
                avg_outdoor_temp=avg_outdoor,
                avg_cop=avg_cop,
                actual_kwh=actual_kwh,
                actual_cost_sek=actual_cost_sek
            )
            self.session.add(dp)
            self.session.commit()
            logger.info(f"✓ Daily performance aggregated for {date}: "
                        f"indoor={avg_indoor}°C, COP={avg_cop}, cost≈{actual_cost_sek} SEK")

            self._calibrate_thermal_model(day_start)

        except Exception as e:
            logger.error(f"Daily performance aggregation failed for {date}: {e}")
            self.session.rollback()

    def _calibrate_thermal_model(self, day_start: datetime):
        """Nightly calibration of K_LEAK and K_GAIN_FLOOR from prediction_accuracy.

        Uses last 7 days of clean samples (|error_c| < 1.5°C).
        REST hours calibrate K_LEAK; RUN hours calibrate K_GAIN_FLOOR.
        Updates are bounded and use EMA (alpha=0.3) to avoid overreacting to noise.
        Results stored in calibration_history; smart_planner reads the latest row.
        """
        try:
            # Already calibrated today?
            existing = self.session.query(CalibrationHistory).filter(
                CalibrationHistory.date == day_start
            ).first()
            if existing:
                return

            cutoff = day_start - timedelta(days=7)
            rows = self.session.query(PredictionAccuracy).filter(
                PredictionAccuracy.forecast_hour >= cutoff,
                PredictionAccuracy.forecast_hour < day_start,
            ).all()

            # Filter outliers (airing, guests, solar spikes)
            clean = [r for r in rows if r.error_c is not None and abs(r.error_c) < 1.5]
            if len(clean) < 24:
                logger.info(f"Calibration: only {len(clean)} clean samples (need 24), skipping")
                return

            # Get previous calibration as baseline (or config defaults)
            prev = self.session.query(CalibrationHistory).order_by(
                CalibrationHistory.date.desc()
            ).first()
            k_leak  = prev.k_leak       if prev else settings.OPTIMIZER_K_LEAK
            k_gain  = prev.k_gain_floor if prev else settings.K_GAIN_FLOOR

            mae_before = sum(abs(r.error_c) for r in clean) / len(clean)

            # REST hours: calibrate K_LEAK
            # positive bias_rest → house warmer than predicted → K_LEAK too high → reduce
            rest = [r for r in clean if r.planned_offset is not None
                    and r.planned_offset <= settings.OPTIMIZER_REST_THRESHOLD]
            bias_rest = None
            if len(rest) >= 8:
                bias_rest = sum(r.error_c for r in rest) / len(rest)
                if abs(bias_rest) > 0.1:
                    factor = 0.95 if bias_rest > 0 else 1.05
                    k_leak_target = k_leak * factor
                    k_leak = 0.7 * k_leak + 0.3 * k_leak_target
                    k_leak = max(0.001, min(0.010, k_leak))

            # RUN hours: calibrate K_GAIN_FLOOR
            # positive bias_run → house warms faster than predicted → K_GAIN too low → increase
            run = [r for r in clean if r.planned_offset is not None
                   and r.planned_offset > settings.OPTIMIZER_REST_THRESHOLD]
            bias_run = None
            if len(run) >= 8:
                bias_run = sum(r.error_c for r in run) / len(run)
                if abs(bias_run) > 0.1:
                    factor = 1.05 if bias_run > 0 else 0.95
                    k_gain_target = k_gain * factor
                    k_gain = 0.7 * k_gain + 0.3 * k_gain_target
                    k_gain = max(0.05, min(0.30, k_gain))

            cal = CalibrationHistory(
                date=day_start,
                k_leak=round(k_leak, 6),
                k_gain_floor=round(k_gain, 5),
                n_rest=len(rest),
                n_run=len(run),
                bias_rest=round(bias_rest, 3) if bias_rest is not None else None,
                bias_run=round(bias_run, 3) if bias_run is not None else None,
                mae_before=round(mae_before, 3),
            )
            self.session.add(cal)
            self.session.commit()
            logger.info(
                f"✓ Thermal calibration: K_LEAK={k_leak:.5f} (bias_rest={bias_rest}), "
                f"K_GAIN_FLOOR={k_gain:.4f} (bias_run={bias_run}), "
                f"MAE={mae_before:.2f}°C from {len(clean)} samples"
            )
        except Exception as e:
            logger.error(f"Thermal calibration failed: {e}")
            self.session.rollback()

    def run_continuous(self, interval_seconds=300):
        logger.info(f"Starting continuous data logging (interval: {interval_seconds}s)")
        iteration = 0
        try:
            while True:
                iteration += 1
                logger.info(f"[Iteration {iteration}]")
                if iteration % self.SESSION_REFRESH_ITERATIONS == 0:
                    self._refresh_session()
                self.log_reading()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Stopping data logger...")

    def get_stats(self):
        return {
            'systems': self.session.query(System).count(),
            'devices': self.session.query(Device).count(),
            'parameters': self.session.query(Parameter).count(),
            'readings': self.session.query(ParameterReading).count(),
        }


def main():
    import sys
    logger.info("NIBE AUTOTUNER - Data Logger")
    logger_service = DataLogger()
    stats = logger_service.get_stats()
    if stats['systems'] == 0: logger_service.initialize_metadata()
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        logger_service.log_reading()
    elif len(sys.argv) > 1 and sys.argv[1] == '--interval':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        logger_service.run_continuous(interval_seconds=interval)
    else:
        logger_service.run_continuous()

if __name__ == '__main__':
    main()
