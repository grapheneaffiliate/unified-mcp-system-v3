"""
Configuration management using pydantic-settings.

Centralized configuration with environment variable validation,
type checking, and profile support (dev/prod).
"""

import os
from pathlib import Path

from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8081, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment (development/production)")

    # Security
    secret_key: str = Field(default="my-secret-key", description="Secret key for authentication")
    allowed_origins: list[str] = Field(default=["*"], description="CORS allowed origins")
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per minute")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")

    # Database
    database_url: str = Field(default="sqlite:///model_context.db", description="Database URL")
    database_echo: bool = Field(default=False, description="Echo SQL queries")

    # Paths
    sandbox_dir: Path = Field(default=Path("./sandbox"), description="Sandbox directory")
    jupyter_notebooks_dir: Path = Field(default=Path("./jupyter_notebooks"), description="Jupyter notebooks directory")

    # External Services
    google_api_key: str | None = Field(default=None, description="Google API key for search")
    google_cse_id: str | None = Field(default=None, description="Google Custom Search Engine ID")
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")

    # Google OAuth
    google_client_id: str | None = Field(default=None, description="Google OAuth client ID")
    google_client_secret: str | None = Field(default=None, description="Google OAuth client secret")
    google_refresh_token: str | None = Field(default=None, description="Google OAuth refresh token")

    # Composio
    composio_api_key: str | None = Field(default=None, description="Composio API key")

    # Supabase
    supabase_url: str | None = Field(default=None, description="Supabase URL")
    supabase_service_key: str | None = Field(default=None, description="Supabase service key")

    # Obsidian
    obsidian_api_url: str | None = Field(default=None, description="Obsidian API URL")
    obsidian_api_key: str | None = Field(default=None, description="Obsidian API key")

    # Jupyter Docker
    jupyter_docker_container: str = Field(
        default="aeac4f30f3fe1da646f84a8d755d16ae7eb1252eefe1510bdc569aa402830118",
        description="Jupyter Docker container ID"
    )
    jupyter_host: str = Field(default="http://localhost:8002", description="Jupyter host URL")
    jupyter_user: str = Field(default="testuser", description="Jupyter username")
    jupyter_token: str | None = Field(default=None, description="Jupyter token")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json/text)")
    log_file: Path | None = Field(default=None, description="Log file path")

    # Metrics
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Metrics server port")

    # Security Settings
    sandbox_enabled: bool = Field(default=True, description="Enable sandbox security")
    network_restrictions: bool = Field(default=True, description="Enable network restrictions")
    allowed_domains: list[str] = Field(
        default=["googleapis.com", "supabase.co", "github.com"],
        description="Allowed external domains"
    )

    @validator("sandbox_dir", "jupyter_notebooks_dir", pre=True)
    def ensure_path_exists(cls, v: str | Path) -> Path:
        """Ensure directories exist."""
        if isinstance(v, str):
            v = Path(v)
        v.mkdir(parents=True, exist_ok=True)
        return v

    @validator("environment")
    def validate_environment(cls, v: str) -> str:
        """Validate environment setting."""
        if v not in ["development", "production", "testing"]:
            raise ValueError("Environment must be 'development', 'production', or 'testing'")
        return v

    @validator("log_level")
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"

    @property
    def google_tasks_scopes(self) -> list[str]:
        """Google Tasks API scopes."""
        return ["https://www.googleapis.com/auth/tasks"]

    def get_database_url(self) -> str:
        """Get database URL with proper path resolution."""
        if self.database_url.startswith("sqlite:///"):
            # Convert relative path to absolute
            db_path = self.database_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
            return f"sqlite:///{db_path}"
        return self.database_url

    def validate_required_for_production(self) -> None:
        """Validate required settings for production environment."""
        if not self.is_production:
            return

        required_fields = []
        if not self.secret_key or self.secret_key == "my-secret-key":
            required_fields.append("SECRET_KEY")
        if not self.google_api_key:
            required_fields.append("GOOGLE_API_KEY")
        if not self.openai_api_key:
            required_fields.append("OPENAI_API_KEY")

        if required_fields:
            raise ValueError(
                f"Production environment requires these environment variables: {', '.join(required_fields)}"
            )


# Global settings instance
settings = Settings()
