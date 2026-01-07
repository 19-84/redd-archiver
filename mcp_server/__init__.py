# ABOUTME: Package marker for reddarchiver-mcp, an MCP server for the Redd-Archiver API
# ABOUTME: This package exposes 30+ Reddit archive API endpoints as MCP tools

"""
reddarchiver-mcp: MCP Server for Redd-Archiver API

This package provides an MCP (Model Context Protocol) server that exposes
the Redd-Archiver REST API as AI-accessible tools using FastMCP.

Usage:
    # Local development
    uv run python server.py --api-url http://localhost:5000

    # With environment variable
    export REDDARCHIVER_API_URL=http://localhost:5000
    uv run python server.py

    # Docker
    docker compose up mcp-server
"""

__version__ = "1.0.0"
__author__ = "Redd-Archiver Contributors"
