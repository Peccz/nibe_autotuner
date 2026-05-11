"""
Deterministic Energy Bank V10.1 (HW Awareness)
Manages heat pump operation by simulating Degree Minutes (GM) locally.
Pauses debt accumulation when pump is making Hot Water.
"""
import time
import sys
import os
from datetime import datetime, timedelta, timezone
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from sqlalchemy import desc

from data.database import SessionLocal
from data.models import GMAccount, Device, PlannedHeatingSchedule, Parameter, ParameterReading, GMTransaction
from services.analyzer import HeatPumpAnalyzer
from services.safety_guard import SafetyGuard
from services.outdoor_temperature import effective_outdoor_temp
from services.comfort_profile import comfort_bounds_for_time
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth
from core.config import settings
from api.schemas import AgentAIDecisionSchema

class GMController:
    # Constants
    PARAM_GM_READ = '40941' 
    PARAM_GM_WRITE = '40940' 
    PARAM_SUPPLY_READ = '40008' # BT2
    PARAM_OUTDOOR_READ = '40004' # BT1
    PARAM_INDOOR_READ = '40033' # BT50
    PARAM_SYSTEM_MODE = 'VP_SYSTEM_MODE' # Calculated by DataLogger
    
    # Physical Limits
    MIN_BALANCE = -2000 # Allow deep debt for electric heater
    MAX_BALANCE = 200   # Max heat surplus
    
    # Nibe Settings
    PUMP_START_THRESHOLD = -200 
    EL_HEATER_START_LIMIT = -400 
    CRITICAL_TEMP_LIMIT = 19.0 
    WARM_OVERRIDE_FLOOR_MARGIN = 0.2
    WARM_OVERRIDE_DEXTER_MARGIN = 0.3
    WARM_OVERRIDE_RELEASE_MARGIN = 0.1
    
    SESSION_REFRESH_INTERVAL = 3600  # Refresh DB session every hour

    def __init__(self):
        self._open_session()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)
        self.analyzer = HeatPumpAnalyzer()
        self.last_tick_time = datetime.now(timezone.utc)
        self.last_written_gm = None
        self.last_session_refresh = datetime.now(timezone.utc)
        self._warm_override_active = False
        self._last_sensor_mode = "unknown"
        self._last_floor_temp = None
        self._last_dexter_temp = None
        self._last_comfort_bounds = None

    def _open_session(self):
        self.db = SessionLocal()
        self.safety_guard = SafetyGuard(self.db)

    def _refresh_session_if_needed(self):
        age = (datetime.now(timezone.utc) - self.last_session_refresh).total_seconds()
        if age > self.SESSION_REFRESH_INTERVAL:
            logger.info("Refreshing database session...")
            try:
                self.db.close()
            except Exception:
                pass
            self._open_session()
            self.last_session_refresh = datetime.now(timezone.utc)
            self._cleanup_old_transactions()

    def _cleanup_old_transactions(self):
        """Keep only 90 days of GM transaction history."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).replace(tzinfo=None)
            deleted = self.db.query(GMTransaction).filter(
                GMTransaction.timestamp < cutoff
            ).delete(synchronize_session=False)
            if deleted:
                self.db.commit()
                logger.info(f"Pruned {deleted} old GM transactions (>90 days)")
        except Exception as e:
            logger.warning(f"Transaction cleanup failed: {e}")
            self.db.rollback()

    def _get_account(self):
        account = self.db.query(GMAccount).first()
        if not account:
            account = GMAccount(balance=0.0, mode='NORMAL')
            self.db.add(account)
            self.db.commit()
        return account

    def _get_recent_reading_value(self, parameter_code, now, max_age_minutes=30):
        param = self.db.query(Parameter).filter_by(parameter_id=parameter_code).first()
        if not param:
            return None

        reading = self.db.query(ParameterReading).filter(
            ParameterReading.parameter_id == param.id,
            ParameterReading.timestamp > now.replace(tzinfo=None) - timedelta(minutes=max_age_minutes)
        ).order_by(desc(ParameterReading.timestamp)).first()
        return reading.value if reading else None

    def _get_historical_gap(self, warm_param, base_param, default_gap):
        try:
            warm = self.db.query(Parameter).filter_by(parameter_id=warm_param).first()
            base = self.db.query(Parameter).filter_by(parameter_id=base_param).first()
            if not warm or not base:
                return default_gap

            rows = self.db.query(ParameterReading.value, ParameterReading.timestamp).filter(
                ParameterReading.parameter_id == warm.id,
                ParameterReading.timestamp > datetime.utcnow() - timedelta(days=14)
            ).order_by(desc(ParameterReading.timestamp)).limit(200).all()
            if not rows:
                return default_gap

            gaps = []
            for warm_value, ts in rows:
                base_reading = self.db.query(ParameterReading).filter(
                    ParameterReading.parameter_id == base.id,
                    ParameterReading.timestamp == ts,
                ).first()
                if base_reading:
                    gaps.append(float(warm_value) - float(base_reading.value))

            if gaps:
                return sum(gaps) / len(gaps)
        except Exception as e:
            logger.debug(f"Could not calculate historical gap {warm_param}-{base_param}: {e}")
        return default_gap

    def _get_zone_temperatures(self, now, bt50_indoor):
        dexter_temp = self._get_recent_reading_value('HA_TEMP_DEXTER', now)
        floor_temp = self._get_recent_reading_value('HA_TEMP_DOWNSTAIRS', now)
        sensor_mode = "normal"

        if floor_temp is None or dexter_temp is None:
            sensor_mode = "fallback"
            if floor_temp is None and bt50_indoor is not None:
                floor_gap = self._get_historical_gap('HA_TEMP_DOWNSTAIRS', '40033', 0.0)
                floor_temp = float(bt50_indoor) + floor_gap
                logger.warning(
                    f"sensor_mode=fallback GM downstairs={floor_temp:.2f}C from BT50 "
                    f"{float(bt50_indoor):.2f}C gap {floor_gap:+.2f}C"
                )

            if dexter_temp is None and floor_temp is not None:
                dexter_gap = self._get_historical_gap('HA_TEMP_DEXTER', 'HA_TEMP_DOWNSTAIRS', -1.0)
                dexter_temp = floor_temp + dexter_gap
                logger.warning(
                    f"sensor_mode=fallback GM dexter={dexter_temp:.2f}C from downstairs "
                    f"{floor_temp:.2f}C gap {dexter_gap:+.2f}C"
                )

        self._last_sensor_mode = sensor_mode
        self._last_floor_temp = floor_temp
        self._last_dexter_temp = dexter_temp
        return floor_temp, dexter_temp, sensor_mode

    def _apply_zone_temperature_overrides(self, device, now, action, bt50_indoor=None):
        floor_temp, dexter_temp, sensor_mode = self._get_zone_temperatures(now, bt50_indoor)
        bounds = comfort_bounds_for_time(now)
        self._last_comfort_bounds = bounds
        if sensor_mode == "fallback":
            logger.info("sensor_mode=fallback GM zone override evaluation")

        dexter_cold_threshold = min(19.0, bounds["dexter_min"] - 0.5)
        if dexter_temp is not None and dexter_temp < dexter_cold_threshold and action == 'REST':
            logger.warning(
                f"⚠️ Dexter-skydd: {dexter_temp:.1f}°C < {dexter_cold_threshold}°C — REST → RUN"
            )
            action = 'RUN'

        floor_trigger = bounds["floor_max"]
        dexter_trigger = bounds["dexter_max"]
        floor_release = floor_trigger - self.WARM_OVERRIDE_RELEASE_MARGIN
        dexter_release = dexter_trigger - self.WARM_OVERRIDE_RELEASE_MARGIN

        if self._warm_override_active:
            warm_override = (
                (floor_temp is not None and floor_temp > floor_release) or
                (dexter_temp is not None and dexter_temp > dexter_release)
            )
        else:
            warm_override = (
                (floor_temp is not None and floor_temp > floor_trigger) or
                (dexter_temp is not None and dexter_temp > dexter_trigger)
            )

        override_reason = None
        if warm_override:
            if floor_temp is not None and floor_temp > floor_trigger:
                override_reason = "WARM_OVERRIDE_DOWNSTAIRS"
                logger.warning(
                    f"⚠️ Varmoverride nedervåning ({bounds['profile']}): {floor_temp:.1f}°C > {floor_trigger:.1f}°C — {action} → REST"
                )
            elif dexter_temp is not None and dexter_temp > dexter_trigger:
                override_reason = "WARM_OVERRIDE_DEXTER"
                logger.warning(
                    f"⚠️ Varmoverride Dexter ({bounds['profile']}): {dexter_temp:.1f}°C > {dexter_trigger:.1f}°C — {action} → REST"
                )
            elif floor_temp is not None and floor_temp > floor_release:
                override_reason = "WARM_OVERRIDE_DOWNSTAIRS_HOLD"
            else:
                override_reason = "WARM_OVERRIDE_DEXTER_HOLD"

            if action != 'MUST_RUN':
                action = 'REST'

        self._warm_override_active = warm_override
        return action, override_reason

    def _apply_plan_delay_correction(self, now, plan, next_plan, action, offset, cur_supply, cur_outdoor):
        if not plan or plan.timestamp is None:
            return action, offset

        plan_age_minutes = (now.replace(tzinfo=None) - plan.timestamp).total_seconds() / 60.0
        next_offset = float(next_plan.planned_offset or 0.0) if next_plan else float(offset or 0.0)
        next_action = (next_plan.planned_action or "RUN") if next_plan else "RUN"

        floor_temp = getattr(self, "_last_floor_temp", None)
        dexter_temp = getattr(self, "_last_dexter_temp", None)
        bounds = getattr(self, "_last_comfort_bounds", None) or comfort_bounds_for_time(now)
        over_max = (
            (floor_temp is not None and floor_temp > bounds["floor_max"]) or
            (dexter_temp is not None and dexter_temp > bounds["dexter_max"])
        )

        target_supply_now = 20 + (20 - cur_outdoor) * settings.DEFAULT_HEATING_CURVE * 0.12 + float(offset or 0.0)
        heat_in_flight = cur_supply > 35.0 or cur_supply - target_supply_now > 4.0

        corrected_action = action
        corrected_offset = float(offset or 0.0)
        reason = None

        if plan_age_minutes >= 40.0 and next_offset < corrected_offset and over_max:
            corrected_offset = next_offset
            corrected_action = "REST" if next_action == "REST" or next_offset <= settings.OPTIMIZER_REST_THRESHOLD else "RUN"
            reason = "early_next_shed"
        elif plan_age_minutes >= 40.0 and next_action == "BOOST" and (over_max or heat_in_flight):
            corrected_offset = min(corrected_offset, 0.0)
            corrected_action = "RUN"
            reason = "block_stale_next_boost"
        elif action == "BOOST" and (over_max or heat_in_flight):
            corrected_offset = min(corrected_offset, 0.0)
            corrected_action = "RUN"
            reason = "block_current_boost_heat_in_flight"

        if reason:
            logger.info(
                f"lag_adjustment={reason} plan_age_minutes={plan_age_minutes:.0f} "
                f"offset={offset:.1f}->{corrected_offset:.1f} action={action}->{corrected_action} "
                f"next_offset={next_offset:.1f} heat_in_flight={heat_in_flight} over_max={over_max}"
            )
        else:
            logger.debug(
                f"lag_state plan_age_minutes={plan_age_minutes:.0f} next_offset={next_offset:.1f} "
                f"heat_in_flight={heat_in_flight} over_max={over_max}"
            )

        return corrected_action, corrected_offset

    def run_tick(self):
        now = datetime.now(timezone.utc)
        account = self._get_account()
        device = self.db.query(Device).first()
        if not device: return

        # 1. Fetch Fresh Data
        try:
            all_points = self.client.get_device_points(device.device_id)
            p = {str(item['parameterId']): item for item in all_points}
        except Exception as e:
            logger.error(f"API Fetch failed: {e}")
            return

        def get_val(pid, default=0.0):
            return float(p[pid]['value']) if pid in p else default

        cur_supply = get_val(self.PARAM_SUPPLY_READ)
        cur_outdoor = get_val(self.PARAM_OUTDOOR_READ)
        cur_indoor = get_val(self.PARAM_INDOOR_READ)
        cur_pump_gm = get_val(self.PARAM_GM_READ)
        
        # Get System Mode from DB (as it's a virtual parameter calculated by DataLogger)
        system_mode = 1.0 # Default to Heating
        try:
            param = self.db.query(Parameter).filter_by(parameter_id=self.PARAM_SYSTEM_MODE).first()
            if param:
                reading = self.db.query(ParameterReading).filter_by(parameter_id=param.id).order_by(desc(ParameterReading.timestamp)).first()
                if reading:
                    system_mode = reading.value
        except (AttributeError, TypeError) as e:
            logger.debug(f"System mode reading unavailable, using default (Heating): {e}")

        # 2. Get Current Plan/Offset
        plan = self.db.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp <= now,
            PlannedHeatingSchedule.timestamp > now - timedelta(hours=1)
        ).order_by(
            PlannedHeatingSchedule.timestamp.desc(),
            PlannedHeatingSchedule.id.desc()
        ).first()

        offset = plan.planned_offset if plan else 0.0
        action = plan.planned_action if plan else "RUN"
        reference_outdoor = plan.outdoor_temp if plan and plan.outdoor_temp is not None else None

        next_plan = self.db.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp > now,
            PlannedHeatingSchedule.timestamp <= now + timedelta(hours=2)
        ).order_by(
            PlannedHeatingSchedule.timestamp.asc(),
            PlannedHeatingSchedule.id.desc()
        ).first()

        raw_outdoor = cur_outdoor
        cur_outdoor = effective_outdoor_temp(raw_outdoor, reference_outdoor)
        if cur_outdoor != raw_outdoor:
            logger.info(
                f"BT1 solar filter: raw={raw_outdoor:.1f}C, reference={reference_outdoor:.1f}C, effective={cur_outdoor:.1f}C"
            )

        floor_temp, dexter_temp, sensor_mode = self._get_zone_temperatures(now, cur_indoor)
        self._last_comfort_bounds = comfort_bounds_for_time(now)
        action, offset = self._apply_plan_delay_correction(
            now, plan, next_plan, action, offset, cur_supply, cur_outdoor
        )

        try:
            action, zone_override = self._apply_zone_temperature_overrides(device, now, action, cur_indoor)
            if zone_override:
                safety_override = zone_override
            else:
                safety_override = None
        except Exception as e:
            logger.debug(f"Zone override check failed: {e}")
            safety_override = None

        # 3. Calculate Target & Delta
        target_supply = 20 + (20 - cur_outdoor) * settings.DEFAULT_HEATING_CURVE * 0.12 + offset
        
        dt_min = (now - self.last_tick_time).total_seconds() / 60.0
        if dt_min < 0 or dt_min > 10: dt_min = 1.0 # Safety
        
        # THE TRANSACTION
        supply_delta = None
        if system_mode == 2.0: # HOT WATER
            delta_gm = 0.0 # Pause bank during HW production
            logger.info("⏸️ Bank Paused: Pump is doing Hot Water.")
        elif system_mode == 3.0: # DEFROST
            delta_gm = 0.0
            logger.info("⏸️ Bank Paused: Pump is Defrosting.")
        else:
            diff_temp = cur_supply - target_supply
            supply_delta = diff_temp
            if safety_override and safety_override.startswith("WARM_OVERRIDE"):
                delta_gm = max(0.0, diff_temp * dt_min)
                logger.info("Warm override active — suppressing negative GM debt accumulation.")
            else:
                # TURBO MODE: Linear ramp 1.0x at deficit=2°C → 3.0x at deficit=8°C
                multiplier = 1.0
                if diff_temp < -2.0:
                    multiplier = 1.0 + min(2.0, (abs(diff_temp) - 2.0) / 3.0)
                delta_gm = diff_temp * dt_min * multiplier

        # 4. Update Bank Balance
        old_balance = account.balance
        account.balance += delta_gm

        account.balance = max(self.MIN_BALANCE, min(self.MAX_BALANCE, account.balance))
        if safety_override and safety_override.startswith("WARM_OVERRIDE") and account.balance < 100.0:
            account.balance = 100.0
        elif action == "REST" and account.balance < 100.0:
            logger.info(f"REST plan active — lifting GM bank {account.balance:.1f} → 100.0.")
            account.balance = 100.0
        elif (
            getattr(self, "_last_sensor_mode", None) == "fallback"
            and account.balance < 0.0
            and action not in ("MUST_RUN",)
        ):
            floor_temp = getattr(self, "_last_floor_temp", None)
            dexter_temp = getattr(self, "_last_dexter_temp", None)
            bounds = getattr(self, "_last_comfort_bounds", None) or comfort_bounds_for_time(now)
            floor_floor = bounds["floor_min"]
            dexter_floor = bounds["dexter_min"]
            zones_above_floor = (
                floor_temp is not None
                and floor_temp >= floor_floor
                and (dexter_temp is None or dexter_temp >= dexter_floor)
            )
            if zones_above_floor:
                logger.warning(
                    "sensor_mode=fallback — suppressing stale negative GM bank debt "
                    f"({account.balance:.1f} → 0.0) while zones are above comfort floors."
                )
                account.balance = 0.0

        # 5. SAFETY OVERRIDES
        if cur_indoor > 23.5:
            logger.warning(f"🚨 BASTU-VAKT: {cur_indoor}C. Resetting bank.")
            account.balance = 100.0
            action = "MUST_REST"
            safety_override = "BASTU_VAKT"

        # 6. Exekvering
        if action in ['MUST_REST', 'REST']:
            gm_to_write = 100
        else:
            raw_gm = int(round(account.balance / 10.0) * 10)
            if cur_indoor > self.CRITICAL_TEMP_LIMIT and raw_gm < (self.EL_HEATER_START_LIMIT + 50):
                gm_to_write = self.EL_HEATER_START_LIMIT + 50
            else:
                gm_to_write = raw_gm
            
            if action == 'MUST_RUN':
                gm_to_write = min(gm_to_write, self.PUMP_START_THRESHOLD - 10)

        # 7. Write to Pump (The Leash Logic)
        gm_actually_written = None
        try:
            # We write to the pump if:
            # 1. We haven't written before (startup)
            # 2. The pump has strayed too far from our target (> 50 GM)
            # 3. Our software target has changed significantly (> 10 GM) since last write
            # 4. We are in REST mode and pump is trying to run (GM < 0)

            strayed = abs(cur_pump_gm - gm_to_write) > 50
            target_changed = self.last_written_gm is None or abs(self.last_written_gm - gm_to_write) >= 10.0
            force_rest = (action in ['MUST_REST', 'REST']) and cur_pump_gm < 50

            if strayed or target_changed or force_rest:
                # Validate with SafetyGuard before writing
                decision = AgentAIDecisionSchema(
                    action='adjust',
                    parameter=self.PARAM_GM_WRITE,
                    current_value=cur_pump_gm,
                    suggested_value=gm_to_write,
                    reasoning=f"Bank balance {account.balance:.1f}, action {action}",
                    confidence=1.0,
                    expected_impact=f"Target GM: {gm_to_write}"
                )

                is_safe, safety_reason, safe_value = self.safety_guard.validate_decision(
                    decision,
                    device.device_id
                )

                if not is_safe:
                    logger.warning(f"⚠️ SafetyGuard BLOCKED GM write: {safety_reason}")
                    if safe_value is not None:
                        logger.info(f"Using SafetyGuard-adjusted value: {safe_value}")
                        gm_to_write = safe_value
                    else:
                        logger.error("SafetyGuard rejected with no safe alternative. Skipping write.")
                        return  # Don't write anything, skip this tick
                elif safe_value is not None:
                    # SafetyGuard approved but with adjustment
                    logger.info(f"SafetyGuard adjusted GM: {gm_to_write} → {safe_value} ({safety_reason})")
                    gm_to_write = safe_value

                # Attempt write and verify response
                response = self.client.set_point_value(device.device_id, self.PARAM_GM_WRITE, gm_to_write)

                # Verify write was acknowledged by API
                if response:
                    self.last_written_gm = gm_to_write
                    gm_actually_written = gm_to_write
                    logger.info(f"✓ GM Write Verified: {gm_to_write} (Reason: Strayed={strayed}, Changed={target_changed}, Rest={force_rest})")
                    logger.info(f"  -> Stats: Target Supply: {target_supply:.1f}C, Actual: {cur_supply:.1f}C, Bank: {account.balance:.1f}")
                else:
                    logger.warning(f"⚠️ GM Write returned empty response for value {gm_to_write} - write may have failed")
                    # Don't update last_written_gm - will retry on next tick
        except Exception as e:
            logger.error(f"✗ GM Write failed: {e}")
            # Don't update last_written_gm - will retry on next tick

        # 8. Log transaction for audit trail
        try:
            tx = GMTransaction(
                timestamp=now.replace(tzinfo=None),
                old_balance=old_balance,
                delta_gm=delta_gm,
                new_balance=account.balance,
                system_mode=system_mode,
                supply_actual=cur_supply,
                supply_target=target_supply,
                supply_delta=supply_delta,
                indoor_temp=cur_indoor,
                outdoor_temp=cur_outdoor,
                action=action,
                gm_written=gm_actually_written,
                safety_override=safety_override
            )
            self.db.add(tx)
        except Exception as e:
            logger.warning(f"Failed to log GM transaction: {e}")

        self.last_tick_time = now
        self.db.add(account)
        self.db.commit()

    def run_loop(self):
        logger.info("GM Controller V10.1 (HW Awareness) started.")
        try:
            import sdnotify
            _notifier = sdnotify.SystemdNotifier()
            _notifier.notify("READY=1")
            _watchdog = True
        except ImportError:
            _watchdog = False

        while True:
            try:
                self._refresh_session_if_needed()
                self.run_tick()
            except Exception as e:
                logger.error(f"Loop error: {e}")
                try:
                    self.db.rollback()
                except Exception:
                    pass
            if _watchdog:
                _notifier.notify("WATCHDOG=1")
            time.sleep(60)

if __name__ == "__main__":
    ctrl = GMController()
    ctrl.run_loop()
