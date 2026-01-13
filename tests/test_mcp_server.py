#!/usr/bin/env python
"""
ABOUTME: Unit tests for MCP server configuration and URL handling
ABOUTME: Tests API URL resolution, OpenAPI spec fetching, and CLI argument parsing
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Skip entire module if fastmcp is not installed
pytest.importorskip("fastmcp", reason="fastmcp not installed - skipping MCP server tests")

import httpx

# Add mcp_server to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp_server"))

from mcp_server.server import (
    DEFAULT_API_URL,
    OPENAPI_PATH,
    fetch_openapi_spec,
    get_api_url,
    parse_args,
)

# =============================================================================
# URL RESOLUTION TESTS
# =============================================================================


@pytest.mark.unit
class TestGetApiUrl:
    """Tests for get_api_url function."""

    def test_cli_url_has_highest_priority(self):
        """Test CLI argument takes priority over env and default."""
        with patch.dict(os.environ, {"REDDARCHIVER_API_URL": "http://env-url.com"}):
            result = get_api_url("http://cli-url.com")

        assert result == "http://cli-url.com"

    def test_env_variable_second_priority(self):
        """Test environment variable takes priority over default."""
        with patch.dict(os.environ, {"REDDARCHIVER_API_URL": "http://env-url.com"}):
            result = get_api_url(None)

        assert result == "http://env-url.com"

    def test_default_when_no_cli_or_env(self):
        """Test default URL is used when no CLI or env provided."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if it exists
            os.environ.pop("REDDARCHIVER_API_URL", None)
            result = get_api_url(None)

        assert result == DEFAULT_API_URL

    def test_trailing_slash_removed_from_cli(self):
        """Test trailing slash is stripped from CLI URL."""
        result = get_api_url("http://example.com/")

        assert result == "http://example.com"

    def test_trailing_slash_removed_from_env(self):
        """Test trailing slash is stripped from env URL."""
        with patch.dict(os.environ, {"REDDARCHIVER_API_URL": "http://env-url.com/"}):
            result = get_api_url(None)

        assert result == "http://env-url.com"

    def test_empty_cli_uses_env(self):
        """Test empty CLI string falls back to env."""
        with patch.dict(os.environ, {"REDDARCHIVER_API_URL": "http://env-url.com"}):
            result = get_api_url("")

        # Empty string is falsy, so env should be used
        assert result == "http://env-url.com"


# =============================================================================
# CONSTANTS TESTS
# =============================================================================


@pytest.mark.unit
class TestConstants:
    """Tests for module constants."""

    def test_default_api_url_is_localhost(self):
        """Test default API URL points to localhost."""
        assert DEFAULT_API_URL == "http://localhost:5000"

    def test_openapi_path_is_correct(self):
        """Test OpenAPI path constant."""
        assert OPENAPI_PATH == "/api/v1/openapi.json"


# =============================================================================
# OPENAPI SPEC FETCHING TESTS
# =============================================================================


@pytest.mark.unit
class TestFetchOpenApiSpec:
    """Tests for fetch_openapi_spec function."""

    def test_fetch_openapi_spec_success(self):
        """Test successful OpenAPI spec fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "openapi": "3.0.3",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            result = fetch_openapi_spec("http://localhost:5000")

        assert result["openapi"] == "3.0.3"
        assert result["info"]["title"] == "Test API"

    def test_fetch_openapi_spec_connection_error(self):
        """Test connection error handling."""
        with patch("httpx.get", side_effect=httpx.ConnectError("Connection refused")):
            with pytest.raises(httpx.ConnectError):
                fetch_openapi_spec("http://localhost:5000")

    def test_fetch_openapi_spec_http_error(self):
        """Test HTTP error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        with patch("httpx.get", return_value=mock_response):
            with pytest.raises(httpx.HTTPStatusError):
                fetch_openapi_spec("http://localhost:5000")

    def test_fetch_openapi_spec_invalid_json(self):
        """Test invalid JSON response handling."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch("httpx.get", return_value=mock_response):
            with pytest.raises(ValueError):
                fetch_openapi_spec("http://localhost:5000")

    def test_fetch_openapi_spec_constructs_correct_url(self):
        """Test correct URL is constructed."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"openapi": "3.0.3", "paths": {}}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response) as mock_get:
            fetch_openapi_spec("http://example.com")

        mock_get.assert_called_once_with("http://example.com/api/v1/openapi.json", timeout=30.0)


# =============================================================================
# CLI ARGUMENT PARSING TESTS
# =============================================================================


@pytest.mark.unit
class TestParseArgs:
    """Tests for parse_args function."""

    def test_parse_args_default(self):
        """Test default arguments."""
        with patch("sys.argv", ["server.py"]):
            args = parse_args()

        assert args.api_url is None

    def test_parse_args_with_api_url(self):
        """Test --api-url argument."""
        with patch("sys.argv", ["server.py", "--api-url", "http://custom.com"]):
            args = parse_args()

        assert args.api_url == "http://custom.com"

    def test_parse_args_version_flag_exists(self):
        """Test --version flag is configured."""
        with patch("sys.argv", ["server.py", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                parse_args()

        # --version causes sys.exit(0)
        assert exc_info.value.code == 0
