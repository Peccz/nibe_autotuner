"""
Centralized Configuration Management using Pydantic Settings

This module provides a type-safe, centralized way to manage all application
configuration through environment variables. Uses Pydantic for validation
and type checking.

All settings are loaded from .env file and environment variables.
Environment variables take precedence over .env file values.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings are loaded from .env file and environment variables.
    Environment variables take precedence over .env file values.
    """

    # ============================================================================
    # MyUplink API Configuration
    # ============================================================================

    MYUPLINK_CLIENT_ID: str
    """MyUplink OAuth2 Client ID (required)"""

    MYUPLINK_CLIENT_SECRET: str
    """MyUplink OAuth2 Client Secret (required)"""

    MYUPLINK_CALLBACK_URL: str = "http://localhost:8080/oauth/callback"
    """OAuth2 callback URL"""

    MYUPLINK_API_BASE_URL: str = "https://api.myuplink.com"
    """MyUplink API base URL"""

    MYUPLINK_AUTH_URL: str = "https://api.myuplink.com/oauth/authorize"
    """MyUplink OAuth2 authorization URL"""

    MYUPLINK_TOKEN_URL: str = "https://api.myuplink.com/oauth/token"
    """MyUplink OAuth2 token URL"""

    # ============================================================================
    # Home Assistant Configuration
    # ============================================================================

    HA_URL: Optional[str] = None
    """Home Assistant API base URL (e.g., http://localhost:8123)"""

    HA_TOKEN: Optional[str] = None
    """Home Assistant Long-Lived Access Token"""

    HA_SENSOR_DOWNSTAIRS: str = "sensor.timmerflotte_temp_hmd_sensor_temperature_2"
    """Entity ID for the downstairs IKEA sensor"""

    HA_SENSOR_DEXTER: str = "sensor.timmerflotte_temp_hmd_sensor_temperature"
    """Entity ID for Dexter's room IKEA sensor"""

    # ============================================================================
    # House Physics (Multi-zone & Shunt)
    # ============================================================================

    DEFAULT_HEATING_CURVE: float = 7.0
    """The base heating curve set in the Nibe pump."""

    SHUNT_LIMIT_C: float = 32.0
    """Max temperature the downstairs floor heating shunt allows into the floor."""

    # Two-zone model: ground floor (floor heating) vs upper floors (radiators)
    # Empirically derived from parameter_readings 2026-01 to 2026-04 (cold weather, outdoor < 15°C)
    SHUNT_SETPOINT: float = 40.0
    """Supply temp (°C) above which the shunt starts limiting floor flow → excess heats radiators.
    Empirical: Dexter-Downstairs delta is worst at supply=40°C, improves above 45°C."""

    K_GAIN_FLOOR: float = 0.10
    """Indoor temp gain (°C/h) per offset unit for the floor heating zone.
    Lower than overall because the shunt buffers the floor circuit."""

    K_GAIN_RADIATOR: float = 0.15
    """Indoor temp gain (°C/h) per offset unit for the radiator zone (baseline, below shunt).
    Boosted by RAD_BOOST_FACTOR when supply exceeds SHUNT_SETPOINT."""

    K_LEAK_RADIATOR: float = 0.003
    """Heat loss factor for radiator zone. Slightly higher than floor (less insulated upper floors)."""

    RAD_BOOST_FACTOR: float = 0.012
    """Extra radiator gain (°C/h) per °C of supply above SHUNT_SETPOINT.
    At supply=50°C (10°C above shunt): +0.12°C/h per offset unit."""

    DEXTER_MIN_TEMP: float = 20.0
    """Minimum acceptable temperature in Dexter's room (radiator zone, middle floor)."""

    # ============================================================================
    # AI API Keys
    # ============================================================================

    GOOGLE_API_KEY: Optional[str] = None
    """Google Gemini API key (optional, for AI optimization)"""

    ANTHROPIC_API_KEY: Optional[str] = None
    """Anthropic Claude API key (optional, for legacy AI features)"""

    # ============================================================================
    # External Service APIs
    # ============================================================================

    TIBBER_API_TOKEN: Optional[str] = None
    """Tibber API token (optional, for electricity price data)"""

    # ============================================================================
    # Database Configuration
    # ============================================================================

    DATABASE_URL: str = "sqlite:///./data/nibe_autotuner.db"
    """Database connection URL (SQLite by default)"""

    # ============================================================================
    # Application Configuration
    # ============================================================================

    LOG_LEVEL: str = "INFO"
    """Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"""

    API_SERVER_HOST: str = "0.0.0.0"
    """API server bind address"""

    API_SERVER_PORT: int = 8000
    """API server port"""

    MOBILE_APP_HOST: str = "0.0.0.0"
    """Mobile PWA server bind address"""

    MOBILE_APP_PORT: int = 5001
    """Mobile PWA server port"""

    # ============================================================================
    # SmartPlanner Settings (Tuning)
    # ============================================================================

    K_GM_PER_DELTA_T_PER_H: float = 0.30
    """GM lost per degree-hour difference. Numerically calibrated."""

    COMPRESSOR_HEAT_OUTPUT_C_PER_H: float = 0.18
    """Degrees Celsius gain per hour when compressor is running. Numerically calibrated."""

    GM_PRODUCTION_PER_HOUR_RUNNING: float = 60.0
    """GM produced per hour when compressor is running."""

    OUTDOOR_TEMP_OFFSET_C: float = -0.5
    """Correction for sensor deviation. Add to forecast to match pump sensor. (e.g. -0.5)"""

    # ============================================================================
    # Optimizer V13.0 Constants (Tuning)
    # ============================================================================

    OPTIMIZER_K_LEAK: float = 0.002
    """House heat loss factor per °C delta per hour. Increase if house cools faster than predicted."""

    OPTIMIZER_K_GAIN: float = 0.15
    """Indoor temp gain per unit of offset per hour. Calibrated to heating curve response."""

    OPTIMIZER_MIN_OFFSET: float = -3.0
    """Minimum heating curve offset. Negative values enable active load-shedding (REST periods)."""

    OPTIMIZER_MAX_OFFSET: float = 5.0
    """Maximum heating curve offset. Hard limit from Nibe hardware."""

    OPTIMIZER_REST_THRESHOLD: float = -2.5
    """Offset value at or below which the planned action is classified as REST."""

    OPTIMIZER_TARGET_TEMP: float = 21.0
    """Target indoor temperature. Pass 2 reduces offsets while keeping temp at or above this."""

    OPTIMIZER_MIN_TEMP: float = 20.5
    """Comfort floor. Pass 1 raises offsets to ensure temp never drops below this."""

    OPTIMIZER_HOURLY_LOSS_FACTORS: str = "1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,4.0,4.0,4.0,4.0,1.0,1.0,1.0,1.0,1.0"
    """Per-hour K_LEAK multipliers (comma-separated, 24 values). Hours 15-18 have 4x loss due to occupancy/activity."""

    # ============================================================================
    # Feature Flags
    # ============================================================================

    @property
    def AI_ENABLED(self) -> bool:
        """Check if AI features are enabled (Google API key present)"""
        return self.GOOGLE_API_KEY is not None

    @property
    def TIBBER_ENABLED(self) -> bool:
        """Check if Tibber integration is enabled"""
        return self.TIBBER_API_TOKEN is not None

    @property
    def ANTHROPIC_ENABLED(self) -> bool:
        """Check if Anthropic Claude is enabled"""
        return self.ANTHROPIC_API_KEY is not None

    # ============================================================================
    # Pydantic Configuration
    # ============================================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Ignore extra env vars not defined here
    )


