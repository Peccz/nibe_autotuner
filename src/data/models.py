from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime

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
    updated_at = Column(DateTime, default=datetime.utcnow)
    devices = relationship('Device', back_populates='system')

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
    min_indoor_temp_user_setting = Column(Float, default=20.5, nullable=False)
    target_indoor_temp_min = Column(Float, default=20.5, nullable=False)
    target_indoor_temp_max = Column(Float, default=22.0, nullable=False)
    comfort_adjustment_offset = Column(Float, default=0.0)
    away_mode_enabled = Column(Boolean, default=False)
    away_mode_end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    system = relationship('System', back_populates='devices')
    readings = relationship('ParameterReading', back_populates='device')
    changes = relationship('ParameterChange', back_populates='device')
    recommendations = relationship('Recommendation', back_populates='device')

class Parameter(Base):
    """Parameter metadata"""
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
    readings = relationship('ParameterReading', back_populates='parameter')
    changes = relationship('ParameterChange', back_populates='parameter')
    recommendations = relationship('Recommendation', back_populates='parameter')

class ParameterReading(Base):
    """Time-series readings"""
    __tablename__ = 'parameter_readings'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    value = Column(Float, nullable=False)
    str_value = Column(String(50))
    device = relationship('Device', back_populates='readings')
    parameter = relationship('Parameter', back_populates='readings')

