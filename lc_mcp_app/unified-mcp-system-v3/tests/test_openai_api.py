"""
Tests for OpenAI-compatible API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from lc_mcp_app.config import settings
from lc_mcp_app.server import create_app


@pytest.fixture
def client():
    """Create a test client."""
    # Override settings for testing
    settings.environment = "testing"
    settings.api_keys = []  # Disable auth for testing
    settings.metrics_enabled = False

    app = create_app()
    return TestClient(app)


def test_list_models(client):
    """Test the /v1/models endpoint."""
    response = client.get("/v1/models")
    assert response.status_code == 200

    data = response.json()
    assert data["object"] == "list"
    assert "data" in data
    assert len(data["data"]) > 0

    # Check model structure
    model = data["data"][0]
    assert "id" in model
    assert "object" in model
    assert model["object"] == "model"
    assert "created" in model
    assert "owned_by" in model


def test_chat_completions_non_streaming(client):
    """Test non-streaming chat completions."""
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Hello, test message"}
        ],
        "stream": False
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert data["object"] == "chat.completion"
    assert "created" in data
    assert "model" in data
    assert "choices" in data
    assert len(data["choices"]) > 0

    # Check choice structure
    choice = data["choices"][0]
    assert "index" in choice
    assert "message" in choice
    assert "finish_reason" in choice

    # Check message structure
    message = choice["message"]
    assert message["role"] == "assistant"
    assert "content" in message
    assert isinstance(message["content"], str)


def test_chat_completions_streaming(client):
    """Test streaming chat completions."""
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": "Hello, streaming test"}
        ],
        "stream": True
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"

    # Check that we get streaming data
    content = response.content.decode()
    assert "data: " in content
    assert "[DONE]" in content


def test_chat_completions_invalid_request(client):
    """Test chat completions with invalid request."""
    payload = {
        "model": "gpt-4o-mini",
        "messages": [],  # Empty messages should fail
        "stream": False
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 400


def test_chat_completions_invalid_temperature(client):
    """Test chat completions with invalid temperature."""
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
        "temperature": 3.0,  # Invalid temperature
        "stream": False
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 400


def test_chat_completions_with_parameters(client):
    """Test chat completions with various parameters."""
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
        "max_tokens": 100,
        "temperature": 0.7,
        "top_p": 0.9,
        "stream": False
    }

    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["model"] == "gpt-4o-mini"


def test_tools_endpoint(client):
    """Test the tools listing endpoint."""
    response = client.get("/tools")
    assert response.status_code == 200

    data = response.json()
    assert "tools" in data
    assert "total" in data
    assert "registry_info" in data
    assert isinstance(data["tools"], list)
    assert isinstance(data["total"], int)


@pytest.mark.skip("Requires MCP server running")
def test_tool_execution(client):
    """Test direct tool execution endpoint."""
    response = client.post("/tools/health_check", json={})
    assert response.status_code in [200, 404]  # 404 if tool not found

    if response.status_code == 200:
        data = response.json()
        assert "result" in data