# ============================================================================
# Global Settings Singleton
# ============================================================================

settings = Settings()
"""
Global settings singleton. Import and use this throughout the application.

Example:
    from core.config import settings

    if settings.AI_ENABLED:
        # Use AI features
        pass
"""


# ============================================================================
# Validation Functions
# ============================================================================

def validate_required_settings() -> None:
    """
    Validate that all required settings are present.

    Raises:
        ValueError: If required settings are missing
    """
    required = {
        'MYUPLINK_CLIENT_ID': settings.MYUPLINK_CLIENT_ID,
        'MYUPLINK_CLIENT_SECRET': settings.MYUPLINK_CLIENT_SECRET,
    }

    missing = [key for key, value in required.items() if not value]

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Please set them in .env file or environment."
        )


def print_config_summary() -> None:
    """Print a summary of current configuration (safe for logging)"""
    print("=" * 80)
    print("Configuration Summary")
    print("=" * 80)
    print(f"Database URL:        {settings.DATABASE_URL}")
    print(f"Log Level:           {settings.LOG_LEVEL}")
    print(f"API Server:          {settings.API_SERVER_HOST}:{settings.API_SERVER_PORT}")
    print(f"Mobile App:          {settings.MOBILE_APP_HOST}:{settings.MOBILE_APP_PORT}")
    print(f"AI Enabled:          {settings.AI_ENABLED}")
    print(f"Tibber Enabled:      {settings.TIBBER_ENABLED}")
    print(f"Anthropic Enabled:   {settings.ANTHROPIC_ENABLED}")
    print("=" * 80)
    print("Note: Temperature settings are now stored per-device in database")


if __name__ == "__main__":
    # Test configuration loading
    try:
        validate_required_settings()
        print_config_summary()
        print("\n✓ Configuration loaded successfully!")
    except Exception as e:
        print(f"\n✗ Configuration error: {e}")
        exit(1)
