import time
import sys
import os
from datetime import datetime, timedelta, timezone
from loguru import logger

# Add src to path
sys.path.insert(0, os.path.abspath('src'))

from data.database import SessionLocal
from data.models import GMAccount, Device, PlannedHeatingSchedule
from services.analyzer import HeatPumpAnalyzer
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth

class GMController:
    # Constants
    PARAM_GM_READ = '40941' # Degree Minutes (Read Only)
    PARAM_GM_WRITE = '40940' # Degree Minutes (Writeable)
    PARAM_OFFSET_WRITE = '47011' # Curve Offset
    
    # Safety Limits
    MIN_BALANCE = -800 
    MAX_BALANCE = 100 
    
    def __init__(self):
        self.db = SessionLocal()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)
        self.analyzer = HeatPumpAnalyzer()
        
        self._get_account()
        
        # State tracking
        self.last_written_gm = None
        self.last_written_offset = None

    def _get_account(self):
        account = self.db.query(GMAccount).first()
        if not account:
            account = GMAccount(balance=0.0, mode='NORMAL')
            self.db.add(account)
            self.db.commit()
        return account

    def get_pump_gm(self, device_id):
        try:
            val = self.client.get_point_data(device_id, self.PARAM_GM_READ)
            return float(val['value'])
        except Exception as e:
            logger.error(f"Failed to read pump GM: {e}")
            return None

    def set_pump_gm(self, device_id, value):
        try:
            if self.last_written_gm is None or abs(self.last_written_gm - value) > 0.01:
                self.client.set_point_value(device_id, self.PARAM_GM_WRITE, value)
                self.last_written_gm = value
                logger.info(f"  -> Wrote GM {value:.1f} to pump.")
            return True
        except Exception as e:
            logger.error(f"Failed to write pump GM: {e}")
            return False

    def set_pump_offset(self, device_id, value):
        try:
            if self.last_written_offset is None or abs(self.last_written_offset - value) > 0.1:
                self.client.set_point_value(device_id, self.PARAM_OFFSET_WRITE, value)
                self.last_written_offset = value
                logger.info(f"  -> Wrote Offset {value:.1f} to pump.")
            return True
        except Exception as e:
            logger.error(f"Failed to write Offset: {e}")
            return False

    def run_tick(self):
        """Run one logic tick (e.g. every minute)"""
        
        # 1. Get Context
        account = self._get_account()
        device = self.db.query(Device).first()
        if not device:
            logger.warning("No device found")
            return

        current_pump_gm = self.get_pump_gm(device.device_id)
        if current_pump_gm is None: return

        # 2. Update Balance
        if self.last_written_gm is not None:
            delta = current_pump_gm - self.last_written_gm
            if abs(delta) > 100:
                logger.warning(f"Large GM jump ({delta:.1f}). Syncing.")
                account.balance = current_pump_gm 
                self.last_written_gm = current_pump_gm 
            else:
                account.balance += delta 
            
            # Safety Clamp
            if account.balance < self.MIN_BALANCE:
                logger.warning(f"GM Balance low ({account.balance:.1f}). Forcing SPEND.")
                account.mode = 'SPEND'
            elif account.balance > self.MAX_BALANCE:
                account.balance = self.MAX_BALANCE
                
            self.db.add(account)
            self.db.commit()
        else:
            logger.info("First run: Syncing balance.")
            account.balance = current_pump_gm
            self.last_written_gm = current_pump_gm
            self.db.add(account)
            self.db.commit()
            return

        # 3. Get Plan
        current_time_utc = datetime.now(timezone.utc)
        current_hour_plan = self.db.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp <= current_time_utc,
            PlannedHeatingSchedule.timestamp > current_time_utc - timedelta(hours=1)
        ).order_by(PlannedHeatingSchedule.timestamp.desc()).first()

        planned_action = current_hour_plan.planned_action if current_hour_plan else account.mode
        target_offset = current_hour_plan.planned_offset if current_hour_plan else 0.0

        logger.info(f"Status: GM={current_pump_gm:.0f}, Bal={account.balance:.0f}. Plan: {planned_action}, Offset: {target_offset}")

        # 4. Execute GM Strategy
        value_to_write = current_pump_gm

        if planned_action in ['MUST_RUN', 'RUN']:
            value_to_write = account.balance
            if value_to_write > -60: value_to_write = -500 # Force start if balance is too high
            
        elif planned_action in ['MUST_REST', 'REST']:
            value_to_write = 100 # Force stop

        elif planned_action in ['HOLD', 'NORMAL']:
            value_to_write = account.balance

        # Safety override
        if current_pump_gm > 50 and planned_action not in ['REST', 'MUST_REST']:
             value_to_write = 0

        # Write to Pump
        self.set_pump_gm(device.device_id, value_to_write)
        self.set_pump_offset(device.device_id, target_offset)
        
        self.db.add(account)
        self.db.commit()

    def run_loop(self):
        logger.info("Starting GM Controller...")
        while True:
            try:
                self.run_tick()
            except Exception as e:
                logger.error(f"Crash in GM Controller loop: {e}")
                self.db.rollback()
            time.sleep(60)

if __name__ == "__main__":
    ctrl = GMController()
    ctrl.run_loop()
