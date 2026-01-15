"""
HotWaterUsage Pattern Analyzer (V2)
Detects, logs, and predicts hot water usage.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import func
from loguru import logger
import pandas as pd

from data.database import SessionLocal
from data.models import ParameterReading, Parameter, HotWaterUsage

class HotWaterPatternAnalyzer:
    def __init__(self):
        self.param_id_top = '40013' # BT7
        self.usage_map = {}
        
    def train_on_history(self, days_back=7):
        """Legacy alias for detect_new_usage_events + build_map"""
        self.detect_new_usage_events(days_back)
        self.build_probability_map()

    def detect_new_usage_events(self, days_back=7):
        """Scan recent raw data for new usage events and save to DB."""
        session = SessionLocal()
        try:
            # Get Parameter ID
            param = session.query(Parameter).filter_by(parameter_id=self.param_id_top).first()
            if not param:
                # Try finding it by raw query if model filter fails (sometimes ID vs param_id confusion)
                return

            # Determine where to start scanning
            # Find the latest event we already logged
            last_event = session.query(HotWaterUsage).order_by(HotWaterUsage.end_time.desc()).first()
            
            if last_event and last_event.end_time:
                # Start a bit after last event
                start_scan = last_event.end_time
            else:
                # No events logged yet, scan back X days
                start_scan = datetime.utcnow() - timedelta(days=days_back)

            # Fetch raw readings
            readings = session.query(ParameterReading).filter(
                ParameterReading.parameter_id == param.id,
                ParameterReading.timestamp > start_scan
            ).order_by(ParameterReading.timestamp).all()

            if not readings:
                return

            # Analyze for drops
            # Logic: If temp drops > 3 degrees within 15 mins -> Event Start
            # Event End: When temp starts rising or stabilizes
            
            current_event = None
            
            for i in range(1, len(readings)):
                curr = readings[i]
                prev = readings[i-1]
                
                # Check time continuity (ignore gaps > 15 min in data)
                if (curr.timestamp - prev.timestamp).total_seconds() > 900:
                    if current_event: # Close event if gap
                        self._check_and_save(session, current_event, prev)
                        current_event = None
                    continue

                diff = curr.value - prev.value
                
                # Detect Drop (Start or Continue)
                # Drop faster than 0.5C per reading (approx 5 min)
                if diff < -0.2: # Sensitive threshold for start
                    if not current_event:
                        # New event potential
                        current_event = {
                            'start_time': prev.timestamp,
                            'start_temp': prev.value,
                            'readings': [prev, curr]
                        }
                    else:
                        current_event['readings'].append(curr)
                else:
                    # Stable or Rising
                    if current_event:
                        # Event ended
                        self._check_and_save(session, current_event, prev)
                        current_event = None # Reset

            # Commit any changes
            session.commit()
            
        except Exception as e:
            logger.error(f"Error detecting HW events: {e}")
        finally:
            session.close()

    def _check_and_save(self, session, event_data, end_reading):
        """Validate and save event"""
        last_reading = event_data['readings'][-1]
        total_drop = event_data['start_temp'] - last_reading.value
        
        # Only count if drop > 3C (filtering noise)
        if total_drop >= 3.0:
            duration = (last_reading.timestamp - event_data['start_time']).total_seconds() / 60
            
            usage = HotWaterUsage(
                start_time=event_data['start_time'],
                end_time=last_reading.timestamp,
                duration_minutes=int(duration),
                start_temp=event_data['start_temp'],
                end_temp=last_reading.value,
                temp_drop=total_drop,
                weekday=event_data['start_time'].weekday(),
                hour=event_data['start_time'].hour
            )
            session.add(usage)
            logger.info(f"Detected HW Event: -{total_drop:.1f}C over {int(duration)}m at {event_data['start_time']}")

    def build_probability_map(self):
        """Builds usage_map from DB events."""
        session = SessionLocal()
        try:
            # Count events per weekday/hour
            # We want: P(Usage | Weekday, Hour)
            
            # First, find range of data available
            first = session.query(func.min(HotWaterUsage.start_time)).scalar()
            if not first:
                self.usage_map = {}
                return
            
            # Number of weeks since first data point
            weeks = max(1.0, (datetime.utcnow() - first).days / 7.0)
            
            # Query counts
            results = session.query(
                HotWaterUsage.weekday, 
                HotWaterUsage.hour, 
                func.count(HotWaterUsage.id)
            ).group_by(HotWaterUsage.weekday, HotWaterUsage.hour).all()
            
            self.usage_map = {}
            for wd, hr, count in results:
                # Probability is roughly occurrences / num_weeks
                # Cap at 1.0. If it happens > once a week on average, it's very likely.
                prob = min(1.0, count / weeks)
                self.usage_map[(wd, hr)] = round(prob, 2)
                
        finally:
            session.close()

    def get_usage_probability(self, timestamp: datetime) -> float:
        if not self.usage_map:
            self.build_probability_map()
            
        wd = timestamp.weekday()
        hr = timestamp.hour
        return self.usage_map.get((wd, hr), 0.0)

