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
    PARAM_GM_READ = '40941' # FIXED: Correct ID for Degree Minutes (Read Only)
    PARAM_GM_WRITE = '40940' # Writeable setting
    
    # Safety Limits
    MIN_BALANCE = -800 # Never let virtual balance go below this (house freezes)
    MAX_BALANCE = 100 # No point saving more positive than this
    
    def __init__(self):
        self.db = SessionLocal()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)
        self.analyzer = HeatPumpAnalyzer()
        
        # Initialize account if missing
        self._get_account()
        
        # State tracking
        self.last_written_gm = None # What was the last value we wrote to the pump?

    def _get_account(self):
        account = self.db.query(GMAccount).first()
        if not account:
            account = GMAccount(balance=0.0, mode='NORMAL')
            self.db.add(account)
            self.db.commit()
        return account

    def get_pump_gm(self, device_id):
        # We prefer reading 40009 as it is the "truth"
        try:
            val = self.client.get_point_data(device_id, self.PARAM_GM_READ)
            return float(val['value'])
        except Exception as e:
            logger.error(f"Failed to read pump GM: {e}")
            return None

    def set_pump_gm(self, device_id, value):
        try:
            # Only write if value is different or if it's the first write
            if self.last_written_gm is None or abs(self.last_written_gm - value) > 0.01:
                self.client.set_point_value(device_id, self.PARAM_GM_WRITE, value)
                self.last_written_gm = value
                logger.info(f"  -> Wrote {value:.1f} to pump (GM setpoint).")
            else:
                logger.debug(f"  -> GM setpoint already {value:.1f}, skipping write.")
            return True
        except Exception as e:
            logger.error(f"Failed to write pump GM: {e}")
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
        if current_pump_gm is None:
            logger.error("Could not read current pump GM from API.")
            return

        logger.info(f"STATUS: Pump GM: {current_pump_gm:.1f}, Bank Balance: {account.balance:.1f}, Mode: {account.mode}")

        # 2. Update Balance (Calculate Production/Consumption)
        if self.last_written_gm is not None:
            # The "delta" is how much the pump's GM changed from what we last set it to.
            # This represents the heat loss/gain by the house since our last intervention.
            delta = current_pump_gm - self.last_written_gm
            
            # Sanity check delta (it shouldn't jump thousands in a minute)
            if abs(delta) > 100: # If delta is too large, it might be an error or manual intervention
                logger.warning(f"Large GM jump detected ({delta:.1f}). Syncing balance to pump.")
                account.balance = current_pump_gm # Re-sync with reality
                self.last_written_gm = current_pump_gm # Update what we think pump has
            else:
                account.balance += delta # Add the actual change observed in the pump's GM
            
            # Clamp balance (Safety)
            if account.balance < self.MIN_BALANCE:
                logger.warning(f"GM Bank Balance {account.balance:.1f} too low! Overriding mode to 'SPEND' for safety.")
                account.mode = 'SPEND' # Override mode for safety
            elif account.balance > self.MAX_BALANCE:
                account.balance = self.MAX_BALANCE
                
            self.db.add(account) # Add to session (might be existing)
            self.db.commit()
            logger.info(f"  -> Observed change: {delta:.1f}. New Bank Balance: {account.balance:.1f}")
        else:
            # First run, sync balance to pump's current GM
            logger.info("First run: Syncing Bank Balance to current pump GM.")
            account.balance = current_pump_gm
            self.last_written_gm = current_pump_gm # Assume we've effectively just written this
            self.db.add(account)
            self.db.commit()
            return # Don't write on first tick, just sync

        # 3. Get Planned Action from Schedule
        current_time_utc = datetime.now(timezone.utc)
        current_hour_plan = self.db.query(PlannedHeatingSchedule).filter(
            PlannedHeatingSchedule.timestamp <= current_time_utc,
            PlannedHeatingSchedule.timestamp > current_time_utc - timedelta(hours=1)
        ).order_by(PlannedHeatingSchedule.timestamp.desc()).first()

        planned_action = current_hour_plan.planned_action if current_hour_plan else account.mode # Fallback to account mode
        target_gm_from_plan = current_hour_plan.planned_gm_value if current_hour_plan and current_hour_plan.planned_gm_value is not None else 0 # Fallback

        logger.info(f"  -> Planned action for this hour: {planned_action}")

        # 4. Determine GM Value to Write to Pump (Verkställ)
        value_to_write = current_pump_gm # Default: don't change

        if planned_action == 'MUST_RUN' or planned_action == 'RUN':
            value_to_write = account.balance # Let the pump work off the entire balance
            if value_to_write > 0: # If balance is positive, we want pump to stop
                value_to_write = 0 # Or a higher value if we want to build positive GM in pump
            
            # To make pump run long and hard, set GM to a low value
            # Let's target -500 to make it run for a while if it can
            if account.balance > -500: # Only if balance isn't too negative already
                value_to_write = -500
            else:
                value_to_write = account.balance # Or just current balance if already very negative
            logger.info(f"  Mode RUN. Target DM: {value_to_write:.1f}")

        elif planned_action == 'MUST_REST' or planned_action == 'REST':
            # Stop the pump (set GM to a high positive value, e.g., 100)
            # This makes the pump think it's too warm.
            value_to_write = 100
            logger.info(f"  Mode REST. Target DM: {value_to_write:.1f}")

        elif planned_action == 'HOLD' or planned_action == 'NORMAL':
            # Simply let pump follow its own calculated GM (transparent)
            value_to_write = account.balance
            logger.info(f"  Mode NORMAL/HOLD. Target DM: {value_to_write:.1f}")

        # Safety override: If pump GM is too high, force it to run
        if current_pump_gm > 50:
            logger.warning(f"Pump GM {current_pump_gm:.1f} is high, forcing pump to RUN.")
            value_to_write = 0 # Set to 0 to make pump run if it has demand

        # Final write to pump
        if self.set_pump_gm(device.device_id, value_to_write):
            self.last_written_gm = value_to_write # Update what we actually wrote
        
        self.db.add(account) # Update last_updated
        self.db.commit()

    def run_loop(self):
        logger.info("Starting GM Controller...")
        while True:
            try:
                self.run_tick()
            except Exception as e:
                logger.error(f"Crash in GM Controller loop: {e}")
                self.db.rollback() # Rollback any pending changes
                
            time.sleep(60) # Run every minute

if __name__ == "__main__":
    ctrl = GMController()
    ctrl.run_loop()