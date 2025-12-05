"""
Centralized Configuration Management using Pydantic Settings

This module provides a type-safe, centralized way to manage all application
configuration through environment variables. Uses Pydantic for validation
and type checking.

All configuration should be accessed through the `settings` singleton object.

Example:
    from config import settings

    # Access configuration
    api_key = settings.GOOGLE_API_KEY
    db_url = settings.DATABASE_URL
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
    from config import settings

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


if __name__ == "__main__":
    # Test configuration loading
    try:
        validate_required_settings()
        print_config_summary()
        print("\n✓ Configuration loaded successfully!")
    except Exception as e:
        print(f"\n✗ Configuration error: {e}")
        exit(1)
