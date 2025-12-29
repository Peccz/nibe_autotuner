import sys
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from loguru import logger
from pydantic import BaseModel
import random 

from data.database import SessionLocal
from data.models import Device, Parameter, ParameterReading, GMAccount, PlannedHeatingSchedule
from services.analyzer import HeatPumpAnalyzer
from services.weather_service import SMHIWeatherService
from services.price_service import PriceService
from services.learning_service import LearningService
from services.hw_analyzer import HotWaterPatternAnalyzer 
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth
from core.config import settings


class HourlyPlan(BaseModel):
    timestamp: datetime
    outdoor_temp: float
    electricity_price: float
    cloud_cover: float = 8.0
    solar_gain: float = 0.0 # Degrees C per hour gained from sun
    simulated_indoor_temp: Optional[float] = None
    planned_action: str # "MUST_RUN", "MUST_REST", "RUN", "REST", "HOLD"
    planned_gm_value: Optional[float] = None # GM value to write to pump (40940)
    planned_offset: Optional[float] = 0.0 
    planned_hot_water_mode: Optional[int] = 1 # 0, 1, 2

class SmartPlanner:
    def __init__(self):
        self.session = SessionLocal()
        self.analyzer = HeatPumpAnalyzer()
        self.weather_service = SMHIWeatherService()
        self.price_service = PriceService()
        self.learning_service = LearningService(self.session, self.analyzer)
        self.hw_analyzer = HotWaterPatternAnalyzer() 
        
        # Get device for all operations
        self.device = self.analyzer.get_device()
        
        # Constants are now fetched from settings.py
        self.K_GM_PER_DELTA_T_PER_H = settings.K_GM_PER_DELTA_T_PER_H
        self.COMPRESSOR_HEAT_OUTPUT_C_PER_H = settings.COMPRESSOR_HEAT_OUTPUT_C_PER_H
        self.GM_PRODUCTION_PER_HOUR_RUNNING = settings.GM_PRODUCTION_PER_HOUR_RUNNING
        self.OUTDOOR_TEMP_OFFSET_C = settings.OUTDOOR_TEMP_OFFSET_C

    def calculate_real_world_metrics(self) -> Dict:
        """Analyze recent history to find real heating/cooling rates"""
        if not self.device: return {}
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=6)
        
        try:
            indoor_readings = self.analyzer.get_readings(self.device, self.analyzer.PARAM_INDOOR_TEMP, start_time, end_time)
            if len(indoor_readings) < 2: return {}
            
            total_change = indoor_readings[-1][1] - indoor_readings[0][1]
            hours = (indoor_readings[-1][0] - indoor_readings[0][0]).total_seconds() / 3600
            rate = total_change / hours if hours > 0 else 0
            
            logger.info(f"REALITY CHECK (6h): Indoor temp changed {total_change:.1f}C in {hours:.1f}h. Rate: {rate:.2f} C/h")
            return {'rate_6h': rate}
        except Exception as e:
            logger.warning(f"Reality check failed: {e}")
            return {}

    def plan_next_24h(self) -> List[HourlyPlan]:
        logger.info("Starting new 24h heating plan...")

        if not self.device:
            self.device = self.analyzer.get_device()
            if not self.device:
                logger.error("No device found for SmartPlanner. Aborting.")
                return []

        # Run Reality Check
        self.calculate_real_world_metrics()

        # 1. Fetch current context
        current_metrics = self.analyzer.calculate_metrics(hours_back=1)
        current_indoor_temp = current_metrics.avg_indoor_temp if current_metrics and current_metrics.avg_indoor_temp else None
        
        if current_indoor_temp is None:
            latest = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_INDOOR_TEMP)
            if latest is not None:
                current_indoor_temp = latest
                logger.warning(f"Using latest known indoor temp (older than 1h): {latest}°C")

        # Get Current HW Temp
        hw_temp = self.analyzer.get_latest_value(self.device, '40013') 
        if hw_temp is None: hw_temp = 50.0 

        # Get Comfort Targets
        min_safety_temp = self.device.min_indoor_temp_user_setting
        target_min_temp = self.device.target_indoor_temp_min
        target_max_temp = self.device.target_indoor_temp_max

        if not all([min_safety_temp, target_min_temp, target_max_temp]):
            logger.error("Comfort settings missing. Cannot plan.")
            return []

        # Get Weather and Price Forecast
        weather_forecast = self.weather_service.get_forecast(hours_ahead=48)
        weather_forecast_dict = {f.timestamp.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat(): f for f in weather_forecast}
        
        price_forecast_raw = self.price_service.get_prices_tomorrow()
        price_forecast_today = self.price_service.get_prices_today()
        all_prices_data: Dict[str, float] = {}
        for p in price_forecast_today + price_forecast_raw:
            # Use ISO format of the hour in UTC as key to prevent day-overwriting-day
            utc_key = p.time_start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
            all_prices_data[utc_key] = p.price_per_kwh
            
        # Calculate avg price for HW logic
        avg_price = sum(all_prices_data.values()) / len(all_prices_data) if all_prices_data else 0.5
        
        # Get thermal inertia
        inertia = self.learning_service.analyze_thermal_inertia()
        cooling_rate_0c = inertia.get('cooling_rate_0c', -0.11) # Numerically calibrated fallback

        logger.info(f"Current Indoor: {current_indoor_temp:.1f}°C. HW Temp: {hw_temp:.1f}°C. Targets: {min_safety_temp:.1f}-{target_min_temp:.1f}-{target_max_temp:.1f}°C")

        plan: List[HourlyPlan] = []
        next_full_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        # 2. Build Basic Plan Objects (Weather, Price, HW Logic)
        for i in range(24):
            current_planning_time = next_full_hour + timedelta(hours=i)
            
            # Weather
            iso_ts = current_planning_time.isoformat()
            # ... (weather logic stays same) ...
            outdoor_temp_hour = 0.0
            cloud_cover_hour = 8.0 # Default cloudy
            if iso_ts in weather_forecast_dict:
                 outdoor_temp_hour = weather_forecast_dict[iso_ts].temperature
                 cloud_cover_hour = weather_forecast_dict[iso_ts].cloud_cover
            else:
                 closest = min(weather_forecast, key=lambda x: abs((x.timestamp.replace(tzinfo=timezone.utc) - current_planning_time).total_seconds())) if weather_forecast else None
                 if closest: 
                     outdoor_temp_hour = closest.temperature
                     cloud_cover_hour = getattr(closest, 'cloud_cover', 8.0)
            
            # Apply Weather Correction (Sensor Deviation)
            outdoor_temp_hour += self.OUTDOOR_TEMP_OFFSET_C
            
            # Dynamic Solar Correction for Western facade sensor (afternoons)
            solar_gain_c = 0.0
            if 12 <= current_planning_time.hour <= 19:
                if cloud_cover_hour < 4: # Clear to Half-clear (0-8 scale)
                    # Reduced correction: Up to 8 degrees adjustment (was 20, which was too aggressive)
                    # Scale: 0 clouds -> 8C, 4 clouds -> 0C. Factor = 2.0.
                    solar_spike = (4 - cloud_cover_hour) * 2.0 
                    
                    # 1. Correct sensor error (Pump should calculate loss based on REAL air temp)
                    outdoor_temp_hour -= solar_spike
                    
                    # 2. Add Passive Solar Heat Gain to House
                    # Hypothesis: A 20C sensor spike corresponds to ~0.8C/h passive heating
                    solar_gain_c = solar_spike * 0.04

                    # Log significant corrections
                    if solar_spike > 2.0:
                        logger.info(f"  SOLAR {current_planning_time.hour}:00 | Spike:+{solar_spike:.1f}C | Gain:+{solar_gain_c:.2f}C/h")
            
            # Price
            price_key = current_planning_time.isoformat()
            electricity_price_hour = all_prices_data.get(price_key, 0.5)
            
            # --- HOT WATER STRATEGY (Proactive) ---
            hw_mode = 1 # Default Normal
            hour = current_planning_time.hour
            hw_prob = self.hw_analyzer.get_usage_probability(current_planning_time)
            
            # 1. Critical Boost (Reactive) - Only applied to first hour based on sensor
            is_boost_needed = False
            if i == 0:
                if hw_temp < 42.0: is_boost_needed = True
                elif hw_temp < 47.0 and hw_prob > 0.2: is_boost_needed = True
            
            # 2. Afternoon Charge (Proactive) - 13:00 to 16:00
            is_preheat_time = 13 <= hour <= 16
            is_price_ok_for_preheat = electricity_price_hour < avg_price * 1.15
            
            # 3. Evening Safety (Risk Management) - 17:00 to 21:00
            is_high_risk_time = 17 <= hour <= 21
            
            # 4. General Price Logic
            is_cheap = electricity_price_hour < avg_price * 0.8
            is_expensive = electricity_price_hour > avg_price * 1.2

            # Decision Logic (Priority Order)
            if is_boost_needed:
                hw_mode = 2 # Lux (Critical)
            elif is_preheat_time and is_price_ok_for_preheat:
                hw_mode = 2 # Lux (Pre-load)
            elif is_cheap:
                hw_mode = 2 # Lux (Opportunity)
            elif is_high_risk_time:
                hw_mode = 1 # Normal (Safety floor)
            elif is_expensive:
                hw_mode = 0 # Eco (Savings)
            else:
                hw_mode = 1 # Normal
            
            plan.append(HourlyPlan(
                timestamp=current_planning_time,
                outdoor_temp=outdoor_temp_hour,
                electricity_price=electricity_price_hour,
                cloud_cover=cloud_cover_hour,
                solar_gain=solar_gain_c,
                simulated_indoor_temp=current_indoor_temp, # Placeholder
                planned_action="REST", # Start with ALL REST
                planned_gm_value=0, 
                planned_offset=0.0,
                planned_hot_water_mode=hw_mode
            ))

        # --- OPTIMIZATION: Causal Iterative Pre-heating ---
        # Strategy: Add heating hours one by one, prioritizing CHEAPEST hours that occur BEFORE the point where
        # temperature drops below target. This solves the "23 hour run" bug where it optimized irrelevant hours.
        
        simulation_ok = False
        hours_added = 0
        
        # Max loop 24 times (worst case: run 24h)
        while not simulation_ok and hours_added <= 24:
            # 1. Run Simulation with current plan configuration
            temp = current_indoor_temp
            min_temp_val = 100.0
            min_temp_idx = -1
            
            for i, p_hour in enumerate(plan):
                outdoor = p_hour.outdoor_temp
                effective_cooling_rate = cooling_rate_0c * (1 + (0 - outdoor) / 10)
                
                if p_hour.planned_action == "RUN":
                    temp += self.COMPRESSOR_HEAT_OUTPUT_C_PER_H
                else:
                    temp += effective_cooling_rate
                
                # Add Passive Solar Gain
                temp += p_hour.solar_gain
                
                # Clamp temp (Physics limits)
                temp = min(target_max_temp + 5.0, temp) 
                
                # Check for deepest dip
                if temp < min_temp_val:
                    min_temp_val = temp
                    min_temp_idx = i
            
            # 2. Check Constraint
            # If the lowest temp reached is above target, we are done.
            if min_temp_val >= target_min_temp:
                simulation_ok = True
                logger.info(f"Optimization complete! Min temp {min_temp_val:.2f}C >= Target {target_min_temp}C with {hours_added} run-hours.")
            else:
                # 3. Constraint failed. We need to heat.
                # Find available (REST) hours in the range [0, min_temp_idx].
                # We prioritize cheapest hours in this range to pre-heat effectively.
                
                candidates = []
                for i in range(min_temp_idx + 1):
                    if plan[i].planned_action == "REST":
                        candidates.append((i, plan[i].electricity_price))
                
                if not candidates:
                    # No available slots before the dip?
                    # This means we are running full blast up to the dip and still failing.
                    # Adding heat LATER won't fix this dip.
                    logger.warning(f"Cannot prevent dip at hour {min_temp_idx} by pre-heating (all prior hours running). Accepting plan as best effort.")
                    simulation_ok = True # Break loop
                else:
                    # Pick cheapest candidate causing/preceding the dip
                    best_idx = min(candidates, key=lambda x: x[1])[0]
                    plan[best_idx].planned_action = "RUN"
                    plan[best_idx].planned_gm_value = self.GM_PRODUCTION_PER_HOUR_RUNNING
                    hours_added += 1

        # 4. Finalize simulation values for graphing/logging
        simulated_indoor_temp = current_indoor_temp
        for p_hour in plan:
            outdoor_temp_hour = p_hour.outdoor_temp
            effective_cooling_rate = cooling_rate_0c * (1 + (0 - outdoor_temp_hour) / 10) 

            if p_hour.planned_action == "RUN":
                simulated_indoor_temp += self.COMPRESSOR_HEAT_OUTPUT_C_PER_H
            else: 
                simulated_indoor_temp += effective_cooling_rate
            
            # Add Passive Solar Gain
            simulated_indoor_temp += p_hour.solar_gain
            
            # Clamp for display
            simulated_indoor_temp = max(min_safety_temp - 2.0, min(target_max_temp + 2.0, simulated_indoor_temp))
            p_hour.simulated_indoor_temp = simulated_indoor_temp

        # Log and store
        logger.info("\n--- 24h Heating Plan (Causal Optimization) ---")
        for p_hour in plan:
            hw_str = ["ECO", "NORMAL", "LUX"][p_hour.planned_hot_water_mode]
            solar_str = f" | Sun:+{p_hour.solar_gain:.2f}" if p_hour.solar_gain > 0 else ""
            logger.info(f"{p_hour.timestamp.strftime('%H:%M')}: {p_hour.planned_action:<10} | "
                        f"InneSim:{p_hour.simulated_indoor_temp:5.1f}°C | Pris:{p_hour.electricity_price:.2f} | HW: {hw_str}{solar_str}")
        
        # Save to DB
        self.session.query(PlannedHeatingSchedule).delete()
        self.session.commit()
        
        for p_hour in plan:
            schedule_entry = PlannedHeatingSchedule(
                timestamp=p_hour.timestamp,
                outdoor_temp=p_hour.outdoor_temp,
                electricity_price=p_hour.electricity_price,
                simulated_indoor_temp=p_hour.simulated_indoor_temp,
                planned_action=p_hour.planned_action,
                planned_gm_value=p_hour.planned_gm_value,
                planned_offset=p_hour.planned_offset,
                planned_hot_water_mode=p_hour.planned_hot_water_mode 
            )
            self.session.add(schedule_entry)
        self.session.commit()
        logger.info("✓ 24h Heating Plan saved to database.")

        return plan

if __name__ == "__main__":
    logger.add(sys.stderr, format="{time} {level} {message}", level="INFO")
    planner = SmartPlanner()
    try:
        planner.plan_next_24h()
    except Exception as e:
        logger.error(f"SmartPlanner failed: {e}")
        import traceback
        traceback.print_exc()
