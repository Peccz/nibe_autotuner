"""
Deterministic Energy Bank V10.0
Manages heat pump operation by simulating Degree Minutes (GM) locally.
Calculates energy debt based on Supply Target vs Actual.
"""
import time
import sys
import os
from datetime import datetime, timedelta, timezone
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from data.database import SessionLocal
from data.models import GMAccount, Device, PlannedHeatingSchedule, Parameter, ParameterReading
from services.analyzer import HeatPumpAnalyzer
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth
from core.config import settings

class GMController:
    # Constants
    PARAM_GM_READ = '40941' 
    PARAM_GM_WRITE = '40940' 
    PARAM_SUPPLY_READ = '40008' # BT2
    PARAM_OUTDOOR_READ = '40004' # BT1
    PARAM_INDOOR_READ = '40033' # BT50
    PARAM_VP_BANK = 'VP_GM_BANK'
    
    # Physical Limits
    MIN_BALANCE = -2000 # Allow deep debt for electric heater
    MAX_BALANCE = 200   # Max heat surplus
    
    # Nibe Settings
    PUMP_START_THRESHOLD = -200 # Pump starts at -200 GM
    
    def __init__(self):
        self.db = SessionLocal()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)
        self.analyzer = HeatPumpAnalyzer()
        self.last_tick_time = None
        self.last_written_gm = None

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

        # 2. Get Current Plan/Offset
        plan = self.db.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp <= now,
            PlannedHeatingSchedule.timestamp > now - timedelta(hours=1)
        ).order_by(PlannedHeatingSchedule.timestamp.desc()).first()
        
        offset = plan.planned_offset if plan else 0.0
        action = plan.planned_action if plan else "RUN"

        # 3. Calculate Target & Delta
        # Formula: 20 + (20-Out) * Curve * 0.12 + Offset
        target_supply = 20 + (20 - cur_outdoor) * settings.DEFAULT_HEATING_CURVE * 0.12 + offset
        
        # Calculate time since last tick (usually 1.0 min)
        if self.last_tick_time:
            dt_min = (now - self.last_tick_time).total_seconds() / 60.0
        else:
            dt_min = 1.0
        
        delta_gm = (cur_supply - target_supply) * dt_min
        
        # 4. Update Bank Balance
        # Logic: We only accumulate DEBT if it's not too warm inside
        if cur_indoor < 22.0 or delta_gm > 0:
            account.balance += delta_gm
        
        # Clamp Balance
        account.balance = max(self.MIN_BALANCE, min(self.MAX_BALANCE, account.balance))
        
        # 5. SAFETY OVERRIDES
        # Bastu-vakt: Force positive balance if very hot
        if cur_indoor > 23.5:
            logger.warning(f"🚨 BASTU-VAKT: {cur_indoor}C. Resetting bank.")
            account.balance = 100.0
            action = "MUST_REST"

        # 6. Exekvering (Determine what to write to pump)
        if action in ['MUST_REST', 'REST']:
            # Force stop: write a positive value
            gm_to_write = 100
        else:
            # Normal/Run: write our simulated truth
            # Nibe GM requires stepValue (often 10)
            gm_to_write = int(round(account.balance / 10.0) * 10)
            
            # Ensure pump starts if we have debt
            if action == 'RUN' and gm_to_write > self.PUMP_START_THRESHOLD and gm_to_write < 0:
                # If we want to run but debt hasn't reached -200 yet, 
                # we don't force it. We let the debt grow naturally.
                # BUT if user wants MUST_RUN, we force it.
                pass
            
            if action == 'MUST_RUN':
                gm_to_write = min(gm_to_write, self.PUMP_START_THRESHOLD - 10)

        # 7. Write to Pump
        try:
            if self.last_written_gm is None or abs(self.last_written_gm - gm_to_write) >= 1.0:
                self.client.set_point_value(device.device_id, self.PARAM_GM_WRITE, gm_to_write)
                self.last_written_gm = gm_to_write
                logger.info(f"GM Update: Wrote {gm_to_write} (Target:{target_supply:.1f}C, Actual:{cur_supply:.1f}C, Debt:{account.balance:.1f})")
        except Exception as e:
            logger.error(f"Write failed: {e}")

        self.last_tick_time = now
        self.db.add(account)
        self.db.commit()

    def run_loop(self):
        logger.info("GM Controller V10.0 (Deterministic Bank) started.")
        while True:
            try:
                self.run_tick()
            except Exception as e:
                logger.error(f"Loop error: {e}")
                self.db.rollback()
            time.sleep(60)

if __name__ == "__main__":
    ctrl = GMController()
    ctrl.run_loop()