class ParameterChange(Base):
    """Track manual/AI parameter changes"""
    __tablename__ = 'parameter_changes'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    old_value = Column(Float)
    new_value = Column(Float)
    reason = Column(Text)
    applied_by = Column(String(50))
    recommendation_id = Column(Integer, ForeignKey('recommendations.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    metrics_before_captured = Column(Boolean, default=False)
    metrics_after_captured = Column(Boolean, default=False)
    evaluation_status = Column(String(20), default='pending')
    device = relationship('Device', back_populates='changes')
    parameter = relationship('Parameter', back_populates='changes')
    recommendation = relationship('Recommendation', back_populates='changes')
    ab_test_results = relationship('ABTestResult', back_populates='parameter_change')

class ABTestResult(Base):
    """A/B Testing results"""
    __tablename__ = 'ab_test_results'
    id = Column(Integer, primary_key=True)
    parameter_change_id = Column(Integer, ForeignKey('parameter_changes.id'), nullable=False, index=True)
    before_start = Column(DateTime, nullable=False)
    before_end = Column(DateTime, nullable=False)
    after_start = Column(DateTime, nullable=False)
    after_end = Column(DateTime, nullable=False)
    cop_before = Column(Float)
    cop_after = Column(Float)
    cop_change_percent = Column(Float)
    delta_t_before = Column(Float)
    delta_t_after = Column(Float)
    delta_t_change_percent = Column(Float)
    indoor_temp_before = Column(Float)
    indoor_temp_after = Column(Float)
    indoor_temp_change = Column(Float)
    outdoor_temp_before = Column(Float)
    outdoor_temp_after = Column(Float)
    compressor_freq_before = Column(Float)
    compressor_freq_after = Column(Float)
    runtime_hours_before = Column(Float)
    runtime_hours_after = Column(Float)
    success_score = Column(Float)
    recommendation = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    parameter_change = relationship('ParameterChange', back_populates='ab_test_results')

class Recommendation(Base):
    """AI recommendations"""
    __tablename__ = 'recommendations'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'), nullable=False)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    recommended_value = Column(Float)
    current_value = Column(Float)
    expected_impact = Column(Text)
    priority = Column(String(20))
    status = Column(String(20), default='pending')
    applied_at = Column(DateTime)
    expired_at = Column(DateTime)
    device = relationship('Device', back_populates='recommendations')
    parameter = relationship('Parameter', back_populates='recommendations')
    changes = relationship('ParameterChange', back_populates='recommendation')
    results = relationship('RecommendationResult', back_populates='recommendation')

class RecommendationResult(Base):
    """Track effectiveness"""
    __tablename__ = 'recommendation_results'
    id = Column(Integer, primary_key=True)
    recommendation_id = Column(Integer, ForeignKey('recommendations.id'), nullable=False)
    measured_at = Column(DateTime, nullable=False)
    metric_name = Column(String(50))
    before_value = Column(Float)
    after_value = Column(Float)
    change_percent = Column(Float)
    success = Column(Boolean)
    recommendation = relationship('Recommendation', back_populates='results')

class PlannedTest(Base):
    """AI-proposed tests waiting to be executed"""
    __tablename__ = 'planned_tests'

    id = Column(Integer, primary_key=True)
    parameter_id = Column(Integer, ForeignKey('parameters.id'), nullable=False)
    current_value = Column(Float)
    proposed_value = Column(Float)
    hypothesis = Column(String(500))
    expected_improvement = Column(String(200))
    priority = Column(String(20))
    priority_score = Column(Float, default=0.0)
    execution_order = Column(Integer)
    confidence = Column(Float)
    reasoning = Column(String(1000))
    status = Column(String(20), default='pending')
    proposed_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    result_id = Column(Integer, ForeignKey('ab_test_results.id'))
    instruction = Column(Text)

    parameter = relationship('Parameter')
    result = relationship('ABTestResult', foreign_keys=[result_id])

class ABTest(Base):
    """A/B Test definition"""
    __tablename__ = 'ab_tests'
    id = Column(Integer, primary_key=True)
    parameter_id = Column(Integer, ForeignKey('parameters.id'))
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    status = Column(String(20))
    parameter = relationship('Parameter')

class AIDecision(Base):
    """Unified AI Decision model"""
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
    parameter = relationship('Parameter')

class GMAccount(Base):
    """The 'Bank'"""
    __tablename__ = 'gm_account'
    id = Column(Integer, primary_key=True)
    balance = Column(Float, default=0.0)
    mode = Column(String(20), default='NORMAL')
    last_updated = Column(DateTime, default=datetime.utcnow)

class SystemTuning(Base):
    """Physical coefficients for house modeling"""
    __tablename__ = 'system_tuning'
    parameter_id = Column(String(50), primary_key=True)
    value = Column(Float, nullable=False)
    description = Column(String(200))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AIDecisionLog(Base):
    """Log of all AI decisions"""
    __tablename__ = 'ai_decision_log'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    action = Column(String(20))
    current_value = Column(Float)
    suggested_value = Column(Float)
    reasoning = Column(String(2000))
    confidence = Column(Float)
    expected_impact = Column(String(500))
    applied = Column(Boolean, default=False)

class PlannedHeatingSchedule(Base):
    """Version 4.0 Schedule with Wind and Presence-eco"""
    __tablename__ = "planned_heating_schedule"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    outdoor_temp = Column(Float)
    electricity_price = Column(Float)
    cloud_cover = Column(Float)
    solar_gain = Column(Float)
    wind_speed = Column(Float)
    wind_direction = Column(Integer)
    simulated_indoor_temp = Column(Float)
    simulated_dexter_temp = Column(Float)
    planned_action = Column(String(20))
    planned_gm_value = Column(Float)
    planned_offset = Column(Float, default=0.0)
    planned_hot_water_mode = Column(Integer, default=1)

    def __repr__(self):
        return f"<PlannedHeatingSchedule(timestamp='{self.timestamp}', action='{self.planned_action}')>"

class LearningEvent(Base):
    """Thermal property learning"""
    __tablename__ = 'learning_events'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    parameter_id = Column(String(50), index=True)
    action = Column(String(50))
    old_value = Column(Float)
    new_value = Column(Float)
    outdoor_temp_start = Column(Float)
    indoor_temp_start = Column(Float)
    target_temp_start = Column(Float, nullable=True)
    indoor_temp_1h = Column(Float, nullable=True)
    indoor_temp_4h = Column(Float, nullable=True)
    thermal_rate = Column(Float, nullable=True)

class HotWaterUsage(Base):
    """HW usage log"""
    __tablename__ = 'hot_water_usage'
    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer)
    start_temp = Column(Float)
    end_temp = Column(Float)
    temp_drop = Column(Float)
    weekday = Column(Integer)
    hour = Column(Integer)
