# Redd-Archiver MCP Server

MCP (Model Context Protocol) server that exposes the Redd-Archiver REST API as AI-accessible tools. Uses [FastMCP](https://gofastmcp.com) to auto-generate 30+ tools from the API's OpenAPI specification.

## Features

- **29 MCP tools** auto-generated from OpenAPI (posts, comments, users, search, aggregation)
- **5 MCP resources** for instant data access (`archive://stats`, `archive://top-posts`, etc.)
- **2 MCP prompts** for LLM guidance on token safety
- **LLM-visible warnings** embedded in tool descriptions (⚠️ 🔴 ✅ emojis)
- **Token overflow prevention** via parameter guidance (limit, fields, max_body_length)
- **Docker & local deployment** with simple configuration
- **100% test coverage** (11/11 passing)

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Running Redd-Archiver search server (see main project README)

### Installation

```bash
# Navigate to MCP server directory
cd mcp_server/

# Install dependencies with uv
uv sync

# Or with pip
pip install -e .
```

### Running Locally

```bash
# Start the Redd-Archiver search server first (from project root)
docker compose up -d search-server

# Run MCP server with CLI argument
uv run python server.py --api-url http://localhost:5000

# Or with environment variable
export REDDARCHIVER_API_URL=http://localhost:5000
uv run python server.py

# Default (localhost:5000)
uv run python server.py
```

### Running with Docker

```bash
# From project root, start MCP server with dependencies
docker compose up -d mcp-server

# View logs
docker compose logs -f mcp-server

# Stop
docker compose stop mcp-server
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDDARCHIVER_API_URL` | `http://localhost:5000` | Base URL of the Redd-Archiver API |
| `REDDARCHIVER_MAX_RESPONSE_SIZE` | `50` | Maximum response size in KB before truncation |

### CLI Arguments

| Argument | Description |
|----------|-------------|
| `--api-url URL` | Base URL of the Redd-Archiver API (overrides env var) |
| `--max-response-size N` | Maximum response size in KB (default: 50) |
| `--version` | Show version and exit |
| `--help` | Show help message |

## Claude Desktop Configuration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "reddarchiver": {
      "command": "uv",
      "args": ["--directory", "/path/to/redd-archiver/mcp_server", "run", "python", "server.py"],
      "env": {
        "REDDARCHIVER_API_URL": "http://localhost:5000"
      }
    }
  }
}
```

Or if using a remote API:

```json
{
  "mcpServers": {
    "reddarchiver": {
      "command": "uv",
      "args": ["--directory", "/path/to/redd-archiver/mcp_server", "run", "python", "server.py", "--api-url", "https://archive.example.com"]
    }
  }
}
```

## Available MCP Tools

All tools are auto-generated from the API's OpenAPI specification with friendly, descriptive names for better usability.

### System Tools (4)
- `check_health` - Check API and database health status
- `get_archive_stats` - Get archive statistics and instance metadata
- `get_api_schema` - API capabilities discovery (MCP-optimized)
- `get_openapi_spec` - Get OpenAPI 3.0 specification

### Posts Tools (9)
- `list_posts` - List posts with filtering, sorting, pagination
- `get_post` - Get single post by ID
- `list_post_comments` - Get comments for a post
- `get_post_with_comments` - Post + top comments in one call (MCP-optimized)
- `get_comment_tree` - Hierarchical comment structure
- `find_related_posts` - Find similar posts via FTS
- `get_random_posts` - Random post sampling
- `aggregate_posts` - Aggregate by author/subreddit/time
- `batch_get_posts` - Batch lookup by IDs

### Comments Tools (5)
- `list_comments` - List comments with filtering
- `get_comment` - Get single comment by ID
- `get_random_comments` - Random comment sampling
- `aggregate_comments` - Aggregate statistics
- `batch_get_comments` - Batch lookup by IDs

### Users Tools (7)
- `list_users` - List users with sorting
- `get_user_profile` - Get user profile and statistics
- `get_user_summary` - Quick user overview (MCP-optimized)
- `list_user_posts` - User's posts
- `list_user_comments` - User's comments
- `batch_get_users` - Batch lookup by usernames
- `aggregate_users` - Aggregate user statistics

### Subreddits Tools (3)
- `list_subreddits` - List subreddits with statistics
- `get_subreddit_stats` - Subreddit detailed statistics
- `get_subreddit_summary` - Subreddit overview (MCP-optimized)

### Search Tools (2)
- `search_archive` - Full-text search with Google-style operators
- `explain_search_query` - Query parsing debugger

## MCP Resources

Resources provide quick access to frequently requested data without needing to call tools:

| URI | Description |
|-----|-------------|
| `archive://stats` | Current archive statistics (posts, comments, users, subreddits) |
| `archive://subreddits` | List of all subreddits in the archive |
| `archive://top-posts` | Top 25 posts by score (fields optimized) |
| `archive://recent-posts` | Most recent 25 posts (fields optimized) |
| `archive://search-help` | Search operator documentation with examples |

