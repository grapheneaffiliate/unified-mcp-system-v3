"""
Configuration management with pydantic-settings and production validation.
"""


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

    # App Configuration
    app_host: str = Field(default="0.0.0.0", description="Application host")
    app_port: int = Field(default=8001, description="Application port")
    app_log_level: str = Field(default="info", description="Log level")
    app_workers: int = Field(default=1, description="Number of workers")
    app_reload: bool = Field(default=False, description="Enable auto-reload")

    # Security
    api_keys: list[str] = Field(default=[], description="Valid API keys for authentication")
    allowed_origins: list[str] = Field(default=["*"], description="CORS allowed origins")

    # Rate Limiting
    rate_limit_rpm: int = Field(default=120, description="Rate limit requests per minute")
    rate_limit_burst: int = Field(default=60, description="Rate limit burst capacity")

    # MCP Server Configuration
    mcp_server_base_url: str = Field(default="http://127.0.0.1:8081", description="MCP server base URL")
    mcp_username: str | None = Field(default=None, description="MCP server username")
    mcp_password: str | None = Field(default=None, description="MCP server password")
    mcp_timeout_s: float = Field(default=30.0, description="MCP client timeout in seconds")
    mcp_max_connections: int = Field(default=20, description="Max connections to MCP server")
    mcp_max_keepalive: int = Field(default=10, description="Max keepalive connections to MCP server")

    # OpenAI Compatibility
    openai_api_base: str | None = Field(default=None, description="OpenAI API base URL")
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    openai_model_name: str = Field(default="gpt-4o-mini", description="Default OpenAI model name")
    openai_default_model: str = Field(default="gpt-4o-mini", description="Default model for compatibility")
    openai_max_tokens: int = Field(default=4096, description="Max tokens for responses")
    openai_temperature: float = Field(default=0.2, description="Default temperature")

    # Agent Configuration
    agent_timeout_s: float = Field(default=120.0, description="Agent execution timeout")
    agent_max_iterations: int = Field(default=10, description="Max agent iterations")
    agent_verbose: bool = Field(default=False, description="Enable verbose agent logging")

    # Observability
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    tracing_enabled: bool = Field(default=False, description="Enable OpenTelemetry tracing")
    log_format: str = Field(default="json", description="Log format (json/text)")

    # Environment
    environment: str = Field(default="development", description="Environment (development/production/testing)")

    @validator("app_log_level")
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["debug", "info", "warning", "error", "critical"]
        if v.lower() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.lower()

    @validator("environment")
    def validate_environment(cls, v: str) -> str:
        """Validate environment setting."""
        if v not in ["development", "production", "testing"]:
            raise ValueError("Environment must be 'development', 'production', or 'testing'")
        return v

    @validator("openai_temperature")
    def validate_temperature(cls, v: float) -> float:
        """Validate temperature range."""
        if not 0.0 <= v <= 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        """Check if running in testing."""
        return self.environment == "testing"

    def validate_required_for_production(self) -> None:
        """Validate required settings for production environment."""
        if not self.is_production:
            return

        required_fields = []
        if not self.api_keys:
            required_fields.append("API_KEYS")
        if not self.openai_api_key:
            required_fields.append("OPENAI_API_KEY")
        if not self.openai_api_base:
            required_fields.append("OPENAI_API_BASE")

        if required_fields:
            raise ValueError(
                f"Production environment requires these environment variables: {', '.join(required_fields)}"
            )

    def get_mcp_endpoint(self) -> str:
        """Get MCP JSON-RPC endpoint URL."""
        return f"{self.mcp_server_base_url.rstrip('/')}/jsonrpc"

    def get_mcp_health_endpoint(self) -> str:
        """Get MCP health check endpoint URL."""
        return f"{self.mcp_server_base_url.rstrip('/')}/health"


# Global settings instance
settings = Settings()
