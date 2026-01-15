import sys
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
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

    def _run_physics_engine(self, plan: List[HourlyPlan], initial_down: float, initial_dex: float) -> List[Dict]:
        """
        Core Physics Simulation - SINGLE SOURCE OF TRUTH
        Returns state history for validation.
        """
        t_down = initial_down
        t_dex = initial_dex
        states = []
        
        # Params
        base_curve = settings.DEFAULT_HEATING_CURVE
        shunt_limit = self.tuning.get('actual_shunt_limit', 29.0)
        leak_down = self.tuning['thermal_leakage']
        leak_dex = self.tuning.get('thermal_leakage_dexter', leak_down)
        slab_eff = self.tuning['slab_efficiency']
        rad_eff = self.tuning['rad_efficiency']
        wind_sens_down = self.tuning.get('wind_sensitivity', 0.005)
        wind_sens_dex = self.tuning.get('wind_sensitivity_dexter', 0.005)
        trans_coeff = self.tuning.get('inter_zone_transfer', 0.005)
        
        solar_c_down = self.tuning['solar_gain_coeff']
        solar_c_dex = self.tuning.get('solar_gain_dexter', solar_c_down)
        int_down = self.tuning.get('internal_heat_gain', 0.015)
        int_dex = self.tuning.get('internal_gain_dexter', 0.015)

        for p in plan:
            # 1. Supply Temp
            curve_supply = 20 + ((20 - p.outdoor_temp) * base_curve * 0.12)
            offset = p.planned_offset if p.planned_action == "RUN" else 0.0
            target_supply = curve_supply + offset
            
            # 2. Constraints
            supply_down = min(target_supply, shunt_limit)
            supply_dex = target_supply
            
            # 3. Heat Input (Power Law)
            gain_down = 0.0
            gain_dex = 0.0
            if p.planned_action == "RUN":
                # Using 1.1 exponent for slab (radiant) and 1.3 for radiator (convective)
                dT_down = max(0, supply_down - t_down)
                dT_dex = max(0, supply_dex - t_dex)
                gain_down = slab_eff * (dT_down ** 1.1)
                gain_dex = rad_eff * (dT_dex ** 1.3)

            # 4. Losses (Square Law Wind)
            w_fac = self._get_wind_factor(p.wind_direction)
            wd_imp_d = (p.wind_speed ** 2) * wind_sens_down
            wd_imp_x = (p.wind_speed ** 2) * wind_sens_dex
            
            loss_down = (t_down - p.outdoor_temp) * leak_down * (1 + wd_imp_d)
            loss_dex = (t_dex - p.outdoor_temp) * leak_dex * w_fac * (1 + wd_imp_x)
            
            # 5. Transfer
            trans = (t_down - t_dex) * trans_coeff
            
            # 6. Ext Gains
            sol_d = (p.solar_gain * (solar_c_down / 0.04))
            sol_x = (p.solar_gain * (solar_c_dex / 0.04))
            
            # Update
            t_down += gain_down - loss_down - trans + sol_d + int_down
            t_dex += gain_dex + trans - loss_dex + sol_x + int_dex
            
            # Store
            p.simulated_indoor_temp = t_down
            p.simulated_dexter_temp = t_dex
            p.predicted_supply = supply_dex
            
            states.append({'t_down': t_down, 't_dex': t_dex})
            
        return states

    def plan_next_24h(self) -> List[HourlyPlan]:
        logger.info("Starting SmartPlanner V7.0 (Granular Optimization) - Audit Build")

        if not self.device:
            self.device = self.analyzer.get_device()
            if not self.device: return []

        # --- INITIALIZATION ---
        current_indoor_temp = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_HA_TEMP_DOWNSTAIRS) or 21.0
        current_dexter_temp = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_HA_TEMP_DEXTER) or current_indoor_temp
        
        # Constraints
        LIMIT_MIN_DOWN = 20.5
        LIMIT_TARGET_DOWN_MAX = 22.0
        LIMIT_MIN_DEXTER = 20.0
        
        # Data Fetching (Weather/Price) - [Same as V6 logic, abbreviated for clarity]
        weather_forecast = self.weather_service.get_forecast(hours_ahead=48)
        weather_forecast_dict = {f.timestamp.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat(): f for f in weather_forecast}
        avg_temp_baseline = sum([f.temperature for f in weather_forecast[:24]]) / max(1, len(weather_forecast[:24]))
        
        price_forecast_today = self.price_service.get_prices_today()
        price_forecast_tomorrow = self.price_service.get_prices_tomorrow()
        price_forecast_yesterday = self.price_service.get_prices_yesterday() # For fallback
        
        all_prices_data = {}
        for p in price_forecast_yesterday + price_forecast_today + price_forecast_tomorrow:
            utc_key = p.time_start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
            all_prices_data[utc_key] = p.price_per_kwh
            
        current_prices = [p.price_per_kwh for p in price_forecast_today + price_forecast_tomorrow]
        if not current_prices: current_prices = [1.0]
        
        # Calculate Price Percentiles for "Economy" logic
        sorted_prices = sorted(current_prices)
        price_low_threshold = sorted_prices[int(len(sorted_prices) * 0.33)] # Bottom 33%
        avg_price = sum(current_prices) / len(current_prices)

        # Build Initial Plan (REST)
        plan: List[HourlyPlan] = []
        current_hour_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        for i in range(25):
            current_time = current_hour_start + timedelta(hours=i)
            iso_ts = current_time.isoformat()
            forecast = weather_forecast_dict.get(iso_ts)
            
            # Defaults
            out_temp = forecast.temperature if forecast else 0.0
            wind_speed = forecast.wind_speed if forecast else 0.0
            wind_dir = forecast.wind_direction if forecast else 0
            
            # Price Prediction (V6 Logic)
            price = all_prices_data.get(iso_ts)
            if price is None:
                fallback_ts = (current_time - timedelta(days=1)).isoformat()
                base_price = all_prices_data.get(fallback_ts, avg_price)
                sens = self.tuning.get('price_wind_sensitivity', 0.0)
                wind_drop = (wind_speed * sens) if sens > 0 else 0
                weekend_factor = 1.0
                if current_time.weekday() >= 5: weekend_factor = self.tuning.get('weekend_discount_factor', 0.90)
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
                solar_gain=0.0, # Simplified solar logic handling inside physics engine via coeff
                planned_action="REST",
                planned_offset=0.0
            ))
            
            # Re-inject solar gain data if available in forecast object (hack for clean passing)
            # Actually, calculate it here:
            if 11 <= current_time.hour <= 17 and forecast and forecast.cloud_cover < 4:
                plan[-1].solar_gain = (4 - forecast.cloud_cover)

        # ====================================================================
        # OPTIMIZATION LOOP V7: GRANULAR INCREMENTAL
        # ====================================================================
        
        # Phase 1: Satisfy Minimum Constraints (Time Priority)
        # Strategy: Add hours (Offset 1) until constraints met.
        
        offset = self.device.comfort_adjustment_offset or 0.0
        
        iterations = 0
        while iterations < 40:
            states = self._run_physics_engine(plan, current_indoor_temp, current_dexter_temp)
            
            # Check Failure
            fail_idx = -1
            for i, s in enumerate(states):
                # Dynamic target based on price penalty (max 0.5C)
                pen = 0.5 if (plan[i].electricity_price / avg_price) > 1.5 else 0.0
                if s['t_down'] < (LIMIT_MIN_DOWN + offset - pen) or s['t_dex'] < (LIMIT_MIN_DEXTER + offset - pen):
                    fail_idx = i
                    break
            
            if fail_idx == -1:
                break # Safe
            
            # Fix: Add Offset 1 to cheapest REST hour before failure
            candidates = [i for i in range(fail_idx + 1) if plan[i].planned_action == "REST"]
            
            if candidates:
                # Pick cheapest (with Continuity Bonus)
                # Strategy: Score = Price - Bonus. 
                # Bonus if neighbor (prev/next) is RUN.
                candidates_scored = []
                for idx in candidates:
                    score = plan[idx].electricity_price
                    
                    # Check neighbors
                    is_neighbor_run = False
                    if idx > 0 and plan[idx-1].planned_action == "RUN": is_neighbor_run = True
                    if idx < len(plan)-1 and plan[idx+1].planned_action == "RUN": is_neighbor_run = True
                    
                    if is_neighbor_run:
                        # Apply bonus (equivalent to price being 20% cheaper)
                        score *= 0.8 
                    
                    candidates_scored.append((idx, score))
                
                best_idx = min(candidates_scored, key=lambda x: x[1])[0]
                
                # Action: Normal efficient run
                plan[best_idx].planned_action = "RUN"
                plan[best_idx].planned_offset = 1.0
                plan[best_idx].planned_gm_value = -300.0
                iterations += 1
                continue
            
            # Phase 2: Power Up (Granular Boost)
            # If we have no more hours to add (all RUN), we must increase power.
            # Find cheapest RUN hour that isn't maxed out (Offset < 4)
            boost_candidates = [i for i in range(fail_idx + 1) 
                                if plan[i].planned_action == "RUN" and plan[i].planned_offset < 4.0]
            
            if not boost_candidates:
                logger.warning(f"Cannot satisfy hour {fail_idx}. System Maxed (Offset 4 everywhere).")
                break
                
            best_boost_idx = min(boost_candidates, key=lambda i: plan[i].electricity_price)
            # Increment Offset
            plan[best_boost_idx].planned_offset += 1.0
            iterations += 1
            logger.info(f"Boosting hour {best_boost_idx} to Offset {plan[best_boost_idx].planned_offset}")

        # Phase 3: Economy Buffering (Fill cheap hours)
        # Strategy: If price is low (bottom 33%), add Offset 1 if safe.
        
        for i, p in enumerate(plan):
            if p.planned_action == "REST" and p.electricity_price <= price_low_threshold:
                # Speculative Enable
                p.planned_action = "RUN"
                p.planned_offset = 1.0
                p.planned_gm_value = -300.0
                
                states = self._run_physics_engine(plan, current_indoor_temp, current_dexter_temp)
                
                # Check Overheat
                if states[i]['t_down'] > LIMIT_TARGET_DOWN_MAX:
                    p.planned_action = "REST"
                    p.planned_offset = 0.0
                    p.planned_gm_value = None
                else:
                    logger.info(f"Economy Charge at hour {i} (Price: {p.electricity_price:.2f})")

        # Phase 4: Pruning (Cost Optimization)
        # Strategy: Try reducing offsets or turning off hours to save money
        
        # Get all RUN hours
        run_indices = [i for i, p in enumerate(plan) if p.planned_action == "RUN"]
        
        def pruning_priority(i):
            # Base priority is price (Higher price = Higher priority to prune)
            score = plan[i].electricity_price
            
            # Check for Island (neighbors are REST)
            # If island, boost score to make it more likely to be pruned
            is_island = True
            if i > 0 and plan[i-1].planned_action == "RUN": is_island = False
            if i < 24 and plan[i+1].planned_action == "RUN": is_island = False
            
            if is_island:
                score *= 1.5 # 50% "Prune Bonus" for islands
            
            return score

        run_indices.sort(key=pruning_priority, reverse=True)
        
        for idx in run_indices:
            original_offset = plan[idx].planned_offset
            
            # Try reducing by 1.0 (or to 0/REST)
            # We loop down: 4->3, 3->2, 2->1, 1->REST
            
            # For simplicity in V7, just try turning OFF first.
            # If fail, try reducing offset to 1.0 if it was high.
            
            # Attempt 1: Turn OFF
            plan[idx].planned_action = "REST"
            plan[idx].planned_offset = 0.0
            
            states = self._run_physics_engine(plan, current_indoor_temp, current_dexter_temp)
            valid = True
            for i, s in enumerate(states):
                pen = 0.5 if (plan[i].electricity_price / avg_price) > 1.5 else 0.0
                if s['t_down'] < (LIMIT_MIN_DOWN + offset - pen) or s['t_dex'] < (LIMIT_MIN_DEXTER + offset - pen):
                    valid = False
                    break
            
            if valid:
                logger.info(f"Pruned hour {idx} to REST. Valid.")
                continue # Success
            
            # Attempt 2: If it was high offset, try Offset 1.0
            if original_offset > 1.0:
                plan[idx].planned_action = "RUN"
                plan[idx].planned_offset = 1.0
                
                states = self._run_physics_engine(plan, current_indoor_temp, current_dexter_temp)
                valid = True
                for i, s in enumerate(states):
                    pen = 0.5 if (plan[i].electricity_price / avg_price) > 1.5 else 0.0
                    if s['t_down'] < (LIMIT_MIN_DOWN + offset - pen) or s['t_dex'] < (LIMIT_MIN_DEXTER + offset - pen):
                        valid = False
                        break
                
                if valid:
                    logger.info(f"Reduced hour {idx} from Offset {original_offset} to 1.0. Valid.")
                    continue
            
            # Restore original
            plan[idx].planned_action = "RUN"
            plan[idx].planned_offset = original_offset
            plan[idx].planned_gm_value = -300.0

        # Phase 5: Hot Water
        sorted_by_price = sorted(range(len(plan)), key=lambda k: plan[k].electricity_price)
        cheapest_3 = set(sorted_by_price[:3])
        expensive_indices = set(i for i, p in enumerate(plan) if p.electricity_price > avg_price * 1.4)
        
        for i, p in enumerate(plan):
            if i in cheapest_3: p.planned_hot_water_mode = 2
            elif i in expensive_indices: p.planned_hot_water_mode = 1 # Keep normal to avoid cold water
            else: p.planned_hot_water_mode = 1

        # 4. Save
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
            logger.info(f"✓ SmartPlanner V7.0 successful.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Save failed: {e}")

        return plan

if __name__ == "__main__":
    planner = SmartPlanner()
    planner.plan_next_24h()
