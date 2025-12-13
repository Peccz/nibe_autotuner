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
    planned_offset: Optional[float] = 0.0 # Heating curve offset

class SmartPlanner:
    def __init__(self):
        self.session = SessionLocal()
        self.analyzer = HeatPumpAnalyzer()
        self.weather_service = SMHIWeatherService()
        self.price_service = PriceService()
        self.learning_service = LearningService(self.session, self.analyzer)
        
        # Get device for all operations
        self.device = self.analyzer.get_device()
        
        # Constants (can be moved to settings eventually)
        self.K_GM_PER_DELTA_T_PER_H = getattr(settings, 'K_GM_PER_DELTA_T_PER_H', 4.0) 
        self.COMPRESSOR_HEAT_OUTPUT_C_PER_H = getattr(settings, 'COMPRESSOR_HEAT_OUTPUT_C_PER_H', 0.5)
        self.GM_PRODUCTION_PER_HOUR_RUNNING = getattr(settings, 'GM_PRODUCTION_PER_HOUR_RUNNING', 60.0)

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
            
            # Simple adaptive logic: If rate is low despite heating, maybe our output constant is too high?
            # Or if rate is negative, maybe cooling rate is higher than we thought?
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

        # Run Reality Check (Logging only for now, later feedback loop)
        self.calculate_real_world_metrics()

        # 1. Fetch current context
        current_metrics = self.analyzer.calculate_metrics(hours_back=1)
        current_indoor_temp = current_metrics.avg_indoor_temp if current_metrics and current_metrics.avg_indoor_temp else None
        
        # Fallback 1: Latest known value
        if current_indoor_temp is None:
            latest = self.analyzer.get_latest_value(self.device, self.analyzer.PARAM_INDOOR_TEMP)
            if latest is not None:
                current_indoor_temp = latest
                logger.warning(f"Using latest known indoor temp (older than 1h): {latest}°C")

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
        all_prices_data: Dict[int, float] = {}
        for p in price_forecast_today + price_forecast_raw:
            all_prices_data[p.time_start.hour] = p.price_per_kwh
        
        # Get thermal inertia
        inertia = self.learning_service.analyze_thermal_inertia()
        cooling_rate_0c = inertia.get('cooling_rate_0c', -0.15) 

        logger.info(f"Current Indoor: {current_indoor_temp:.1f}°C. Targets: {min_safety_temp:.1f}-{target_min_temp:.1f}-{target_max_temp:.1f}°C")

        plan: List[HourlyPlan] = []
        simulated_indoor_temp = current_indoor_temp
        
        # 2. First Pass: Comfort Simulation
        next_full_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        for i in range(24):
            current_planning_time = next_full_hour + timedelta(hours=i)
            
            # Weather
            iso_ts = current_planning_time.isoformat()
            outdoor_temp_hour = 0.0
            if iso_ts in weather_forecast_dict:
                 outdoor_temp_hour = weather_forecast_dict[iso_ts].temperature
            else:
                 closest = min(weather_forecast, key=lambda x: abs((x.timestamp.replace(tzinfo=timezone.utc) - current_planning_time).total_seconds())) if weather_forecast else None
                 if closest: outdoor_temp_hour = closest.temperature
            
            # Price
            electricity_price_hour = all_prices_data.get(current_planning_time.hour, 0.5)
            
            # Simulation (Passive)
            effective_cooling_rate = cooling_rate_0c * (1 + (0 - outdoor_temp_hour) / 10) 
            simulated_indoor_if_off = simulated_indoor_temp + effective_cooling_rate

            action = "HOLD"
            
            if simulated_indoor_if_off <= min_safety_temp + 0.2:
                action = "MUST_RUN"
            elif simulated_indoor_if_off >= target_max_temp + 0.2:
                action = "MUST_REST"
            
            plan.append(HourlyPlan(
                timestamp=current_planning_time,
                outdoor_temp=outdoor_temp_hour,
                electricity_price=electricity_price_hour,
                simulated_indoor_temp=simulated_indoor_temp,
                planned_action=action,
                planned_gm_value=0,
                planned_offset=0.0 # Default
            ))

            # Update Simulation
            if action == "MUST_RUN":
                simulated_indoor_temp += self.COMPRESSOR_HEAT_OUTPUT_C_PER_H
            elif action == "MUST_REST":
                simulated_indoor_temp = simulated_indoor_if_off 
            else: 
                simulated_indoor_temp = simulated_indoor_if_off
            
            simulated_indoor_temp = max(min_safety_temp - 1.0, min(target_max_temp + 2.0, simulated_indoor_temp))


        # 3. Second Pass: Price Optimization & Offset Assignment
        hours_needed_to_run = 0
        total_estimated_heat_loss = 0.0
        for p in plan:
            effective_cooling_rate = cooling_rate_0c * (1 + (0 - p.outdoor_temp) / 10)
            total_estimated_heat_loss += abs(effective_cooling_rate)

        heat_needed_c = total_estimated_heat_loss + (target_max_temp - target_min_temp)
        hours_needed_to_run = heat_needed_c / self.COMPRESSOR_HEAT_OUTPUT_C_PER_H
        
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
        
        # 4. Assign Offsets based on final plan
        simulated_indoor_temp = current_indoor_temp # Reset for final pass
        for p_hour in plan:
            # Simulation update
            outdoor_temp_hour = p_hour.outdoor_temp
            effective_cooling_rate = cooling_rate_0c * (1 + (0 - outdoor_temp_hour) / 10) 

            if p_hour.planned_action in ["RUN", "MUST_RUN"]:
                simulated_indoor_temp += self.COMPRESSOR_HEAT_OUTPUT_C_PER_H
            else: 
                simulated_indoor_temp += effective_cooling_rate
            
            p_hour.simulated_indoor_temp = simulated_indoor_temp
            
            # Offset Logic
            if p_hour.planned_action == "MUST_RUN":
                p_hour.planned_offset = 2.0 # Force heat
            elif p_hour.planned_action == "RUN":
                p_hour.planned_offset = 1.0 # Efficient heat
            elif p_hour.planned_action in ["REST", "MUST_REST"]:
                p_hour.planned_offset = -5.0 # Force stop
            else:
                p_hour.planned_offset = 0.0


        # Log and store
        logger.info("\n--- 24h Heating Plan (with Offset) ---")
        for p_hour in plan:
            logger.info(f"{p_hour.timestamp.strftime('%H:%M')}: {p_hour.planned_action:<10} | "
                        f"Offset:{p_hour.planned_offset:>4.1f} | "
                        f"InneSim:{p_hour.simulated_indoor_temp:5.1f}°C")
        
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
                planned_offset=p_hour.planned_offset # Save offset
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
