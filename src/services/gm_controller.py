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

class GMController:
    # Constants
    PARAM_GM_READ = '40941' # Degree Minutes (Read Only)
    PARAM_GM_WRITE = '40940' # Degree Minutes (Writeable)
    PARAM_HW_DEMAND_WRITE = '47041' # Hot Water Demand
    PARAM_VENTILATION_WRITE = '50005' # Increased Ventilation (0=Off, 1=On... 3=Max)
    PARAM_VP_BANK = 'VP_GM_BANK' # Virtual Parameter for History Logging
    
    # Safety Limits
    MIN_BALANCE = -3000 
    MAX_BALANCE = 500   
    
    # Pump Safety Limits
    HEATER_SAFETY_LIMIT = -350 
    
    def __init__(self):
        self.db = SessionLocal()
        self.auth = MyUplinkAuth()
        self.client = MyUplinkClient(self.auth)
        self.analyzer = HeatPumpAnalyzer()
        
        self._get_account()
        self._ensure_virtual_param()
        
        # State tracking
        self.last_written_gm = None

    def _get_account(self):
        account = self.db.query(GMAccount).first()
        if not account:
            account = GMAccount(balance=0.0, mode='NORMAL')
            self.db.add(account)
            self.db.commit()
        return account

    def _ensure_virtual_param(self):
        """Ensure the virtual parameter exists in DB for logging"""
        try:
            p = self.db.query(Parameter).filter_by(parameter_id=self.PARAM_VP_BANK).first()
            if not p:
                logger.info("Creating virtual parameter for GM Bank History")
                p = Parameter(
                    parameter_id=self.PARAM_VP_BANK,
                    parameter_name='GM Bank Balance',
                    parameter_unit='GM',
                    writable=False
                )
                self.db.add(p)
                self.db.commit()
        except Exception as e:
            logger.error(f"Failed to init virtual param: {e}")

    def log_bank_history(self, device_db_id, balance):
        """Log balance to history"""
        try:
            p = self.db.query(Parameter).filter_by(parameter_id=self.PARAM_VP_BANK).first()
            if not p: return
            
            reading = ParameterReading(
                device_id=device_db_id,
                parameter_id=p.id,
                timestamp=datetime.utcnow(),
                value=balance
            )
            self.db.add(reading)
        except Exception as e:
            logger.error(f"Failed to log bank history: {e}")

    def get_pump_value(self, device_id, param_id):
        try:
            val = self.client.get_point_data(device_id, param_id)
            return float(val['value'])
        except Exception as e:
            # logger.error(f"Failed to read {param_id}: {e}")
            return None

    def set_pump_gm(self, device_id, value):
        try:
            val_int = int(round(value))
            if self.last_written_gm is None or abs(self.last_written_gm - value) > 1.0:
                self.client.set_point_value(device_id, self.PARAM_GM_WRITE, val_int)
                self.last_written_gm = value
                logger.info(f"  -> Wrote GM {val_int} to pump (Bank Bal: {self._get_account().balance:.1f}).")
            return True
        except Exception as e:
            logger.error(f"Failed to write pump GM: {e}")
            return False

    def set_hw_demand(self, device_id, value):
        try:
            self.client.set_point_value(device_id, self.PARAM_HW_DEMAND_WRITE, int(value))
            logger.info(f"  -> Wrote HW Demand {value} to pump.")
            return True
        except Exception as e:
            logger.error(f"Failed to write HW Demand: {e}")
            return False

    def set_ventilation(self, device_id, value):
        try:
            self.client.set_point_value(device_id, self.PARAM_VENTILATION_WRITE, int(value))
            logger.info(f"  -> Wrote Ventilation {value} to pump.")
            return True
        except Exception as e:
            logger.error(f"Failed to write Ventilation: {e}")
            return False

    def run_tick(self):
        """Run one logic tick (e.g. every minute)"""
        
        # 1. Get Context
        account = self._get_account()
        device = self.db.query(Device).first()
        if not device:
            logger.warning("No device found")
            return

        # QM OPTIMIZATION: Fetch ALL points in ONE call instead of 4 separate calls
        try:
            all_points = self.client.get_device_points(device.device_id)
            points_dict = {str(p['parameterId']): p for p in all_points}
        except Exception as e:
            logger.error(f"Failed to fetch points from API: {e}")
            return

        # Helper to get value from our fetched list
        def get_val(pid):
            p = points_dict.get(str(pid))
            return float(p['value']) if p else None

        current_pump_gm = get_val(self.PARAM_GM_READ)
        if current_pump_gm is None: 
            logger.error("Failed to read current pump GM from point list, skipping tick.")
            return 
        
        current_hw_temp = get_val('40013')
        current_real_hw_mode = get_val(self.PARAM_HW_DEMAND_WRITE)
        current_real_vent_mode = get_val(self.PARAM_VENTILATION_WRITE)


        # 2. Update Balance
        if self.last_written_gm is not None:
            delta = current_pump_gm - self.last_written_gm
            if abs(delta) > 100:
                logger.warning(f"Large GM jump ({delta:.1f}). Syncing.")
                account.balance = current_pump_gm 
                self.last_written_gm = current_pump_gm 
            else:
                account.balance += delta 
            
            if account.balance < self.MIN_BALANCE: account.balance = self.MIN_BALANCE
            elif account.balance > self.MAX_BALANCE: account.balance = self.MAX_BALANCE
                
            self.db.add(account)
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
        planned_hw_mode = current_hour_plan.planned_hot_water_mode if current_hour_plan else 1 

        # --- EMERGENCY HW OVERRIDE (Forced from GMController) ---
        if current_hw_temp is not None and current_hw_temp < 41.0: # If real temp is low
            if planned_hw_mode != 2: # and plan is not already LUX
                logger.warning(f"Emergency HW Boost: Temp is {current_hw_temp:.1f}°C. Forcing LUX.")
                planned_hw_mode = 2 # Force LUX

        target_vent_mode = 3.0 if planned_hw_mode == 2 else 0.0 # Use Mode 3 (65%) for Lux

        logger.info(f"Status: GM={current_pump_gm:.0f}, Bal={account.balance:.0f}. Plan: {planned_action}, HW: {planned_hw_mode}, Vent: {target_vent_mode}")

        # 4. Execute Strategy
        value_to_write_gm = current_pump_gm

        if planned_action in ['MUST_RUN', 'RUN']:
            value_to_write_gm = account.balance
            if value_to_write_gm > -60: 
                value_to_write_gm = -100 
            if value_to_write_gm < self.HEATER_SAFETY_LIMIT:
                value_to_write_gm = self.HEATER_SAFETY_LIMIT
            
        elif planned_action in ['MUST_REST', 'REST']:
            value_to_write_gm = 100 

        elif planned_action in ['HOLD', 'NORMAL']:
            value_to_write_gm = account.balance
            if value_to_write_gm < self.HEATER_SAFETY_LIMIT:
                value_to_write_gm = self.HEATER_SAFETY_LIMIT

        # --- Write to Pump ---
        # GM Parameter
        self.set_pump_gm(device.device_id, value_to_write_gm)
        
        # HW Demand Parameter (47041)
        if current_real_hw_mode is None or int(current_real_hw_mode) != planned_hw_mode:
            logger.info(f"HW Mode Mismatch (Pump:{current_real_hw_mode} != Plan:{planned_hw_mode}). Correcting...")
            self.set_hw_demand(device.device_id, planned_hw_mode)
            
        # Ventilation Parameter (50005)
        if current_real_vent_mode is None or int(current_real_vent_mode) != target_vent_mode:
            logger.info(f"Vent Mode Mismatch (Pump:{current_real_vent_mode} != Plan:{target_vent_mode}). Correcting...")
            self.set_ventilation(device.device_id, target_vent_mode)
        
        # LOG HISTORY
        self.log_bank_history(device.id, account.balance)
        
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
