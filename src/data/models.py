"""
Database models for Nibe Autotuner

SQLAlchemy ORM models representing the database schema.
Import Base from data.database for declarative base.
"""
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

# Import Base from centralized database configuration
from data.database import Base


class System(Base):
    """Heat pump system"""
    __tablename__ = 'systems'

    id = Column(Integer, primary_key=True)
    system_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100))
    country = Column(String(50))
    security_level = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    devices = relationship('Device', back_populates='system')

    def __repr__(self):
        return f"<System(id={self.id}, name='{self.name}')>"


class Device(Base):
    """Heat pump device"""
    __tablename__ = 'devices'

    id = Column(Integer, primary_key=True)
    device_id = Column(String(100), unique=True, nullable=False, index=True)
    system_id = Column(Integer, ForeignKey('systems.id'), nullable=False)
    product_name = Column(String(100))
    serial_number = Column(String(50))
    firmware_version = Column(String(20))
    connection_state = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # User Settings - Dynamic configuration stored per device
    min_indoor_temp_user_setting = Column(Float, default=20.5, nullable=False)
    """Minimum indoor temperature (°C) - user configurable safety threshold. Default: 20.5°C"""

    target_indoor_temp_min = Column(Float, default=20.5, nullable=False)
    """Target indoor temperature minimum (°C). Default: 20.5°C"""

    target_indoor_temp_max = Column(Float, default=22.0, nullable=False)
    """Target indoor temperature maximum (°C). Default: 22.0°C"""

    comfort_adjustment_offset = Column(Float, default=0.0)
    """Global comfort offset (°C) added to min/target temperatures. Default: 0.0"""

    # Relationships
    system = relationship('System', back_populates='devices')
    readings = relationship('ParameterReading', back_populates='device')
    changes = relationship('ParameterChange', back_populates='device')
    recommendations = relationship('Recommendation', back_populates='device')

    def __repr__(self):
        return f"<Device(id={self.id}, name='{self.product_name}')>"


class Parameter(Base):
    """Parameter metadata (catalog of all available parameters)"""
    __tablename__ = 'parameters'

    id = Column(Integer, primary_key=True)
    parameter_id = Column(String(10), unique=True, nullable=False, index=True)
    parameter_name = Column(String(200))
    parameter_unit = Column(String(20))
    category = Column(String(100))
    writable = Column(Boolean, default=False)
    min_value = Column(Float)
    max_value = Column(Float)
    step_value = Column(Float)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    readings = relationship('ParameterReading', back_populates='parameter')
    changes = relationship('ParameterChange', back_populates='parameter')
    recommendations = relationship('Recommendation', back_populates='parameter')

    def __repr__(self):
        return f"<Parameter(id={self.parameter_id}, name='{self.parameter_name}')>"


