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
                'actual_shunt_limit': 32.0
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
        logger.info("Starting SmartPlanner 4.0 (Adaptive Multi-Zone logic)...")

        if not self.device:
            self.device = self.analyzer.get_device()
            if not self.device: return []

        # 1. Fetch current context
        current_indoor_temp = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_HA_TEMP_DOWNSTAIRS) or 21.0
        current_dexter_temp = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_HA_TEMP_DEXTER) or current_indoor_temp

        target_min_temp = self.device.target_indoor_temp_min or 21.0
        
        weather_forecast = self.weather_service.get_forecast(hours_ahead=48)
        weather_forecast_dict = {f.timestamp.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat(): f for f in weather_forecast}
        
        price_forecast_today = self.price_service.get_prices_today()
        price_forecast_tomorrow = self.price_service.get_prices_tomorrow()
        all_prices_data: Dict[str, float] = {}
        for p in price_forecast_today + price_forecast_tomorrow:
            utc_key = p.time_start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
            all_prices_data[utc_key] = p.price_per_kwh
            
        avg_price = sum(all_prices_data.values()) / len(all_prices_data) if all_prices_data else 1.0
        
        plan: List[HourlyPlan] = []
        current_hour_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        # 2. Build Environmental Plan
        for i in range(25):
            current_time = current_hour_start + timedelta(hours=i)
            iso_ts = current_time.isoformat()
            forecast = weather_forecast_dict.get(iso_ts)
            
            out_temp = forecast.temperature if forecast else 0.0
            humidity = forecast.humidity if forecast else 50.0
            wind_speed = forecast.wind_speed if forecast else 0.0
            wind_dir = forecast.wind_direction if forecast else 0
            price = all_prices_data.get(iso_ts, avg_price)
            
            # --- COP SHIELD (Defrost Penalty) ---
            if out_temp < 5.0 and humidity > 80.0:
                price *= 1.20 

            solar_gain = 0.0
            if 11 <= current_time.hour <= 17 and forecast and forecast.cloud_cover < 4:
                solar_gain = (4 - forecast.cloud_cover) * self.tuning.get('solar_gain_coeff', 0.04)

            plan.append(HourlyPlan(
                timestamp=current_time,
                outdoor_temp=out_temp,
                electricity_price=price,
                wind_speed=wind_speed,
                wind_direction=wind_dir,
                solar_gain=solar_gain,
                planned_action="REST",
                planned_offset=0.0,
                planned_hot_water_mode=1
            ))

        # 3. Iterative Optimization
        simulation_ok = False
        hours_added = 0
        shunt_limit = self.tuning.get('actual_shunt_limit', 32.0)
        base_curve = settings.DEFAULT_HEATING_CURVE

        while not simulation_ok and hours_added < 25:
            cur_down = current_indoor_temp
            cur_dexter = current_dexter_temp
            worst_fail_idx = -1
            
            for i, p_hour in enumerate(plan):
                if p_hour.planned_action == "RUN":
                    if cur_dexter < 19.8: p_hour.planned_offset = 4.0
                    else: p_hour.planned_offset = 0.0
                
                active_offset = p_hour.planned_offset if p_hour.planned_action == "REST" else (p_hour.planned_offset or 3.0)
                predicted_supply = (base_curve * (20 - p_hour.outdoor_temp) * 0.15) + 22 + active_offset
                
                # Cooling Physics (Wind-aware)
                wind_factor = self._get_wind_factor(p_hour.wind_direction)
                loss_down = (cur_down - p_hour.outdoor_temp) * self.tuning['thermal_leakage']
                loss_dexter = (cur_dexter - p_hour.outdoor_temp) * self.tuning['thermal_leakage'] * 1.3 * wind_factor * (1 + p_hour.wind_speed * self.tuning['wind_sensitivity'])
                
                if p_hour.planned_action == "RUN":
                    eff_supply_down = min(predicted_supply, shunt_limit)
                    gain_down = max(0, (eff_supply_down - cur_down) * self.tuning['slab_efficiency'])
                    gain_dexter = max(0, (predicted_supply - cur_dexter) * self.tuning['rad_efficiency'])
                    cur_down += gain_down
                    cur_dexter += gain_dexter
                else:
                    cur_down -= loss_down
                    cur_dexter -= loss_dexter
                
                cur_down += p_hour.solar_gain + self.tuning.get('internal_heat_gain', 0.015)
                cur_dexter += p_hour.solar_gain + self.tuning.get('internal_heat_gain', 0.015)
                
                # Failure detection
                dyn_min_down = target_min_temp - (0.5 if (p_hour.electricity_price / avg_price) > 1.5 else 0)
                dyn_min_dexter = 19.5 - (0.8 if (p_hour.electricity_price / avg_price) > 1.5 else 0)
                
                if (cur_down < dyn_min_down or cur_dexter < dyn_min_dexter) and worst_fail_idx == -1:
                    worst_fail_idx = i

            if worst_fail_idx == -1:
                simulation_ok = True
            else:
                candidates = []
                for j in range(worst_fail_idx + 1):
                    if plan[j].planned_action == "REST":
                        candidates.append((j, plan[j].electricity_price))
                
                if not candidates: simulation_ok = True
                else:
                    best_idx = min(candidates, key=lambda x: x[1])[0]
                    plan[best_idx].planned_action = "RUN"
                    plan[best_idx].planned_gm_value = 60.0
                    hours_added += 1

        # Final Pass for Simulated UI Values
        cur_down = current_indoor_temp
        cur_dexter = current_dexter_temp
        for p_hour in plan:
            active_offset = p_hour.planned_offset if p_hour.planned_action == "REST" else (p_hour.planned_offset or 3.0)
            predicted_supply = (base_curve * (20 - p_hour.outdoor_temp) * 0.15) + 22 + active_offset
            wind_factor = self._get_wind_factor(p_hour.wind_direction)
            if p_hour.planned_action == "RUN":
                eff_supply_down = min(predicted_supply, shunt_limit)
                cur_down += max(0, (eff_supply_down - cur_down) * self.tuning['slab_efficiency'])
                cur_dexter += max(0, (predicted_supply - cur_dexter) * self.tuning['rad_efficiency'])
            else:
                loss_down = (cur_down - p_hour.outdoor_temp) * self.tuning['thermal_leakage']
                loss_dexter = (cur_dexter - p_hour.outdoor_temp) * self.tuning['thermal_leakage'] * 1.3 * wind_factor * (1 + p_hour.wind_speed * self.tuning['wind_sensitivity'])
                cur_down -= loss_down
                cur_dexter -= loss_dexter
            cur_down += p_hour.solar_gain + self.tuning.get('internal_heat_gain', 0.015)
            cur_dexter += p_hour.solar_gain + self.tuning.get('internal_heat_gain', 0.015)
            p_hour.simulated_indoor_temp = cur_down
            p_hour.simulated_dexter_temp = cur_dexter

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
            logger.info(f"✓ SmartPlanner 4.0 successful. Added {hours_added} hours.")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Save failed: {e}")

        return plan

if __name__ == "__main__":
    planner = SmartPlanner()
    planner.plan_next_24h()
