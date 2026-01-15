from sqlalchemy import Column, Integer, Float, DateTime, String
from data.database import Base
from datetime import datetime

class DailyPerformance(Base):
    """
    Stores aggregated performance metrics for a full day (00:00 - 23:59).
    Used to calculate savings and track long-term efficiency.
    """
    __tablename__ = 'daily_performance'

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False, unique=True, index=True)
    
    # Energy & Cost
    actual_kwh = Column(Float)
    actual_cost_sek = Column(Float)
    baseline_kwh = Column(Float)
    baseline_cost_sek = Column(Float)
    savings_sek = Column(Float)
    savings_percent = Column(Float)
    
    # Comfort
    avg_indoor_temp = Column(Float)
    min_indoor_temp = Column(Float)
    max_indoor_temp = Column(Float)
    target_temp = Column(Float)
    
    # Efficiency
    avg_cop = Column(Float)
    avg_outdoor_temp = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DailyPerf(date={self.date}, savings={self.savings_sek:.2f} SEK)>"