class ParameterReading(Base):
    """Time-series parameter readings"""
    __tablename__ = 'parameter_readings'

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    value = Column(Float, nullable=False)
    str_value = Column(String(50))

    # Relationships
    device = relationship('Device', back_populates='readings')
    parameter = relationship('Parameter', back_populates='readings')

    # Indexes for fast time-series queries
    __table_args__ = (
        Index('idx_device_timestamp', 'device_id', 'timestamp'),
        Index('idx_param_timestamp', 'parameter_id', 'timestamp'),
        Index('idx_device_param_timestamp', 'device_id', 'parameter_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<Reading(param={self.parameter_id}, value={self.value}, time={self.timestamp})>"


class ParameterChange(Base):
    """Track manual parameter changes"""
    __tablename__ = 'parameter_changes'

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    old_value = Column(Float)
    new_value = Column(Float)
    reason = Column(Text)
    applied_by = Column(String(50))  # 'user', 'system', 'recommendation'
    recommendation_id = Column(Integer, ForeignKey('recommendations.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

    # A/B Testing - Metrics captured before/after change
    metrics_before_captured = Column(Boolean, default=False)
    metrics_after_captured = Column(Boolean, default=False)
    evaluation_status = Column(String(20), default='pending')  # 'pending', 'evaluating', 'completed'

    # Relationships
    device = relationship('Device', back_populates='changes')
    parameter = relationship('Parameter', back_populates='changes')
    recommendation = relationship('Recommendation', back_populates='changes')
    ab_test_results = relationship('ABTestResult', back_populates='parameter_change')

    def __repr__(self):
        return f"<Change(param={self.parameter_id}, {self.old_value}->{self.new_value})>"


class ABTestResult(Base):
    """A/B Testing results - Compare metrics before and after parameter changes"""
    __tablename__ = 'ab_test_results'

    id = Column(Integer, primary_key=True)
    parameter_change_id = Column(Integer, ForeignKey('parameter_changes.id'), nullable=False, index=True)

    # Time periods
    before_start = Column(DateTime, nullable=False)
    before_end = Column(DateTime, nullable=False)
    after_start = Column(DateTime, nullable=False)
    after_end = Column(DateTime, nullable=False)

    # COP metrics
    cop_before = Column(Float)
    cop_after = Column(Float)
    cop_change_percent = Column(Float)

    # Delta T metrics
    delta_t_before = Column(Float)
    delta_t_after = Column(Float)
    delta_t_change_percent = Column(Float)

    # Temperature metrics
    indoor_temp_before = Column(Float)
    indoor_temp_after = Column(Float)
    indoor_temp_change = Column(Float)

    outdoor_temp_before = Column(Float)
    outdoor_temp_after = Column(Float)

    # Compressor metrics
    compressor_freq_before = Column(Float)
    compressor_freq_after = Column(Float)
    compressor_cycles_before = Column(Integer)
    compressor_cycles_after = Column(Integer)

    # Runtime metrics
    runtime_hours_before = Column(Float)
    runtime_hours_after = Column(Float)

    # Cost metrics (calculated)
    cost_per_day_before = Column(Float)  # SEK
    cost_per_day_after = Column(Float)   # SEK
    cost_savings_per_day = Column(Float) # SEK
    cost_savings_per_year = Column(Float) # SEK

    # Overall evaluation
    success_score = Column(Float)  # 0-100 score
    recommendation = Column(Text)  # 'Keep', 'Revert', 'Adjust further'

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    parameter_change = relationship('ParameterChange', back_populates='ab_test_results')

    def __repr__(self):
        return f"<ABTestResult(change_id={self.parameter_change_id}, cop_change={self.cop_change_percent}%)>"


class Recommendation(Base):
    """AI-generated optimization recommendations"""
    __tablename__ = 'recommendations'

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    recommended_value = Column(Float)
    current_value = Column(Float)
    expected_impact = Column(Text)  # JSON with expected changes
    priority = Column(String(20))  # 'high', 'medium', 'low'
    status = Column(String(20), default='pending')  # 'pending', 'applied', 'rejected', 'expired'
    applied_at = Column(DateTime)
    expired_at = Column(DateTime)

    # Relationships
    device = relationship('Device', back_populates='recommendations')
    parameter = relationship('Parameter', back_populates='recommendations')
    changes = relationship('ParameterChange', back_populates='recommendation')
    results = relationship('RecommendationResult', back_populates='recommendation')

    def __repr__(self):
        return f"<Recommendation(id={self.id}, param={self.parameter_id}, status={self.status})>"


class RecommendationResult(Base):
    """Track effectiveness of applied recommendations"""
    __tablename__ = 'recommendation_results'

    id = Column(Integer, primary_key=True)
    recommendation_id = Column(Integer, ForeignKey('recommendations.id'), nullable=False)
    measured_at = Column(DateTime, nullable=False)
    metric_name = Column(String(50))  # e.g., 'energy_consumption', 'comfort_level'
    before_value = Column(Float)
    after_value = Column(Float)
    change_percent = Column(Float)
    success = Column(Boolean)

    # Relationships
    recommendation = relationship('Recommendation', back_populates='results')

    def __repr__(self):
        return f"<Result(rec={self.recommendation_id}, metric={self.metric_name}, change={self.change_percent}%)>"


class PlannedTest(Base):
    """AI-proposed tests waiting to be executed"""
    __tablename__ = 'planned_tests'

    id = Column(Integer, primary_key=True)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    current_value = Column(Float)
    proposed_value = Column(Float)
    hypothesis = Column(String(500))  # Why we think this will help
    expected_improvement = Column(String(200))  # Expected benefit
    priority = Column(String(20))  # 'high', 'medium', 'low'
    priority_score = Column(Float, default=0.0)  # Numeric priority score (0-100)
    execution_order = Column(Integer)  # Recommended execution order
    confidence = Column(Float)  # 0.0-1.0
    reasoning = Column(String(1000))  # AI reasoning
    status = Column(String(20), default='pending')  # 'pending', 'active', 'completed', 'cancelled'
    proposed_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    result_id = Column(Integer, ForeignKey('ab_test_results.id'))
    instruction = Column(Text) # Instructions for manual tests

    # Relationships
    parameter = relationship('Parameter')
    result = relationship('ABTestResult', foreign_keys=[result_id])

    def __repr__(self):
        return f"<PlannedTest(id={self.id}, param={self.parameter.parameter_name if self.parameter else 'unknown'}, priority={self.priority}, status={self.status})>"


class AIDecisionLog(Base):
    """Log of all AI agent decisions"""
    __tablename__ = 'ai_decision_log'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    action = Column(String(20))  # 'adjust', 'hold', 'investigate'
    parameter_id = Column(Integer, ForeignKey('parameters.id'))
    current_value = Column(Float)
    suggested_value = Column(Float)
    reasoning = Column(String(2000))
    confidence = Column(Float)
    expected_impact = Column(String(500))
    applied = Column(Boolean, default=False)  # Whether change was actually applied
    parameter_change_id = Column(Integer, ForeignKey('parameter_changes.id'))

    # Relationships
    parameter = relationship('Parameter')
    parameter_change = relationship('ParameterChange', foreign_keys=[parameter_change_id])

    def __repr__(self):
        return f"<AIDecision(id={self.id}, action={self.action}, applied={self.applied})>"



class LearningEvent(Base):
    """
    Tracks action-reaction events to learn house thermal properties.
    Example: Action "Offset -3" -> Result "Temp dropped 0.5C in 4h"
    """
    __tablename__ = 'learning_events'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    parameter_id = Column(String(50), index=True) # e.g. '47011'
    action = Column(String(50))                   # e.g. 'adjust_offset'
    
    # State before action
    old_value = Column(Float)
    new_value = Column(Float)
    outdoor_temp_start = Column(Float)
    indoor_temp_start = Column(Float)
    target_temp_start = Column(Float, nullable=True)
    
    # Results (filled in later by LearningService)
    indoor_temp_1h = Column(Float, nullable=True)
    indoor_temp_4h = Column(Float, nullable=True)
    thermal_rate = Column(Float, nullable=True)   # Degrees C per hour change (negative = cooling)
    
    def __repr__(self):
        return f"<LearningEvent(id={self.id}, action={self.action}, rate={self.thermal_rate})>"


class HotWaterUsage(Base):
    '''
    Log of detected hot water usage events (showers, baths, etc.)
    '''
    __tablename__ = 'hot_water_usage'

    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer)
    start_temp = Column(Float) # BT6/40013 value at start
    end_temp = Column(Float)   # BT6/40013 value at lowest point
    temp_drop = Column(Float)  # Total drop
    weekday = Column(Integer)  # 0=Monday, 6=Sunday
    hour = Column(Integer)     # 0-23
    
    def __repr__(self):
        return f"<HWUsage({self.start_time}, drop={self.temp_drop})>"

if __name__ == '__main__':
    # Test database models
    from loguru import logger
    from data.database import engine, init_db

    logger.info("Creating database...")
    init_db()
    logger.info(f"✓ Database created successfully!")
    logger.info(f"✓ Tables: {', '.join(Base.metadata.tables.keys())}")

# --- TILLAGDA FÖR ATT MATCHA NYA ROUTERS ---

class AIDecision(Base):
    """Unified AI Decision model matching the new router"""
    __tablename__ = 'ai_decisions'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    model_used = Column(String(50))
    action = Column(String(50))
    parameter_id = Column(Integer, ForeignKey('parameters.id'))
    current_value = Column(Float)
    suggested_value = Column(Float)
    reasoning = Column(Text)
    confidence = Column(Float)
    
    # Relationships
    parameter = relationship('Parameter')

class ABTest(Base):
    """A/B Test definition"""
    __tablename__ = 'ab_tests'
    
    id = Column(Integer, primary_key=True)
    parameter_id = Column(Integer, ForeignKey('parameters.id'))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    status = Column(String(20))
    
    # Relationships
    parameter = relationship('Parameter')
