"""
Tests for the main server functionality.
"""

import pytest
from fastapi.testclient import TestClient

from mcp_agent.config import settings
from mcp_agent.server import create_app


@pytest.fixture
def client():
    """Create a test client."""
    # Override settings for testing
    settings.environment = "testing"
    settings.database_url = "sqlite:///:memory:"
    settings.sandbox_enabled = False
    settings.metrics_enabled = False

    app = create_app()
    return TestClient(app)


def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["version"] == "1.0.0"
    assert data["environment"] == "testing"


def test_metrics_endpoint_disabled(client):
    """Test metrics endpoint when disabled."""
    response = client.get("/metrics")
    assert response.status_code == 404


def test_jsonrpc_initialize(client):
    """Test MCP initialize method."""
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {},
        "id": 1
    }

    response = client.post("/jsonrpc", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert data["result"]["protocol_version"] == "2024-11-05"


def test_jsonrpc_capabilities_list(client):
    """Test MCP capabilities/list method."""
    payload = {
        "jsonrpc": "2.0",
        "method": "capabilities/list",
        "params": {},
        "id": 1
    }

    response = client.post("/jsonrpc", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert "capabilities" in data["result"]
    assert len(data["result"]["capabilities"]) > 0


def test_jsonrpc_health_check_tool(client):
    """Test health check tool via JSON-RPC."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tool/health_check",
        "params": {},
        "id": 1
    }

    response = client.post("/jsonrpc", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert data["result"]["status"] in ["healthy", "degraded"]


def test_jsonrpc_invalid_method(client):
    """Test invalid JSON-RPC method."""
    payload = {
        "jsonrpc": "2.0",
        "method": "invalid/method",
        "params": {},
        "id": 1
    }

    response = client.post("/jsonrpc", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32601
    assert "Method not found" in data["error"]["message"]


def test_jsonrpc_invalid_json(client):
    """Test invalid JSON in request."""
    response = client.post(
        "/jsonrpc",
        content="invalid json",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 200

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == -32700
    assert "Parse error" in data["error"]["message"]
