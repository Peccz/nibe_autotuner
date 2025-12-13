from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from loguru import logger
from pydantic import BaseModel
import random # For simulating weather if not available

from data.database import SessionLocal
from data.models import Device, Parameter, ParameterReading, GMAccount, PlannedHeatingSchedule
from services.analyzer import HeatPumpAnalyzer
from services.weather_service import SMHIWeatherService # FIXED IMPORT
from services.price_service import PriceService
from services.learning_service import LearningService
from integrations.api_client import MyUplinkClient
from integrations.auth import MyUplinkAuth
from core.config import settings


class HourlyPlan(BaseModel):
    timestamp: datetime
    outdoor_temp: float
    electricity_price: float
    simulated_indoor_temp: Optional[float] = None
    planned_action: str # "MUST_RUN", "MUST_REST", "RUN", "REST", "HOLD"
    planned_gm_value: Optional[float] = None # GM value to write to pump (40940)

class SmartPlanner:
    def __init__(self):
        self.session = SessionLocal()
        self.analyzer = HeatPumpAnalyzer()
        self.weather_service = SMHIWeatherService() # FIXED INSTANTIATION
        self.price_service = PriceService()
        self.learning_service = LearningService(self.session, self.analyzer)
        
        # Get device for all operations
        self.device = self.analyzer.get_device()
        if not self.device:
            # Fallback handling if device not found immediately (e.g. first run)
            logger.warning("No device found in DB for SmartPlanner. Retrying via analyzer.")
            # self.device remains None, methods should handle it
        
        # Constants (can be moved to settings eventually)
        self.K_GM_PER_DELTA_T_PER_H = getattr(settings, 'K_GM_PER_DELTA_T_PER_H', 4.0) 
        self.COMPRESSOR_HEAT_OUTPUT_C_PER_H = getattr(settings, 'COMPRESSOR_HEAT_OUTPUT_C_PER_H', 0.5)
        self.GM_PRODUCTION_PER_HOUR_RUNNING = getattr(settings, 'GM_PRODUCTION_PER_HOUR_RUNNING', 60.0)

    def plan_next_24h(self) -> List[HourlyPlan]:
        logger.info("Starting new 24h heating plan...")

        # Refresh device just in case
        if not self.device:
            self.device = self.analyzer.get_device()
            if not self.device:
                logger.error("No device found for SmartPlanner. Aborting.")
                return []

        # 1. Fetch current context
        current_metrics = self.analyzer.calculate_metrics(hours_back=1)
        current_indoor_temp = current_metrics.avg_indoor_temp if current_metrics else None
        
        # Fallback if no indoor temp reading
        if current_indoor_temp is None:
            current_indoor_temp = self.device.target_indoor_temp_min # Assume target if unknown
            logger.warning(f"Could not get current indoor temp. Assuming target: {current_indoor_temp:.1f}°C")

        # Get Comfort Targets
        min_safety_temp = self.device.min_indoor_temp_user_setting
        target_min_temp = self.device.target_indoor_temp_min
        target_max_temp = self.device.target_indoor_temp_max

        if not all([min_safety_temp, target_min_temp, target_max_temp]):
            logger.error("Comfort settings missing. Cannot plan.")
            return []

        # Get Weather and Price Forecast
        # FIXED: Use 'hours_ahead' instead of 'hours'
        weather_forecast = self.weather_service.get_forecast(hours_ahead=48) 
        
        # Convert weather_forecast to a dict for easier lookup
        weather_forecast_dict = {f.timestamp.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc).isoformat(): f for f in weather_forecast}
        
        price_forecast_raw = self.price_service.get_prices_tomorrow() # Get tomorrow's prices
        price_forecast_today = self.price_service.get_prices_today() # Get rest of today's prices
        
        # Combine and align prices by hour
        all_prices_data: Dict[int, float] = {}
        for p in price_forecast_today + price_forecast_raw:
            all_prices_data[p.time_start.hour] = p.price_per_kwh
        
        # Get thermal inertia (cooling rate)
        inertia = self.learning_service.analyze_thermal_inertia()
        cooling_rate_0c = inertia.get('cooling_rate_0c', -0.15) # C/h at 0C outdoor temp (fallback)

        logger.info(f"Current Indoor: {current_indoor_temp:.1f}°C. Targets: {min_safety_temp:.1f}-{target_min_temp:.1f}-{target_max_temp:.1f}°C")
        logger.info(f"Cooling Rate (0C): {cooling_rate_0c:.2f} C/h")

        plan: List[HourlyPlan] = []
        simulated_indoor_temp = current_indoor_temp
        
        # 2. First Pass: Determine "MUST_RUN" and "MUST_REST" for comfort
        next_full_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        for i in range(24):
            current_planning_time = next_full_hour + timedelta(hours=i)
            
            # Get outdoor temp
            outdoor_temp_hour = 0.0
            # Use isoformat matching logic from previous steps
            iso_ts = current_planning_time.isoformat()
            # Try exact match first
            if iso_ts in weather_forecast_dict:
                 outdoor_temp_hour = weather_forecast_dict[iso_ts].temperature
            else:
                 # Fallback: find closest
                 closest = min(weather_forecast, key=lambda x: abs((x.timestamp.replace(tzinfo=timezone.utc) - current_planning_time).total_seconds())) if weather_forecast else None
                 if closest: outdoor_temp_hour = closest.temperature

            
            # Get electricity price for this hour
            electricity_price_hour = all_prices_data.get(current_planning_time.hour, 0.5) # Fallback price
            
            # --- Simulate temperature change if pump is OFF ---
            effective_cooling_rate = cooling_rate_0c * (1 + (0 - outdoor_temp_hour) / 10) 
            simulated_indoor_if_off = simulated_indoor_temp + effective_cooling_rate

            action = "HOLD" # Default action
            
            # Hard Comfort Constraints
            if simulated_indoor_if_off <= min_safety_temp + 0.2: # Add buffer
                action = "MUST_RUN"
            elif simulated_indoor_if_off >= target_max_temp + 0.2: 
                action = "MUST_REST"
            
            plan.append(HourlyPlan(
                timestamp=current_planning_time,
                outdoor_temp=outdoor_temp_hour,
                electricity_price=electricity_price_hour,
                simulated_indoor_temp=simulated_indoor_temp,
                planned_action=action,
                planned_gm_value=0
            ))

            # Update simulated temp for next hour based on this action
            if action == "MUST_RUN":
                simulated_indoor_temp += self.COMPRESSOR_HEAT_OUTPUT_C_PER_H 
            elif action == "MUST_REST":
                simulated_indoor_temp = simulated_indoor_if_off 
            else: 
                simulated_indoor_temp = simulated_indoor_if_off
            
            simulated_indoor_temp = max(min_safety_temp - 1.0, min(target_max_temp + 2.0, simulated_indoor_temp))


        # 3. Second Pass: Price Optimization for "HOLD" hours
        hours_needed_to_run = 0 # Simplified placeholder
        # Estimate total heat loss over 24h:
        total_estimated_heat_loss = 0.0
        for p in plan:
            effective_cooling_rate = cooling_rate_0c * (1 + (0 - p.outdoor_temp) / 10)
            total_estimated_heat_loss += abs(effective_cooling_rate)

        # Calculate needed run hours
        heat_needed_c = total_estimated_heat_loss + (target_max_temp - target_min_temp) # Cover loss + build buffer
        hours_needed_to_run = heat_needed_c / self.COMPRESSOR_HEAT_OUTPUT_C_PER_H
        
        logger.info(f"Hours needed to run pump over 24h: {hours_needed_to_run:.1f} hours")
        
        # Sort ALL hours by price
        all_hours_sorted_by_price = sorted(plan, key=lambda p: p.electricity_price)
        
        run_hours_assigned = 0
        for p_hour in all_hours_sorted_by_price:
            if p_hour.planned_action == "MUST_RUN":
                run_hours_assigned += 1
            elif p_hour.planned_action == "MUST_REST":
                pass
            elif run_hours_assigned < hours_needed_to_run:
                p_hour.planned_action = "RUN"
                p_hour.planned_gm_value = self.GM_PRODUCTION_PER_HOUR_RUNNING
                run_hours_assigned += 1
            else:
                p_hour.planned_action = "REST"
                p_hour.planned_gm_value = 0
                
        # Final simulation
        simulated_indoor_temp = current_indoor_temp
        for p_hour in plan:
            effective_cooling_rate = cooling_rate_0c * (1 + (0 - p_hour.outdoor_temp) / 10) 

            if p_hour.planned_action in ["RUN", "MUST_RUN"]:
                simulated_indoor_temp += self.COMPRESSOR_HEAT_OUTPUT_C_PER_H
            else: 
                simulated_indoor_temp += effective_cooling_rate
            
            p_hour.simulated_indoor_temp = simulated_indoor_temp
            
            if simulated_indoor_temp < min_safety_temp:
                logger.error(f"PLANNING ERROR: Simulated indoor temp {simulated_indoor_temp:.1f} fell below safety limit at {p_hour.timestamp}")


        # Log and store
        logger.info("\n--- 24h Heating Plan ---")
        for p_hour in plan:
            logger.info(f"{p_hour.timestamp.strftime('%Y-%m-%d %H:%M')}: {p_hour.planned_action:<10} | "
                        f"Ute:{p_hour.outdoor_temp:5.1f}°C | "
                        f"InneSim:{p_hour.simulated_indoor_temp:5.1f}°C | "
                        f"Pris:{p_hour.electricity_price:5.2f} SEK/kWh | GM:{p_hour.planned_gm_value:5.1f}")
        
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
                planned_gm_value=p_hour.planned_gm_value
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