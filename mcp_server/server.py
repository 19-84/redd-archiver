#!/usr/bin/env python3
# ABOUTME: MCP server for Redd-Archiver API using FastMCP's OpenAPI integration
# ABOUTME: Auto-generates 30+ MCP tools from the API's OpenAPI specification with MCP resources

"""
Redd-Archiver MCP Server v1.0

An MCP (Model Context Protocol) server that exposes the Redd-Archiver REST API
as AI-accessible tools. Uses FastMCP's OpenAPI integration to automatically
generate tools from the API's OpenAPI specification.

Features:
- Auto-generates 30+ MCP tools from OpenAPI spec
- MCP resources for quick access to common data
- Supports environment variable and CLI configuration
- Graceful error handling for API connectivity issues
- Async HTTP client with connection pooling

Important - Token Limits:
For large queries (>25 items), use API parameters to control response size:
- limit=10-25 (keep responses manageable)
- fields=id,title,score (select specific fields)
- max_body_length=200 (truncate text content)

Usage:
    # With CLI argument
    python server.py --api-url http://localhost:5000

    # With environment variable
    export REDDARCHIVER_API_URL=http://localhost:5000
    python server.py

    # Default (localhost:5000)
    python server.py
"""

import argparse
import os
import sys
from typing import Optional

import httpx
from fastmcp import FastMCP


# Default API URL if not specified
DEFAULT_API_URL = "http://localhost:5000"

# OpenAPI endpoint path
OPENAPI_PATH = "/api/v1/openapi.json"

# Global client reference for resources
_http_client: Optional[httpx.AsyncClient] = None


def get_api_url(cli_url: Optional[str] = None) -> str:
    """
    Get API URL from CLI argument, environment variable, or default.

    Priority:
    1. CLI argument (--api-url)
    2. Environment variable (REDDARCHIVER_API_URL)
    3. Default (http://localhost:5000)

    Args:
        cli_url: URL passed via command line argument

    Returns:
        API base URL string
    """
    if cli_url:
        return cli_url.rstrip("/")

    env_url = os.environ.get("REDDARCHIVER_API_URL")
    if env_url:
        return env_url.rstrip("/")

    return DEFAULT_API_URL


