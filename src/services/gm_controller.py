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
    
    SESSION_REFRESH_INTERVAL = 3600  # Refresh DB session every hour

    def __init__(self):
        self._open_session()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)
        self.analyzer = HeatPumpAnalyzer()
        self.last_tick_time = datetime.now(timezone.utc)
        self.last_written_gm = None
        self.last_session_refresh = datetime.now(timezone.utc)

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

        # Dexter cold override: if radiator zone < threshold during REST, force RUN
        DEXTER_COLD_THRESHOLD = 19.0
        try:
            dexter_param = self.db.query(Parameter).filter_by(parameter_id='HA_TEMP_DEXTER').first()
            if dexter_param:
                dexter_reading = self.db.query(ParameterReading).filter(
                    ParameterReading.parameter_id == dexter_param.id,
                    ParameterReading.timestamp > now.replace(tzinfo=None) - timedelta(hours=1)
                ).order_by(desc(ParameterReading.timestamp)).first()
                if dexter_reading and dexter_reading.value < DEXTER_COLD_THRESHOLD and action == 'REST':
                    logger.warning(
                        f"⚠️ Dexter-skydd: {dexter_reading.value:.1f}°C < {DEXTER_COLD_THRESHOLD}°C — REST → RUN"
                    )
                    action = 'RUN'
        except Exception as e:
            logger.debug(f"Dexter cold check failed: {e}")

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
            # TURBO MODE: Linear ramp 1.0x at deficit=2°C → 3.0x at deficit=8°C
            multiplier = 1.0
            if diff_temp < -2.0:
                multiplier = 1.0 + min(2.0, (abs(diff_temp) - 2.0) / 3.0)
            delta_gm = diff_temp * dt_min * multiplier

        # 4. Update Bank Balance
        old_balance = account.balance
        account.balance += delta_gm

        account.balance = max(self.MIN_BALANCE, min(self.MAX_BALANCE, account.balance))

        # 5. SAFETY OVERRIDES
        safety_override = None
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
