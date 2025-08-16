"""
Tests for health check functionality.
"""

import pytest
from fastapi.testclient import TestClient

from lc_mcp_app.server import create_app
from lc_mcp_app.config import settings


@pytest.fixture
def client():
    """Create a test client."""
    # Override settings for testing
    settings.environment = "testing"
    settings.api_keys = []  # Disable auth for testing
    settings.metrics_enabled = False
    
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["version"] == "0.1.0"
    assert data["environment"] == "testing"
    assert "mcp_server" in data
    assert "tools" in data
    assert "timestamp" in data


def test_health_endpoint_structure(client):
    """Test health endpoint response structure."""
    response = client.get("/health")
    data = response.json()
    
    # Check required fields
    required_fields = ["status", "version", "environment", "mcp_server", "tools", "timestamp"]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Check MCP server info structure
    mcp_info = data["mcp_server"]
    assert "url" in mcp_info
    assert "healthy" in mcp_info
    assert isinstance(mcp_info["healthy"], bool)
    
    # Check tools info structure
    tools_info = data["tools"]
    assert "total_tools" in tools_info
    assert isinstance(tools_info["total_tools"], int)


def test_metrics_endpoint_disabled(client):
    """Test metrics endpoint when disabled."""
    response = client.get("/metrics")
    assert response.status_code == 404
    assert "Metrics disabled" in response.text