**Usage in Claude Code**: Resources are automatically available when the MCP server is connected.

## ⚠️  Token Limit Management

**IMPORTANT**: Some tools can exceed Claude Code's token limits without proper parameters.

### High-Risk Tools

| Tool | Safe Usage | Why |
|------|------------|-----|
| `Full_text_search` | limit=10-25, max_body_length=200 | ⚠️  Can reach 218KB at limit=50 |
| `List_posts` | limit=10-25, fields="id,title,score" | Large responses without fields |
| `List_comments` | limit=10-25, max_body_length=200 | Comment bodies can be huge |
| `Get_post_context` | top_comments=5, max_body_length=150 | Multiple comments included |

### Token Savings Strategies

```python
# ❌ BAD: Will likely overflow
Full_text_search(q="censorship", limit=50)

# ✅ GOOD: Safe and efficient
Full_text_search(q="censorship", limit=10, max_body_length=200)

# 💡 BEST: Maximum efficiency
List_posts(limit=15, fields="id,title,score,subreddit")  # 62% smaller
```

**All tool descriptions include LLM-visible warnings (⚠️ 🔴 ✅) to guide safe usage.**

## Search Operators

| Operator | Example | Description |
|----------|---------|-------------|
| `"phrase"` | `"reddit censorship"` | Exact phrase |
| `OR` | `banned OR removed` | Boolean OR |
| `-exclude` | `censorship -moderator` | Exclude term |
| `sub:` | `sub:privacy` | Filter by subreddit |
| `author:` | `author:username` | Filter by author |
| `score:` | `score:100` | Minimum score |

## Development

### Running Tests

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v
```

### Project Structure

```
mcp_server/
├── pyproject.toml    # Package configuration
├── server.py         # Main MCP server
├── __init__.py       # Package marker
├── Dockerfile        # Docker image
├── README.md         # This file
└── tests/
    └── test_server.py
```

## Troubleshooting

### "Cannot connect to API"

1. Ensure the Redd-Archiver search server is running:
   ```bash
   docker compose ps search-server
   ```

2. Check the API URL is correct:
   ```bash
   curl http://localhost:5000/api/v1/health
   ```

3. If using Docker, ensure both containers are on the same network.

### "Invalid JSON response"

The API might be returning an error. Check:
```bash
curl http://localhost:5000/api/v1/openapi.json | jq
```

### Claude Desktop connection issues

1. Verify the MCP server starts without errors:
   ```bash
   uv run python server.py --api-url http://localhost:5000
   ```

2. Check Claude Desktop logs for MCP connection errors.

3. Ensure the path in `claude_desktop_config.json` is absolute.

## Additional Documentation

- `docs/TOKEN-LIMITS.md` - Complete token management reference
- `docs/LLM-GUIDANCE.md` - Technical details on guidance system
- `docs/` - Development history, testing reports, API fixes

## License

This project is released under the Unlicense. See the main project [LICENSE](../LICENSE) file.
