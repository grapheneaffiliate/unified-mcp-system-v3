"""
Database operations with metrics and error handling.
"""

import json
from typing import Any

from sqlmodel import Session, SQLModel, create_engine, select

from ..config import settings
from ..observability.logging import get_logger
from ..observability.metrics import database_metrics
from .models import ModelContextDB

logger = get_logger("database.operations")


class DatabaseManager:
    """Manages database operations with proper error handling and metrics."""

    def __init__(self):
        self.engine = create_engine(
            settings.get_database_url(),
            echo=settings.database_echo
        )
        self.setup_database()

    def setup_database(self):
        """Create database tables and initialize with sample data."""
        try:
            SQLModel.metadata.create_all(self.engine)
            logger.info("Database tables created successfully")
            self._initialize_sample_data()
        except Exception as e:
            logger.error("Failed to setup database", error=str(e))
            raise

    @database_metrics("select", "modelcontext")
    def get_model_context(self, model_id: str) -> ModelContextDB | None:
        """Get model context by ID."""
        try:
            with Session(self.engine) as session:
                model = session.get(ModelContextDB, model_id)
                if model:
                    logger.debug("Model context retrieved", model_id=model_id)
                else:
                    logger.warning("Model context not found", model_id=model_id)
                return model
        except Exception as e:
            logger.error("Failed to get model context", model_id=model_id, error=str(e))
            raise

    @database_metrics("select", "modelcontext")
    def list_models(self) -> list[dict[str, Any]]:
        """List all models with basic information."""
        try:
            with Session(self.engine) as session:
                models = session.exec(select(ModelContextDB)).all()
                result = [
                    {
                        "id": model.id,
                        "version": model.version,
                        "status": model.status
                    }
                    for model in models
                ]
                logger.info("Models listed", count=len(result))
                return result
        except Exception as e:
            logger.error("Failed to list models", error=str(e))
            raise

    @database_metrics("insert", "modelcontext")
    def add_model(
        self,
        model_id: str,
        version: str,
        status: str,
        parameters: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None
    ) -> ModelContextDB:
        """Add a new model context."""
        try:
            # Check if model already exists
            existing_model = self.get_model_context(model_id)
            if existing_model:
                raise ValueError(f"Model ID '{model_id}' already exists")

            # Convert dicts to JSON strings
            parameters_str = json.dumps(parameters or {})
            metrics_str = json.dumps(metrics) if metrics else None

            new_model = ModelContextDB(
                id=model_id,
                version=version,
                status=status,
                parameters=parameters_str,
                metrics=metrics_str
            )

            with Session(self.engine) as session:
                session.add(new_model)
                session.commit()
                session.refresh(new_model)

            logger.info("Model added successfully", model_id=model_id)
            return new_model

        except Exception as e:
            logger.error("Failed to add model", model_id=model_id, error=str(e))
            raise

    @database_metrics("update", "modelcontext")
    def update_model(
        self,
        model_id: str,
        version: str | None = None,
        status: str | None = None,
        parameters: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None
    ) -> ModelContextDB | None:
        """Update an existing model context."""
        try:
            with Session(self.engine) as session:
                model = session.get(ModelContextDB, model_id)
                if not model:
                    logger.warning("Model not found for update", model_id=model_id)
                    return None

                # Update fields if provided
                if version is not None:
                    model.version = version
                if status is not None:
                    model.status = status
                if parameters is not None:
                    model.parameters = json.dumps(parameters)
                if metrics is not None:
                    model.metrics = json.dumps(metrics)

                session.add(model)
                session.commit()
                session.refresh(model)

            logger.info("Model updated successfully", model_id=model_id)
            return model

        except Exception as e:
            logger.error("Failed to update model", model_id=model_id, error=str(e))
            raise

    @database_metrics("delete", "modelcontext")
    def delete_model(self, model_id: str) -> bool:
        """Delete a model context."""
        try:
            with Session(self.engine) as session:
                model = session.get(ModelContextDB, model_id)
                if not model:
                    logger.warning("Model not found for deletion", model_id=model_id)
                    return False

                session.delete(model)
                session.commit()

            logger.info("Model deleted successfully", model_id=model_id)
            return True

        except Exception as e:
            logger.error("Failed to delete model", model_id=model_id, error=str(e))
            raise

    def get_model_context_dict(self, model_id: str) -> dict[str, Any] | None:
        """Get model context as dictionary with parsed JSON fields."""
        model = self.get_model_context(model_id)
        if not model:
            return None

        try:
            parameters_dict = json.loads(model.parameters or "{}")
            metrics_dict = json.loads(model.metrics or "null")

            return {
                "id": model.id,
                "version": model.version,
                "status": model.status,
                "parameters": parameters_dict,
                "metrics": metrics_dict,
            }
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON fields", model_id=model_id, error=str(e))
            # Return with raw strings if JSON parsing fails
            return {
                "id": model.id,
                "version": model.version,
                "status": model.status,
                "parameters": model.parameters,
                "metrics": model.metrics,
            }

    def _initialize_sample_data(self):
        """Initialize database with sample data if empty."""
        try:
            with Session(self.engine) as session:
                # Check if table is empty
                existing_models = session.exec(select(ModelContextDB)).first()
                if existing_models is None:
                    logger.info("Database is empty, initializing with sample data")

                    sample_model = ModelContextDB(
                        id="model_abc",
                        version="1.2.0",
                        status="active",
                        parameters=json.dumps({"lr": 0.01, "batch_size": 32}),
                        metrics=json.dumps({"accuracy": 0.95, "loss": 0.05})
                    )

                    session.add(sample_model)
                    session.commit()
                    logger.info("Sample data added successfully")
                else:
                    logger.info("Database already contains data")
        except Exception as e:
            logger.error("Failed to initialize sample data", error=str(e))
            # Don't raise here as this is not critical

    def health_check(self) -> dict[str, Any]:
        """Perform database health check."""
        try:
            with Session(self.engine) as session:
                # Simple query to test connection
                result = session.exec(select(ModelContextDB)).first()

            return {
                "status": "healthy",
                "database_url": settings.get_database_url(),
                "tables_exist": True,
                "sample_data_exists": result is not None
            }
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
                "database_url": settings.get_database_url(),
            }


# Global database manager instance
_database_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance."""
    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager()
    return _database_manager


def initialize_database():
    """Initialize the database manager."""
    get_database_manager()
    logger.info("Database manager initialized")
