from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from loguru import logger

from data.models import LearningEvent, ParameterReading
from services.analyzer import HeatPumpAnalyzer

class LearningService:
    def __init__(self, db_session: Session, analyzer: HeatPumpAnalyzer):
        self.db = db_session
        self.analyzer = analyzer

    def record_action(self, 
                      parameter_id: str, 
                      action: str, 
                      old_value: float, 
                      new_value: float, 
                      metrics=None):
        """
        Records an action to be analyzed later.
        """
        try:
            # Get current temperatures
            device = self.analyzer.get_device()
            outdoor = self.analyzer.get_latest_value(device, self.analyzer.PARAM_OUTDOOR_TEMP)
            indoor = self.analyzer.get_latest_value(device, self.analyzer.PARAM_INDOOR_TEMP)
            
            # Create event
            event = LearningEvent(
                timestamp=datetime.utcnow(),
                parameter_id=parameter_id,
                action=action,
                old_value=old_value,
                new_value=new_value,
                outdoor_temp_start=outdoor,
                indoor_temp_start=indoor,
                target_temp_start=20.5 # Default or fetch from settings
            )
            
            self.db.add(event)
            self.db.commit()
            logger.info(f"Recorded learning event: {action} {old_value}->{new_value}")
            
        except Exception as e:
            logger.error(f"Failed to record learning event: {e}")

    def update_pending_events(self):
        """
        Checks past events and fills in results (1h/4h later)
        """
        try:
            # Get events from last 48h that lack 4h result
            cutoff = datetime.utcnow() - timedelta(hours=48)
            pending_events = self.db.query(LearningEvent).filter(
                LearningEvent.timestamp >= cutoff,
                LearningEvent.indoor_temp_4h == None
            ).all()
            
            updated_count = 0
            
            for event in pending_events:
                # Check if enough time has passed
                time_since = datetime.utcnow() - event.timestamp
                hours_passed = time_since.total_seconds() / 3600
                
                device = self.analyzer.get_device()
                
                # Update 1h result
                if hours_passed >= 1 and event.indoor_temp_1h is None:
                    target_time = event.timestamp + timedelta(hours=1)
                    reading = self._get_reading_at(device, self.analyzer.PARAM_INDOOR_TEMP, target_time)
                    if reading:
                        event.indoor_temp_1h = reading.value
                        
                # Update 4h result
                if hours_passed >= 4 and event.indoor_temp_4h is None:
                    target_time = event.timestamp + timedelta(hours=4)
                    reading = self._get_reading_at(device, self.analyzer.PARAM_INDOOR_TEMP, target_time)
                    if reading:
                        event.indoor_temp_4h = reading.value
                        
                        # Calculate thermal rate (deg/h)
                        # Simple linear calculation: (End - Start) / 4
                        if event.indoor_temp_start is not None:
                            diff = event.indoor_temp_4h - event.indoor_temp_start
                            event.thermal_rate = diff / 4.0
                            updated_count += 1
            
            if updated_count > 0:
                self.db.commit()
                logger.info(f"Updated {updated_count} learning events with results")
                
        except Exception as e:
            logger.error(f"Error updating pending events: {e}")

    def _get_reading_at(self, device, param_id, target_time, window_minutes=15) -> Optional[ParameterReading]:
        """Helper to find a reading near a specific time"""
        start = target_time - timedelta(minutes=window_minutes)
        end = target_time + timedelta(minutes=window_minutes)
        
        # We need the parameter DB ID, not the API ID string
        param = self.analyzer.get_parameter(param_id)
        if not param:
            return None
            
        return self.db.query(ParameterReading).filter(
            ParameterReading.device_id == device.id,
            ParameterReading.parameter_id == param.id,
            ParameterReading.timestamp >= start,
            ParameterReading.timestamp <= end
        ).order_by(
            ParameterReading.timestamp
        ).first()

    def analyze_thermal_inertia(self) -> Dict[str, float]:
        """
        Analyzes completed events to determine house thermal properties.
        Returns average thermal rate (C/h) for different outdoor temperature zones.
        """
        try:
            # Default values (fallback)
            results = {
                "cooling_rate_cold": -0.2,  # < 0C
                "cooling_rate_mild": -0.15, # 0-10C
                "cooling_rate_warm": -0.1,  # > 10C
                "heating_rate_cold": 0.15,
                "heating_rate_mild": 0.2,
                "heating_rate_warm": 0.3,
                # Legacy keys
                "cooling_rate_0c": -0.15,
                "heating_rate_0c": 0.2
            }
            
            # Fetch all completed events with valid rates
            events = self.db.query(LearningEvent).filter(
                LearningEvent.thermal_rate != None
            ).all()
            
            if not events:
                return results # Return defaults if no data
                
            # Buckets for aggregation
            buckets = {
                "cold": [], # < 0
                "mild": [], # 0 - 10
                "warm": []  # > 10
            }
            
            for e in events:
                if e.outdoor_temp_start is None: continue
                
                if e.outdoor_temp_start < 0:
                    buckets["cold"].append(e.thermal_rate)
                elif e.outdoor_temp_start <= 10:
                    buckets["mild"].append(e.thermal_rate)
                else:
                    buckets["warm"].append(e.thermal_rate)
            
            # Helper to avg
            def get_avg(lst):
                return sum(lst) / len(lst) if lst else None

            # Cooling (rate < 0) vs Heating (rate > 0) separation within buckets
            for zone, rates in buckets.items():
                cooling = [r for r in rates if r < 0]
                heating = [r for r in rates if r > 0]
                
                avg_cool = get_avg(cooling)
                avg_heat = get_avg(heating)
                
                if avg_cool is not None:
                    results[f"cooling_rate_{zone}"] = round(avg_cool, 3)
                    # Update legacy key if mild
                    if zone == "mild":
                        results["cooling_rate_0c"] = round(avg_cool, 3)
                
                if avg_heat is not None:
                    results[f"heating_rate_{zone}"] = round(avg_heat, 3)
                    # Update legacy key if mild
                    if zone == "mild":
                        results["heating_rate_0c"] = round(avg_heat, 3)
            
            return results

        except Exception as e:
            logger.error(f"Error analyzing thermal inertia: {e}")
            return {
                "cooling_rate_0c": -0.15,
                "error": str(e)
            }
