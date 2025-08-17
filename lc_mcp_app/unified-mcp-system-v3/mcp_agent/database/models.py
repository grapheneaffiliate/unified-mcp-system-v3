"""
SQLModel database models.
"""


from sqlmodel import Field, SQLModel


class ModelContextDB(SQLModel, table=True):
    """Model context database table."""

    __tablename__ = "modelcontext"

    id: str = Field(primary_key=True, index=True, description="Unique model identifier")
    version: str = Field(..., description="Model version")
    status: str = Field(..., description="Model status (active, deprecated, etc.)")
    parameters: str = Field(default="{}", description="Model parameters as JSON string")
    metrics: str | None = Field(default=None, description="Model metrics as JSON string")

    class Config:
        """SQLModel configuration."""
        schema_extra = {
            "example": {
                "id": "model_abc",
                "version": "1.2.0",
                "status": "active",
                "parameters": '{"lr": 0.01, "batch_size": 32}',
                "metrics": '{"accuracy": 0.95, "loss": 0.05}'
            }
        }
