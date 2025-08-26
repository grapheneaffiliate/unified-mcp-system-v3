"""
Test configuration and fixtures for unified-mcp-system tests.
"""

import os
import pytest
import responses


@pytest.fixture(autouse=True)
def mock_external_apis():
    """
    Mock external API calls in CI environment to avoid auth/network issues.
    This allows tests to focus on MCP functionality without external dependencies.
    """
    if os.getenv("CI") == "true":
        with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            # Mock any external API calls with generic success responses
            rsps.add(
                responses.GET,
                responses.matchers.urlencoded_params_matcher({}),
                json={"ok": True, "mock": True, "ci_mode": True},
                status=200
            )
            rsps.add(
                responses.POST,
                responses.matchers.urlencoded_params_matcher({}),
                json={"ok": True, "mock": True, "ci_mode": True},
                status=200
            )
            yield
    else:
        # In local development, don't mock anything
        yield


@pytest.fixture
def ci_mode():
    """Fixture to detect if running in CI environment."""
    return os.getenv("CI") == "true"


@pytest.fixture
def mock_auth_headers():
    """Provide mock authentication headers for CI tests."""
    if os.getenv("CI") == "true":
        return {
            "Authorization": "Bearer test-token",
            "X-API-Key": "test-key",
            "X-Bypass-Auth": "ci-mode"
        }
    return {}


@pytest.fixture
def test_mode():
    """Fixture to enable test mode behaviors."""
    original = os.environ.get("TEST_MODE")
    os.environ["TEST_MODE"] = "true"
    yield True
    if original is None:
        os.environ.pop("TEST_MODE", None)
    else:
        os.environ["TEST_MODE"] = original