def fetch_openapi_spec(api_url: str) -> dict:
    """
    Fetch OpenAPI specification from the API.

    Args:
        api_url: Base URL of the Redd-Archiver API

    Returns:
        OpenAPI specification as dictionary

    Raises:
        httpx.HTTPError: If the API is unreachable or returns an error
        ValueError: If the response is not valid JSON
    """
    openapi_url = f"{api_url}{OPENAPI_PATH}"

    try:
        response = httpx.get(openapi_url, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError as e:
        print(f"Error: Cannot connect to API at {api_url}", file=sys.stderr)
        print(f"       Make sure the Redd-Archiver search server is running.", file=sys.stderr)
        print(f"       Details: {e}", file=sys.stderr)
        raise
    except httpx.HTTPStatusError as e:
        print(f"Error: API returned status {e.response.status_code}", file=sys.stderr)
        print(f"       URL: {openapi_url}", file=sys.stderr)
        raise
    except ValueError as e:
        print(f"Error: Invalid JSON response from {openapi_url}", file=sys.stderr)
        raise


# ============================================================================
# MCP RESOURCES (Quick access to common data)
# ============================================================================

# ============================================================================
# MCP PROMPTS (LLM Guidance)
# ============================================================================

def add_prompts(mcp: FastMCP) -> None:
    """
    Add MCP prompts to guide LLM usage of high-risk endpoints.

    Prompts provide best practices and warnings that LLMs can
    reference before making tool calls.

    Args:
        mcp: FastMCP server instance to add prompts to
    """

    @mcp.prompt("token-safety-guide")
    def token_safety_prompt():
        """
        Best practices for avoiding token overflow when using Redd-Archiver MCP tools.

        READ THIS BEFORE using Full_text_search, List_posts, or List_comments tools.
        """
        return """
🔴 HIGH-RISK TOOLS (Token Overflow Risk)

These tools can exceed 200KB responses if used incorrectly:

1. Full_text_search
   ❌ NEVER: limit=50 (produces 218KB response)
   ✅ ALWAYS: limit=10-25, max_body_length=200

2. List_posts
   ❌ AVOID: limit>25 without fields parameter
   ✅ ALWAYS: limit=10-25, fields="id,title,score,subreddit"

3. List_comments
   ❌ AVOID: Large limits without max_body_length
   ✅ ALWAYS: limit=10-25, max_body_length=200

4. Get_post_context
   ❌ AVOID: top_comments=50, max_depth=5
   ✅ ALWAYS: top_comments=5, max_depth=2, max_body_length=150

💡 TOKEN SAVINGS STRATEGIES:

1. Field Selection (62% savings)
   - Instead of: List_posts(limit=20)
   - Use: List_posts(limit=20, fields="id,title,score")

2. Text Truncation (40-60% savings)
   - Always set max_body_length=200 for text-heavy queries

3. Pagination (avoids large responses)
   - Instead of: limit=50
   - Use: limit=10, page=1 then page=2 if needed

✅ SAFE TOOLS (No parameters needed):
- Archive_statistics, Health_check
- Get_post, Get_comment, Get_user (single items)
- Batch operations (reasonable defaults)
- All summary endpoints
- All resources (archive://*)
"""

    @mcp.prompt("search-query-builder")
    def search_query_prompt():
        """
        How to build effective search queries with operators.

        Use this to learn search syntax before calling Full_text_search.
        """
        return """
SEARCH OPERATORS:

"exact phrase" - Match exact phrase
OR - Boolean OR (must be uppercase)
-exclude - Exclude term from results
sub:subreddit - Filter by subreddit
author:username - Filter by author
score:N - Minimum score (score:50, score:100)
type:post or type:comment - Result type
sort:score or sort:date - Sort order

EXAMPLES:

1. Find censorship posts with high score:
   q=censorship score:50 type:post&limit=10

2. Search specific subreddit:
   q="moderator abuse" sub:politics&limit=15

3. Complex query:
   q=banned OR removed -troll score:20 type:post&limit=10

4. User investigation:
   q=author:username type:post&limit=25

BEST PRACTICES:
- Start with limit=10, increase to 15-25 if needed
- Always set max_body_length=200 for search
- Use type=posts or type=comments (not "all")
- Combine with score: for quality results
"""


def add_resources(mcp: FastMCP) -> None:
    """
    Add MCP resources for frequently accessed archive data.

    Resources provide quick access to common queries without
    needing to call tools.

    Args:
        mcp: FastMCP server instance to add resources to
    """

    @mcp.resource("archive://stats")
    async def get_stats_resource():
        """Current archive statistics (posts, comments, users, subreddits)."""
        response = await _http_client.get("/stats")
        return response.json()

    @mcp.resource("archive://subreddits")
    async def get_subreddits_resource():
        """List of all subreddits in the archive with post counts."""
        response = await _http_client.get("/subreddits")
        return response.json()

    @mcp.resource("archive://top-posts")
    async def get_top_posts_resource():
        """Top 25 posts by score across all subreddits."""
        response = await _http_client.get("/posts?sort=score&limit=25&fields=id,title,score,subreddit,num_comments")
        return response.json()

    @mcp.resource("archive://recent-posts")
    async def get_recent_posts_resource():
        """Most recent 25 posts across all subreddits."""
        response = await _http_client.get("/posts?sort=created_utc&limit=25&fields=id,title,score,subreddit,created_at")
        return response.json()

    @mcp.resource("archive://search-help")
    async def get_search_help_resource():
        """
        Search operator documentation and examples.

        Returns help text explaining supported search operators.
        """
        return {
            "operators": [
                {"operator": '"phrase"', "example": '"reddit censorship"', "description": "Exact phrase search"},
                {"operator": "OR", "example": "banned OR removed", "description": "Boolean OR (uppercase)"},
                {"operator": "-exclude", "example": "censorship -moderator", "description": "Exclude term"},
                {"operator": "sub:", "example": "sub:privacy", "description": "Filter by subreddit"},
                {"operator": "author:", "example": "author:username", "description": "Filter by author"},
                {"operator": "score:", "example": "score:100", "description": "Minimum score"},
                {"operator": "type:", "example": "type:post", "description": "Result type (post|comment)"},
                {"operator": "sort:", "example": "sort:score", "description": "Sort order"},
            ],
            "examples": [
                "censorship OR banned",
                '"shadow ban" sub:technology',
                "moderator abuse -troll score:10",
                'type:post "without explanation"'
            ],
            "token_limits": {
                "warning": "Large queries (limit >25) may exceed token limits",
                "recommendations": [
                    "Use limit=10-25 (not 50-100) to keep responses manageable",
                    "Use fields parameter to select only needed fields",
                    "Use max_body_length parameter to truncate text content",
                    "Use pagination (page parameter) for large result sets"
                ]
            }
        }


def create_mcp_server(api_url: str) -> FastMCP:
    """
    Create MCP server from OpenAPI specification.

    Args:
        api_url: Base URL of the Redd-Archiver API

    Returns:
        Configured FastMCP server instance with resources
    """
    global _http_client

    # Fetch OpenAPI spec
    print(f"Fetching OpenAPI spec from {api_url}{OPENAPI_PATH}...", file=sys.stderr)
    openapi_spec = fetch_openapi_spec(api_url)
    print(f"Successfully fetched OpenAPI spec (v{openapi_spec.get('info', {}).get('version', 'unknown')})", file=sys.stderr)

    # Create async HTTP client for API requests
    _http_client = httpx.AsyncClient(
        base_url=f"{api_url}/api/v1",
        timeout=60.0,
        follow_redirects=True,
        headers={
            "User-Agent": "reddarchiver-mcp/1.0.0",
            "Accept": "application/json",
        },
    )

    # Create MCP server from OpenAPI spec
    print("Generating MCP tools from OpenAPI specification...", file=sys.stderr)
    mcp = FastMCP.from_openapi(
        openapi_spec=openapi_spec,
        client=_http_client,
        name="Redd-Archiver MCP Server",
    )

    # Add MCP prompts for LLM guidance
    print("Adding MCP prompts for LLM guidance...", file=sys.stderr)
    add_prompts(mcp)

    # Add MCP resources for common data
    print("Adding MCP resources for common queries...", file=sys.stderr)
    add_resources(mcp)

    # Count generated tools, prompts, and resources
    tool_count = len(openapi_spec.get("paths", {}))
    print(f"Generated {tool_count} MCP tools from API endpoints", file=sys.stderr)
    print(f"Added 2 MCP prompts for token safety guidance", file=sys.stderr)
    print(f"Added 5 MCP resources for quick access to common data", file=sys.stderr)

    return mcp


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="MCP server for Redd-Archiver API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Connect to local API
    python server.py --api-url http://localhost:5000

    # Connect to remote API
    python server.py --api-url https://archive.example.com

    # Use environment variable
    export REDDARCHIVER_API_URL=http://localhost:5000
    python server.py

Environment Variables:
    REDDARCHIVER_API_URL    Base URL of the Redd-Archiver API
                            (default: http://localhost:5000)

Token Limit Tips:
    For large queries, use API parameters to control response size:
    - limit=10-25 (default: 25, max: 100)
    - fields=id,title,score (comma-separated field names)
    - max_body_length=200 (truncate text content)
        """,
    )

    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="Base URL of the Redd-Archiver API (overrides REDDARCHIVER_API_URL)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="reddarchiver-mcp 1.0.0",
    )

    return parser.parse_args()


def main() -> None:
    """
    Main entry point for the MCP server.

    Parses arguments, creates the MCP server, and runs it.
    """
    args = parse_args()

    # Get API URL
    api_url = get_api_url(args.api_url)
    print(f"Connecting to Redd-Archiver API at {api_url}", file=sys.stderr)

    try:
        # Create and run MCP server
        mcp = create_mcp_server(api_url)
        print("MCP server ready. Waiting for connections...", file=sys.stderr)
        print("", file=sys.stderr)
        print("⚠️  Token Limit Warning:", file=sys.stderr)
        print("   Large queries (limit >25) may exceed token limits.", file=sys.stderr)
        print("   Use: limit=10-25, fields=..., max_body_length=200", file=sys.stderr)
        print("", file=sys.stderr)
        mcp.run()
    except httpx.HTTPError:
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutting down MCP server...", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
