"""
Pydantic schemas for API request/response validation

DTOs (Data Transfer Objects) for type-safe API communication.
These schemas define the structure of data sent to and received from API endpoints.
"""

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Any, Dict


# ============================================================================
# User Settings Schemas
# ============================================================================

class UserSettingsSchema(BaseModel):
    """User-configurable settings for a device"""

    min_indoor_temp_user_setting: float = Field(
        ...,
        ge=18.0,
        le=25.0,
        description="Minimum indoor temperature (°C) - safety threshold"
    )

    target_indoor_temp_min: float = Field(
        ...,
        ge=18.0,
        le=25.0,
        description="Target indoor temperature minimum (°C)"
    )

    target_indoor_temp_max: float = Field(
        ...,
        ge=18.0,
        le=25.0,
        description="Target indoor temperature maximum (°C)"
    )

    model_config = ConfigDict(from_attributes=True)


class UserSettingsUpdateSchema(BaseModel):
    """Schema for updating user settings"""

    min_indoor_temp_user_setting: Optional[float] = Field(
        None,
        ge=18.0,
        le=25.0,
        description="Minimum indoor temperature (°C)"
    )

    target_indoor_temp_min: Optional[float] = Field(
        None,
        ge=18.0,
        le=25.0,
        description="Target indoor temperature minimum (°C)"
    )

    target_indoor_temp_max: Optional[float] = Field(
        None,
        ge=18.0,
        le=25.0,
        description="Target indoor temperature maximum (°C)"
    )


# ============================================================================
# Device Schemas
# ============================================================================

class DeviceSchema(BaseModel):
    """Device information"""

    id: int
    device_id: str
    product_name: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    connection_state: Optional[str] = None

    # User settings
    min_indoor_temp_user_setting: float
    target_indoor_temp_min: float
    target_indoor_temp_max: float

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeviceListSchema(BaseModel):
    """List of devices"""
    devices: List[DeviceSchema]


# ============================================================================
# System Schemas
# ============================================================================

class SystemSchema(BaseModel):
    """System information"""

    id: int
    system_id: str
    name: Optional[str] = None
    country: Optional[str] = None
    security_level: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Parameter Schemas
# ============================================================================

class ParameterSchema(BaseModel):
    """Parameter metadata"""

    id: int
    parameter_id: str
    parameter_name: Optional[str] = None
    parameter_unit: Optional[str] = None
    category: Optional[str] = None
    writable: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step_value: Optional[float] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ParameterReadingSchema(BaseModel):
    """Parameter reading"""

    id: int
    device_id: str
    parameter_id: str
    parameter_name: Optional[str] = None
    value: float
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ParameterChangeSchema(BaseModel):
    """Parameter change record"""

    id: int
    device_id: str
    parameter_id: str
    parameter_name: Optional[str] = None
    old_value: Optional[float] = None
    new_value: float
    reason: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

class ParameterChangeRequest(BaseModel):
    """Request to change a parameter value"""
    parameter_id: str
    value: float


# ============================================================================
# AI Decision Schemas
# ============================================================================

class AgentAIDecisionSchema(BaseModel):
    """AI decision from agent before logging"""
    action: str
    parameter: Optional[str] = None
    current_value: Optional[float] = None
    suggested_value: Optional[float] = None
    reasoning: str
    confidence: float
    expected_impact: str

    model_config = ConfigDict(from_attributes=True)

class AIDecisionSchema(BaseModel):
    """AI decision record"""

    id: int
    device_id: str
    action: str
    parameter: Optional[str] = None
    current_value: Optional[float] = None
    suggested_value: Optional[float] = None
    reasoning: str
    confidence: float
    applied: bool
    metrics_snapshot: Optional[str] = None
    price_snapshot: Optional[str] = None
    weather_snapshot: Optional[str] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# API Response Schemas
# ============================================================================

class APIResponse(BaseModel):
    """Generic API response wrapper"""
    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None

class SuccessResponse(BaseModel):
    """Generic success response"""
    success: bool = True
    message: Optional[str] = None

class ErrorResponse(BaseModel):
    """Generic error response"""
    success: bool = False
    error: str

class SettingsResponse(BaseModel):
    """Settings API response"""
    success: bool = True
    settings: UserSettingsSchema
