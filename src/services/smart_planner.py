import sys
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import text

from data.database import SessionLocal
from data.models import Device, Parameter, ParameterReading, GMAccount, PlannedHeatingSchedule
from services.analyzer import HeatPumpAnalyzer
from services.weather_service import SMHIWeatherService
from services.price_service import PriceService
from services.learning_service import LearningService
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth
from core.config import settings


class HourlyPlan(BaseModel):
    timestamp: datetime
    outdoor_temp: float
    electricity_price: float
    cloud_cover: float = 8.0
    solar_gain: float = 0.0 
    wind_speed: float = 0.0
    wind_direction: int = 0
    simulated_indoor_temp: Optional[float] = None
    simulated_dexter_temp: Optional[float] = None
    planned_action: str 
    planned_gm_value: Optional[float] = None 
    planned_offset: Optional[float] = 0.0 
    planned_hot_water_mode: Optional[int] = 1 
    predicted_supply: Optional[float] = None

class SmartPlanner:
    def __init__(self):
        self.session = SessionLocal()
        self.analyzer = HeatPumpAnalyzer()
        self.weather_service = SMHIWeatherService()
        self.price_service = PriceService()
        self.learning_service = LearningService(self.session, self.analyzer)
        
        self.device = self.analyzer.get_device()
        self.tuning = self._load_tuning_parameters()

    def _load_tuning_parameters(self) -> Dict[str, float]:
        """Load physical coefficients from system_tuning table"""
        try:
            res = self.session.execute(text("SELECT parameter_id, value FROM system_tuning")).fetchall()
            tuning = {row[0]: row[1] for row in res}
            # Ensure defaults for new V4.0 params
            defaults = {
                'thermal_leakage': 0.009,
                'rad_efficiency': 0.022,
                'slab_efficiency': 0.015,
                'wind_sensitivity': 0.01,
                'solar_gain_coeff': 0.04,
                'wind_direction_west_factor': 1.2,
                'internal_heat_gain': 0.015,
                'actual_shunt_limit': 29.0
            }
            for k, v in defaults.items():
                if k not in tuning: tuning[k] = v
            return tuning
        except Exception as e:
            logger.error(f"Failed to load tuning parameters: {e}")
            return {'thermal_leakage': 0.009, 'rad_efficiency': 0.022, 'slab_efficiency': 0.015}

    def _get_wind_factor(self, direction: int) -> float:
        """Returns the cooling multiplier based on wind direction"""
        if direction is None: return 1.0
        # 0=N, 90=E, 180=S, 270=W. West wind (225-315) hits Dexter's room side.
        if 225 <= direction <= 315: return self.tuning.get('wind_direction_west_factor', 1.2)
        return 1.0

    def plan_next_24h(self) -> List[HourlyPlan]:
        logger.info("Starting SmartPlanner V6.0 (Safety & Economy)...")

        if not self.device:
            self.device = self.analyzer.get_device()
            if not self.device: return []

        # 1. Fetch current context & Parameters
        current_indoor_temp = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_HA_TEMP_DOWNSTAIRS) or 21.0
        current_dexter_temp = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_HA_TEMP_DEXTER) or current_indoor_temp
        
        # Constraints (Strict per user request)
        LIMIT_MIN_DOWN = 20.5
        LIMIT_TARGET_DOWN_MIN = 21.0
        LIMIT_TARGET_DOWN_MAX = 22.0
        LIMIT_MIN_DEXTER = 19.5
        
        # Physics Params
        leak_down = self.tuning['thermal_leakage']
        leak_dexter = self.tuning.get('thermal_leakage_dexter', leak_down * 1.3)
        rad_eff = self.tuning['rad_efficiency']
        slab_eff = self.tuning['slab_efficiency']
        trans_coeff = self.tuning.get('inter_zone_transfer', 0.005)
        shunt_limit = self.tuning.get('actual_shunt_limit', 29.0)
        base_curve = settings.DEFAULT_HEATING_CURVE

        # Weather & Price Data
        weather_forecast = self.weather_service.get_forecast(hours_ahead=48)
        weather_forecast_dict = {f.timestamp.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat(): f for f in weather_forecast}
        
        # Calculate baseline temp for price sensitivity
        avg_temp_baseline = sum([f.temperature for f in weather_forecast[:24]]) / max(1, len(weather_forecast[:24]))

        price_forecast_yesterday = self.price_service.get_prices_yesterday()
        price_forecast_today = self.price_service.get_prices_today()
        price_forecast_tomorrow = self.price_service.get_prices_tomorrow()
        
        all_prices_data: Dict[str, float] = {}
        for p in price_forecast_yesterday + price_forecast_today + price_forecast_tomorrow:
            utc_key = p.time_start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
            all_prices_data[utc_key] = p.price_per_kwh
            
        current_prices = [p.price_per_kwh for p in price_forecast_today + price_forecast_tomorrow]
        avg_price = sum(current_prices) / max(1, len(current_prices))

        # 2. Initialize Plan (Default REST)
        plan: List[HourlyPlan] = []
        current_hour_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        for i in range(25):
            current_time = current_hour_start + timedelta(hours=i)
            iso_ts = current_time.isoformat()
            forecast = weather_forecast_dict.get(iso_ts)
            
            out_temp = forecast.temperature if forecast else 0.0
            wind_speed = forecast.wind_speed if forecast else 0.0
            wind_dir = forecast.wind_direction if forecast else 0
            
            # Price Prediction Logic
            price = all_prices_data.get(iso_ts)
            if price is None:
                fallback_ts = (current_time - timedelta(days=1)).isoformat()
                base_price = all_prices_data.get(fallback_ts, avg_price)
                
                sens = self.tuning.get('price_wind_sensitivity', 0.0)
                wind_drop = (wind_speed * sens) if sens > 0 else 0
                
                weekend_factor = 1.0
                if current_time.weekday() >= 5:
                    weekend_factor = self.tuning.get('weekend_discount_factor', 0.90)
                
                temp_sens = self.tuning.get('price_temp_sensitivity', 0.0)
                temp_hike = 0.0
                if temp_sens > 0 and out_temp < 0:
                    delta_c = max(0, avg_temp_baseline - out_temp)
                    temp_hike = delta_c * temp_sens

                price = max(0.01, (base_price * weekend_factor) - wind_drop + temp_hike)

            plan.append(HourlyPlan(
                timestamp=current_time,
                outdoor_temp=out_temp,
                electricity_price=price,
                wind_speed=wind_speed,
                wind_direction=wind_dir,
                planned_action="REST",
                planned_offset=0.0
            ))

        # --- SIMULATION FUNCTION ---
        def simulate_plan(candidate_plan):
            t_down = current_indoor_temp
            t_dex = current_dexter_temp
            states = [] # List of dicts: {t_down, t_dex, supply_down, supply_dex}

            for p in candidate_plan:
                # 1. Determine Supply Temp
                curve_supply = 20 + ((20 - p.outdoor_temp) * base_curve * 0.15)
                
                offset = p.planned_offset if p.planned_action == "RUN" else 0.0
                target_supply = curve_supply + offset
                
                # 2. Zone Constraints
                supply_down = min(target_supply, shunt_limit)
                supply_dexter = target_supply
                
                # 3. Physics: Heat Exchange
                gain_down = 0.0
                if p.planned_action == "RUN":
                    gain_down = max(0, (supply_down - t_down) * slab_eff)
                
                gain_dex = 0.0
                if p.planned_action == "RUN":
                    gain_dex = max(0, (supply_dexter - t_dex) * rad_eff)
                
                # 4. Physics: Losses
                w_fac = self._get_wind_factor(p.wind_direction)
                
                loss_down = (t_down - p.outdoor_temp) * leak_down * (1 + p.wind_speed * self.tuning.get('wind_sensitivity', 0.005))
                loss_dex = (t_dex - p.outdoor_temp) * leak_dexter * w_fac * (1 + p.wind_speed * self.tuning.get('wind_sensitivity_dexter', 0.005))
                
                # 5. Physics: Inter-zone Transfer
                transfer = (t_down - t_dex) * trans_coeff
                
                # 6. Physics: External Inputs
                sol_down = (p.solar_gain * (self.tuning['solar_gain_coeff']/0.04))
                sol_dex = (p.solar_gain * (self.tuning.get('solar_gain_dexter', 0.02)/0.04))
                int_down = self.tuning.get('internal_heat_gain', 0.015)
                int_dex = self.tuning.get('internal_gain_dexter', 0.015)
                
                # 7. Step State
                t_down += gain_down - loss_down - transfer + sol_down + int_down
                t_dex += gain_dex + transfer - loss_dex + sol_dex + int_dex
                
                # Store for UI/Analysis
                p.simulated_indoor_temp = t_down
                p.simulated_dexter_temp = t_dex
                p.predicted_supply = supply_dexter 
                
                states.append({'t_down': t_down, 't_dex': t_dex, 'price': p.electricity_price, 'idx': len(states)})
            
            return states

        # --- PHASE 1: SECURE THE SLAB (Baseline Heating) ---
        iterations = 0
        while iterations < 20:
            states = simulate_plan(plan)
            
            # Check for Slab Failure
            fail_idx = -1
            for i, s in enumerate(states):
                if s['t_down'] < LIMIT_MIN_DOWN:
                    fail_idx = i
                    break
            
            if fail_idx == -1:
                break # Slab is safe
            
            # Solution: Charge BEFORE failure
            candidates = [i for i in range(fail_idx + 1) if plan[i].planned_action == "REST"]
            
            if not candidates:
                break
                
            best_idx = min(candidates, key=lambda i: plan[i].electricity_price)
            
            # Action: Normal Run
            plan[best_idx].planned_action = "RUN"
            plan[best_idx].planned_offset = 1.0 
            plan[best_idx].planned_gm_value = -300.0
            iterations += 1

        # --- PHASE 2: ECONOMY BUFFERING ---
        cheap_limit = avg_price * 0.85
        
        for i, p in enumerate(plan):
            if p.planned_action == "REST" and p.electricity_price < cheap_limit:
                p.planned_action = "RUN"
                p.planned_offset = 1.0
                p.planned_gm_value = -300.0
                
                states = simulate_plan(plan)
                if states[i]['t_down'] > LIMIT_TARGET_DOWN_MAX:
                    # Too hot, revert
                    p.planned_action = "REST"
                    p.planned_offset = 0.0
                    p.planned_gm_value = None

        # --- PHASE 3: DEXTER RESCUE ---
        while iterations < 40:
            states = simulate_plan(plan)
            
            fail_idx = -1
            for i, s in enumerate(states):
                if s['t_dex'] < LIMIT_MIN_DEXTER:
                    fail_idx = i
                    break
            
            if fail_idx == -1:
                break
            
            candidates = []
            lookback = max(0, fail_idx - 3)
            
            for i in range(lookback, fail_idx + 1):
                score = plan[i].electricity_price
                if plan[i].planned_action == "RUN" and plan[i].planned_offset < 3.0:
                    score -= 1000 # Prioritize upgrading!
                elif plan[i].planned_action == "REST":
                    pass 
                else:
                    score += 9999 # Already boosted
                
                candidates.append((i, score))
            
            candidates.sort(key=lambda x: x[1])
            
            if not candidates or candidates[0][1] > 5000:
                logger.warning(f"Dexter fail at {fail_idx} cannot be fixed.")
                break
                
            best_idx = candidates[0][0]
            
            # Apply BOOST
            plan[best_idx].planned_action = "RUN"
            plan[best_idx].planned_gm_value = -300.0
            plan[best_idx].planned_offset = 4.0 # Turbo
            
            logger.info(f"Phase 3: Boosting Dexter at hour {best_idx} (Offset 4)")
            iterations += 1

        # --- PHASE 4: OPTIMIZATION (Downgrade Overkill) ---
        # 1. Downgrade Boosts
        boost_indices = [i for i, p in enumerate(plan) if p.planned_action == "RUN" and p.planned_offset > 1.5]
        boost_indices.sort(key=lambda i: plan[i].electricity_price, reverse=True)
        
        for idx in boost_indices:
            plan[idx].planned_offset = 1.0 # Try Normal
            states = simulate_plan(plan)
            valid = True
            for s in states:
                if s['t_down'] < LIMIT_MIN_DOWN or s['t_dex'] < LIMIT_MIN_DEXTER:
                    valid = False
                    break
            
            if not valid:
                plan[idx].planned_offset = 4.0 # Restore Boost
            else:
                logger.info(f"Phase 4: Downgraded Boost at h={idx}. Still valid.")

        # 2. Prune Runs
        run_indices = [i for i, p in enumerate(plan) if p.planned_action == "RUN"]
        run_indices.sort(key=lambda i: plan[i].electricity_price, reverse=True)
        
        for idx in run_indices:
            old_action = plan[idx].planned_action
            old_offset = plan[idx].planned_offset
            
            plan[idx].planned_action = "REST"
            plan[idx].planned_offset = 0.0
            plan[idx].planned_gm_value = None
            
            states = simulate_plan(plan)
            valid = True
            
            for s in states:
                if s['t_down'] < LIMIT_MIN_DOWN or s['t_dex'] < LIMIT_MIN_DEXTER:
                    valid = False
                    break
            
            if not valid:
                plan[idx].planned_action = old_action
                plan[idx].planned_offset = old_offset
                if old_action == "RUN": plan[idx].planned_gm_value = -300.0
            else:
                logger.info(f"Phase 4: Pruned RUN at h={idx}. Valid & Saved Money.")

        # Final Re-Simulate
        simulate_plan(plan)

        # --- PHASE 5: HOT WATER OPTIMIZATION (Thermal Battery) ---
        # Strategy: Overcharge HW tank (Lux Mode) during cheapest hours.
        # This stores cheap energy to avoid running HW cycles during expensive peaks.
        
        # 1. Identify cheapest 3 hours
        sorted_by_price = sorted(range(len(plan)), key=lambda k: plan[k].electricity_price)
        cheapest_indices = set(sorted_by_price[:3])
        
        # 2. Identify expensive hours (> 1.4x average)
        expensive_indices = set(i for i, p in enumerate(plan) if p.electricity_price > avg_price * 1.4)
        
        for i, p in enumerate(plan):
            if i in cheapest_indices:
                # Cheap! Charge the battery!
                p.planned_hot_water_mode = 2 # LUX Mode (Higher temp target)
                logger.info(f"HW Strategy: Scheduling LUX charging at hour {i} (Price: {p.electricity_price:.2f})")
            elif i in expensive_indices:
                # Expensive! Avoid heating if possible.
                # Note: We can't force 'stop' easily on F730 without blocking, 
                # but 'Economy' mode usually lowers start temp.
                # Assuming 1 is Normal. If F730 has Economy, it might be 0.
                # Let's stick to Normal (1) to be safe, or 0 if mapped.
                # For now, just ensuring we don't accidentally do Lux.
                p.planned_hot_water_mode = 1 
            else:
                p.planned_hot_water_mode = 1 # Normal

        # 4. Atomic Save
        try:
            self.session.query(PlannedHeatingSchedule).delete()
            for p in plan:
                self.session.add(PlannedHeatingSchedule(
                    timestamp=p.timestamp, outdoor_temp=p.outdoor_temp,
                    electricity_price=p.electricity_price, simulated_indoor_temp=p.simulated_indoor_temp,
                    simulated_dexter_temp=p.simulated_dexter_temp, planned_action=p.planned_action,
                    planned_gm_value=p.planned_gm_value, planned_offset=p.planned_offset,
                    planned_hot_water_mode=p.planned_hot_water_mode, cloud_cover=p.cloud_cover,
                    solar_gain=p.solar_gain, wind_speed=p.wind_speed, wind_direction=p.wind_direction
                ))
            self.session.commit()
            logger.info(f"✓ SmartPlanner V6.0 successful. Actions planned.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Save failed: {e}")

        return plan

if __name__ == "__main__":
    planner = SmartPlanner()
    planner.plan_next_24h()