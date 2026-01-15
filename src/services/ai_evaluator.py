"""
AI Evaluator Service (Senior QM Version)
Calculates actual savings by comparing real operation with a minute-by-minute baseline simulation.
"""
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple, Optional
from loguru import logger
import numpy as np

from data.database import SessionLocal
from data.models import ParameterReading, Device, GMAccount
from data.performance_model import DailyPerformance
from services.analyzer import HeatPumpAnalyzer
from services.price_service import price_service

class AIEvaluator:
    # Physical Constants for F730
    HZ_TO_KW_RATIO = 0.02  # 100 Hz roughly 2.0 kW electrical input
    BASE_START_GM = -60    # Standard Nibe start threshold
    BASE_STOP_GM = 0       # Standard Nibe stop threshold
    
    def __init__(self):
        self.db = SessionLocal()
        self.analyzer = HeatPumpAnalyzer()

    def evaluate_yesterday(self):
        """Perform full performance analysis for the previous day"""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        self.evaluate_day(yesterday)

    def evaluate_day(self, target_date):
        """Analyze a specific date (00:00 - 23:59)"""
        logger.info(f"--- STARTING EVALUATION FOR {target_date} ---")
        
        # Localize start/end to UTC for DB queries
        start_time = datetime.combine(target_date, datetime.min.time())
        end_time = datetime.combine(target_date, datetime.max.time())
        
        device = self.analyzer.get_device()
        
        # 1. Fetch Actual Data
        comp_readings = self.analyzer.get_readings(device, self.analyzer.PARAM_COMPRESSOR_FREQ, start_time, end_time)
        out_readings = self.analyzer.get_readings(device, self.analyzer.PARAM_OUTDOOR_TEMP, start_time, end_time)
        in_readings = self.analyzer.get_readings(device, self.analyzer.PARAM_INDOOR_TEMP, start_time, end_time)
        
        if not comp_readings or not out_readings:
            logger.warning(f"Insufficient data for {target_date}. Skipping.")
            return

        # 2. Calculate Actual Consumption & Cost (High Precision)
        actual_kwh = 0.0
        actual_cost = 0.0
        
        # Group price lookups by hour to speed up
        price_cache = {}

        for i in range(len(comp_readings) - 1):
            ts, hz = comp_readings[i]
            next_ts, _ = comp_readings[i+1]
            duration_h = (next_ts - ts).total_seconds() / 3600
            
            if duration_h > 1.0: continue # Skip data gaps
            
            kw = hz * self.HZ_TO_KW_RATIO
            kwh = kw * duration_h
            
            hour_key = ts.replace(minute=0, second=0, microsecond=0)
            if hour_key not in price_cache:
                price_cache[hour_key] = price_service.get_price_at(hour_key)
            
            price = price_cache[hour_key]
            actual_kwh += kwh
            actual_cost += kwh * price

        # 3. Simulate Baseline (The "Counterfactual")
        baseline_kwh, baseline_cost = self._simulate_baseline(target_date, out_readings, in_readings, price_cache)

        # 4. Finalize Results
        savings_sek = baseline_cost - actual_cost
        savings_pct = (savings_sek / baseline_cost * 100) if baseline_cost > 0 else 0
        
        avg_in = np.mean([r[1] for r in in_readings]) if in_readings else 0
        min_in = np.min([r[1] for r in in_readings]) if in_readings else 0
        max_in = np.max([r[1] for r in in_readings]) if in_readings else 0
        avg_out = np.mean([r[1] for r in out_readings]) if out_readings else 0

        # Save to Database
        perf = DailyPerformance(
            date=datetime.combine(target_date, datetime.min.time()),
            actual_kwh=actual_kwh,
            actual_cost_sek=actual_cost,
            baseline_kwh=baseline_kwh,
            baseline_cost_sek=baseline_cost,
            savings_sek=savings_sek,
            savings_percent=savings_pct,
            avg_indoor_temp=avg_in,
            min_indoor_temp=min_in,
            max_indoor_temp=max_in,
            avg_outdoor_temp=avg_out
        )
        
        existing = self.db.query(DailyPerformance).filter_by(date=perf.date).first()
        if existing: self.db.delete(existing)
        
        self.db.add(perf)
        self.db.commit()
        
        logger.info(f"VERDICT {target_date}:")
        logger.info(f"  Actual:   {actual_kwh:5.1f} kWh | {actual_cost:6.2f} SEK")
        logger.info(f"  Baseline: {baseline_kwh:5.1f} kWh | {baseline_cost:6.2f} SEK")
        logger.info(f"  SAVINGS:  {savings_sek:6.2f} SEK ({savings_pct:.1f}%)")

    def _simulate_baseline(self, date, out_readings, in_readings, price_cache) -> Tuple[float, float]:
        """
        Precise minute-by-minute simulation of a standard Nibe F730 logic.
        """
        total_kwh = 0.0
        total_cost = 0.0
        
        # Convert readings to lookup maps
        out_map = {r[0].replace(second=0, microsecond=0): r[1] for r in out_readings}
        in_map = {r[0].replace(second=0, microsecond=0): r[1] for r in in_readings}
        
        current_gm = -30.0 # Start neutral
        is_running = False
        
        start_ts = datetime.combine(date, datetime.min.time())
        
        # Get averages for interpolation fallback
        default_out = np.mean([r[1] for r in out_readings])
        default_in = np.mean([r[1] for r in in_readings]) if in_readings else 21.0

        for m in range(1440):
            current_ts = start_ts + timedelta(minutes=m)
            ts_key = current_ts.replace(second=0, microsecond=0)
            
            # 1. Get Environmental Data
            t_out = out_map.get(ts_key, default_out)
            t_in = in_map.get(ts_key, default_in)
            
            # 2. GM Physics Logic
            # Gradminutes drop when Framledning < Calculated Framledning.
            # In baseline mode, we assume the house needs exactly what it leaks.
            # Degree Minutes = (Integral of) Calculated Supply - Actual Supply
            # Simpler model: GM loss is proportional to (Indoor - Outdoor)
            gm_loss_per_min = (t_in - t_out) * 0.05 
            
            if is_running:
                # Standard run at ~60Hz
                # Production is 1 GM/min at normal delta T
                current_gm += (1.0 - gm_loss_per_min)
                
                kwh_per_min = (60 * self.HZ_TO_KW_RATIO) / 60
                total_kwh += kwh_per_min
                
                hour_key = current_ts.replace(minute=0, second=0, microsecond=0)
                price = price_cache.get(hour_key, 1.2)
                total_cost += kwh_per_min * price
                
                if current_gm >= self.BASE_STOP_GM:
                    is_running = False
            else:
                current_gm -= gm_loss_per_min
                if current_gm <= self.BASE_START_GM:
                    is_running = True
                    
        return total_kwh, total_cost

if __name__ == "__main__":
    evaluator = AIEvaluator()
    if len(sys.argv) > 1:
        try:
            d = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
            evaluator.evaluate_day(d)
        except Exception as e:
            print(f"Error: {e}")
    else:
        evaluator.evaluate_yesterday()

