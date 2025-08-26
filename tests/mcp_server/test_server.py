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
    assert data["result"]["protocolVersion"] == "2024-11-05"
    assert "capabilities" in data["result"]
    assert "serverInfo" in data["result"]


def test_jsonrpc_tools_list(client):
    """Test MCP tools/list method."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 1
    }

    response = client.post("/jsonrpc", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert "tools" in data["result"]
    assert len(data["result"]["tools"]) > 0
    # Check that tools have proper structure
    for tool in data["result"]["tools"]:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool


def test_jsonrpc_health_check_tool(client):
    """Test health check tool via JSON-RPC."""
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "health_check",
            "arguments": {}
        },
        "id": 1
    }

    response = client.post("/jsonrpc", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "result" in data
    assert "content" in data["result"]
    assert len(data["result"]["content"]) > 0
    assert data["result"]["content"][0]["type"] == "text"


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
