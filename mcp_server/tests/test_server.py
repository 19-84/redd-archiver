# ABOUTME: Unit tests for the reddarchiver-mcp server
# ABOUTME: Tests CLI argument parsing, environment variable handling, and OpenAPI fetching

"""
Tests for Redd-Archiver MCP Server

These tests verify:
- CLI argument parsing
- Environment variable fallback
- OpenAPI spec fetching
- Error handling for API connectivity issues
"""

import os
from unittest.mock import patch

import httpx
import pytest

# Import from parent directory
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import get_api_url, fetch_openapi_spec, parse_args, DEFAULT_API_URL


class TestGetApiUrl:
    """Tests for get_api_url function."""

    def test_cli_argument_takes_priority(self):
        """CLI argument should override environment variable."""
        with patch.dict(os.environ, {"REDDARCHIVER_API_URL": "http://env-url.com"}):
            result = get_api_url("http://cli-url.com")
            assert result == "http://cli-url.com"

    def test_environment_variable_fallback(self):
        """Environment variable should be used when CLI arg not provided."""
        with patch.dict(os.environ, {"REDDARCHIVER_API_URL": "http://env-url.com"}):
            result = get_api_url(None)
            assert result == "http://env-url.com"

    def test_default_fallback(self):
        """Default URL should be used when no config provided."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove REDDARCHIVER_API_URL if it exists
            os.environ.pop("REDDARCHIVER_API_URL", None)
            result = get_api_url(None)
            assert result == DEFAULT_API_URL

    def test_trailing_slash_removed_cli(self):
        """Trailing slash should be removed from CLI URL."""
        result = get_api_url("http://example.com/")
        assert result == "http://example.com"

    def test_trailing_slash_removed_env(self):
        """Trailing slash should be removed from environment URL."""
        with patch.dict(os.environ, {"REDDARCHIVER_API_URL": "http://example.com/"}):
            result = get_api_url(None)
            assert result == "http://example.com"


class TestParseArgs:
    """Tests for parse_args function."""

    def test_default_api_url_is_none(self):
        """Default API URL should be None (uses env var or default)."""
        with patch("sys.argv", ["server.py"]):
            args = parse_args()
            assert args.api_url is None

    def test_api_url_argument(self):
        """--api-url argument should be parsed correctly."""
        with patch("sys.argv", ["server.py", "--api-url", "http://test.com"]):
            args = parse_args()
            assert args.api_url == "http://test.com"


class TestFetchOpenApiSpec:
    """Tests for fetch_openapi_spec function."""

    def test_successful_fetch(self, respx_mock):
        """Successful OpenAPI fetch should return spec dict."""
        mock_spec = {
            "openapi": "3.0.3",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
        }

        respx_mock.get("http://test.com/api/v1/openapi.json").mock(
            return_value=httpx.Response(200, json=mock_spec)
        )

        result = fetch_openapi_spec("http://test.com")
        assert result == mock_spec

    def test_connection_error(self, respx_mock):
        """Connection error should raise httpx.ConnectError."""
        respx_mock.get("http://test.com/api/v1/openapi.json").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(httpx.ConnectError):
            fetch_openapi_spec("http://test.com")

    def test_http_error(self, respx_mock):
        """HTTP error should raise httpx.HTTPStatusError."""
        respx_mock.get("http://test.com/api/v1/openapi.json").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(httpx.HTTPStatusError):
            fetch_openapi_spec("http://test.com")

    def test_invalid_json(self, respx_mock):
        """Invalid JSON should raise ValueError."""
        respx_mock.get("http://test.com/api/v1/openapi.json").mock(
            return_value=httpx.Response(200, text="not json")
        )

        with pytest.raises(ValueError):
            fetch_openapi_spec("http://test.com")


@pytest.fixture
def respx_mock():
    """Fixture to provide respx mock for HTTP requests."""
    import respx
    with respx.mock:
        yield respx


class TestIntegration:
    """Integration tests (require running API)."""

    @pytest.mark.skip(reason="Requires running API - run manually")
    def test_real_api_connection(self):
        """Test connection to real API (manual test)."""
        spec = fetch_openapi_spec("http://localhost:5000")
        assert "openapi" in spec
        assert "paths" in spec
        assert len(spec["paths"]) > 0
