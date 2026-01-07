# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Redd-Archiver v1.0.0 is a PostgreSQL-backed archive generator that transforms compressed data dumps from multiple link aggregator platforms (**Reddit**, **Voat**, **Ruqqus**) into browsable static HTML websites with optional server-side full-text search and MCP/AI integration.

**Key Characteristics:**
- **Multi-Platform Support**: Reddit (.zst), Voat (SQL), Ruqqus (.7z)
- Streaming architecture with constant memory usage regardless of dataset size
- PostgreSQL-only backend (DATABASE_URL required)
- Hybrid output: Static HTML for offline browsing + optional Flask search server
- **REST API v1**: 30+ endpoints with MCP/AI optimization
- **MCP Server**: 29 tools for Claude Desktop/Claude Code integration
- Zero JavaScript design for maximum compatibility

## Build & Run Commands

### Docker Development (Primary Method)

```bash
# Start all services (postgres, builder, search-server, nginx)
sudo docker compose up -d --build

# Run archive generator (Reddit basic)
sudo docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst

# Voat (using pre-split files - 2-5 minutes)
sudo docker compose exec reddarchiver-builder python reddarc.py /data/voat_split/submissions/ \
  --subverse privacy \
  --comments-file /data/voat_split/comments/privacy_comments.sql.gz \
  --submissions-file /data/voat_split/submissions/privacy_submissions.sql.gz \
  --platform voat \
  --output /output/

# Ruqqus (.7z files - p7zip included in Docker)
sudo docker compose exec reddarchiver-builder python reddarc.py /data/ruqqus/ \
  --guild technology \
  --comments-file /data/ruqqus/comments.fx.2021-10-30.txt.sort.2021-11-08.7z \
  --submissions-file /data/ruqqus/submissions.f1.2021-10-30.txt.sort.2021-11-10.7z \
  --platform ruqqus \
  --output /output/

# Full example with all flags
sudo docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst \
  --base-url https://your-domain.com \
  --site-name "Privacy Archive" \
  --site-description "Archived posts and comments from r/Privacy" \
  --project-url https://github.com/your-org/your-archive \
  --contact "admin@example.com" \
  --team-id "archive-team-1" \
  --donation-address "https://ko-fi.com/yourproject" \
  --favicon /data/favicon.ico \
  --og-image /data/og-image.png \
  --min-score 5 \
  --min-comments 2 \
  --hide-deleted-comments \
  --log-file /logs/archive.log \
  --log-level INFO

# View logs
sudo docker compose logs -f search-server

# Check service health
sudo docker compose ps
curl http://localhost/health      # nginx
curl http://localhost:5000/health # search-server
```

### Deployment Modes

```bash
# Development (HTTP only)
docker compose up -d

# Production (HTTPS with Let's Encrypt)
docker compose --profile production up -d

# Tor Hidden Service
docker compose --profile tor up -d

# Dual-mode (HTTPS + Tor)
docker compose --profile production --profile tor up -d
```

### Local Development (without Docker)

```bash
# Install dependencies
uv sync

# Set required environment variable
export DATABASE_URL="postgresql://user:pass@localhost:5432/reddarchiver"

# Run archive generator
uv run python reddarc.py /path/to/data --output archive/

# Run search server
uv run python search_server.py
```

### Testing

```bash
# Run all tests (requires PostgreSQL)
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_postgres_resume.py -v

# Run with coverage
uv run pytest tests/ --cov=. --cov-report=html
```

## CLI Reference

### Required Arguments

| Argument | Description |
|----------|-------------|
| `input_dir` | Directory containing .zst files |

### Processing Modes (mutually exclusive)

| Flag | Description |
|------|-------------|
| (default) | Combined import + export |
| `--import-only` | Stream .zst to PostgreSQL only (no HTML generation) |
| `--export-from-database` | Generate HTML from existing database only (no import) |

### Output Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--output/-o DIR` | `redd-archive-output` | Output directory for generated HTML |

### SEO & Instance Metadata

| Flag | Default | Description |
|------|---------|-------------|
| `--base-url URL` | None | Base URL for canonical links and sitemaps |
| `--site-name NAME` | `Redd Archive` | Site name for meta tags |
| `--site-description TEXT` | None | Site description for API and SEO |
| `--project-url URL` | GitHub repo | Project repository URL for footer links |
| `--contact METHOD` | None | Contact method (email, URL, Matrix, GitHub) shown in API |
| `--team-id ID` | None | Team identifier for registry leaderboard grouping |
| `--donation-address ADDR` | None | Donation method (URL, crypto, payment link) shown in API/footer |
| `--favicon PATH` | None | Path to favicon file (copied to output) |
| `--og-image PATH` | None | Path to Open Graph image (copied to output) |

### Content Filtering

| Flag | Default | Description |
|------|---------|-------------|
| `--min-score N` | `0` | Minimum post score threshold |
| `--min-comments N` | `0` | Minimum comment count threshold |
| `--hide-deleted-comments` | `false` | Hide deleted and removed comments in output |
| `--no-user-pages` | `false` | Skip user page generation (reduces memory) |

### Multi-Platform Community Modes

| Flag | Platform | Description |
|------|----------|-------------|
| `--subreddit/-s NAME` | Reddit | Process specific subreddit(s) (comma-separated) |
| `--subverse NAME` | Voat | Process specific subverse(s) (comma-separated) |
| `--guild NAME` | Ruqqus | Process specific guild(s) (comma-separated) |
| `--platform TYPE` | All | Force platform detection (auto\|reddit\|voat\|ruqqus) |
| `--comments-file PATH` | **All** | Path to comments file (.zst/.sql.gz/.7z) - **now works with all platforms** |
| `--submissions-file PATH` | **All** | Path to submissions file (.zst/.sql.gz/.7z) - **now works with all platforms** |

### Processing Control

| Flag | Description |
|------|-------------|
| `--dry-run` | Show discovered files without processing |
| `--resume` | Resume interrupted processing (auto-detected) |
| `--force-rebuild` | Force full rebuild, ignoring existing progress |
| `--force-parallel-users` | Force parallel user processing (override auto-detection) |

### Debug & Performance Tuning

| Flag | Default | Description |
|------|---------|-------------|
| `--debug-memory-limit GB` | auto-detect | Override memory limit |
| `--debug-max-connections N` | auto-detect | Override DB connection pool (1-20) |
| `--debug-max-workers N` | auto-detect | Override parallel workers (1-16) |

### Logging

| Flag | Default | Description |
|------|---------|-------------|
| `--log-file PATH` | `output_dir/.archive-error.log` | Path to log file |
| `--log-level LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL) |

### Version

| Flag | Description |
|------|-------------|
| `--version` | Show version string and exit |

## Architecture

### Directory Structure

```
redd-archiver/
├── reddarc.py                 # Main CLI entry point (2,355 lines)
├── search_server.py           # Flask search UI server (532 lines)
│
├── core/                      # Core processing modules
│   ├── postgres_database.py   # PostgreSQL backend (3,491 lines)
│   ├── postgres_search.py     # Full-text search (653 lines)
│   ├── write_html.py          # HTML generation coordinator (979 lines)
│   ├── watchful.py            # .zst streaming utilities (336 lines)
│   ├── incremental_processor.py # State/memory management (588 lines)
│   └── importers/             # Multi-platform importers
│       ├── base_importer.py       # Abstract base class
│       ├── reddit_importer.py     # .zst JSON Lines parser
│       ├── voat_importer.py       # SQL dump coordinator
│       ├── voat_sql_parser.py     # SQL INSERT parser
│       └── ruqqus_importer.py     # .7z JSON Lines parser
│
├── api/                       # REST API v1
│   ├── __init__.py            # Blueprint registration
│   └── routes.py              # API endpoints (4,372 lines)
│
├── mcp_server/                # MCP Server for AI integration
│   ├── server.py              # FastMCP server (29 tools)
│   ├── README.md              # MCP documentation
│   └── tests/                 # Test suite
│
├── html_modules/              # HTML generation (17 modules)
│   ├── html_pages_jinja.py    # Jinja2 page rendering (985 lines)
│   ├── html_seo.py            # SEO/sitemaps (1,353 lines)
│   ├── html_dashboard_jinja.py # Dashboard generation
│   ├── jinja_env.py           # Jinja2 environment setup
│   ├── jinja_filters.py       # Custom filters with LRU caching
│   └── css_minifier.py        # CSS optimization with rcssmin
│
├── processing/                # Parallel processing
│   ├── parallel_user_processing.py  # Multi-threaded user pages
│   ├── batch_processing_utils.py    # Auto-tuning batch engine
│   └── incremental_statistics.py    # Statistics caching
│
├── utils/                     # Shared utilities
│   ├── console_output.py      # Professional console formatting
│   ├── input_validation.py    # Input sanitization (612 lines)
│   ├── search_operators.py    # Google-style query parsing
│   └── error_handling.py      # Safe error responses
│
├── templates_jinja2/          # Jinja2 templates (16 files)
│   ├── base/base.html         # Master layout
│   ├── pages/                 # Page templates
│   ├── components/            # Reusable UI components
│   └── macros/                # Template macros
│
├── sql/                       # Database schema
│   ├── schema.sql             # PostgreSQL schema
│   └── indexes.sql            # Performance indexes
│
├── docker/                    # Deployment infrastructure
│   ├── nginx/                 # Reverse proxy configs
│   ├── tor/                   # Tor hidden service
│   ├── search-server/         # Search server Dockerfile
│   ├── leaderboard/           # Registry leaderboard
│   └── scripts/               # Setup scripts (certbot, etc.)
│
├── tests/                     # Test suite
│   ├── test_postgres_resume.py
│   ├── test_postgres_user_pages.py
│   └── test_streaming_user_pages.py
│
└── docs/                      # Documentation
    ├── API.md                 # REST API reference
    ├── TOR_DEPLOYMENT.md      # Tor setup guide
    ├── STATIC_DEPLOYMENT.md   # Static hosting guide
    └── REGISTRY_SETUP.md      # Registry configuration
```

### Data Flow

```
Import Phase:
.zst files → read_lines_zst() → JSON parsing → insert_posts_batch() → PostgreSQL
                                             → insert_comments_batch()
                                             → update_user_statistics()

Export Phase:
PostgreSQL → rebuild_threads_keyset() → Jinja2 templates → Static HTML files
          → stream_user_batches()    →                  → User pages
          → generate_chunked_sitemaps()                 → SEO files
```

### Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| postgres | 5432 | PostgreSQL database |
| reddarchiver-builder | - | Archive generator CLI |
| search-server | 5000 | Flask search API |
| nginx | 80/443 | Reverse proxy + static files |
| certbot | - | Let's Encrypt SSL (production profile) |
| tor | - | Hidden service (tor profile) |

## Key Patterns

### PostgreSQL-Only Backend
All database operations use `core/postgres_database.py`.
`DATABASE_URL` environment variable is **required**.

### Streaming Architecture
- `read_lines_zst()` - Line-by-line .zst decompression
- `rebuild_threads_keyset()` - O(1) keyset pagination (not OFFSET)
- `stream_user_batches()` - Server-side cursors for user pages
- `insert_posts_batch()` / `insert_comments_batch()` - COPY protocol (15K+ inserts/sec)

### Batch Loading (Critical for Performance)
```python
# BAD: N+1 queries
for user in users:
    activity = db.get_user_activity(user)  # 1 query per user

# GOOD: Batch loading (2,000x query reduction)
activities = db.get_user_activity_batch(usernames)  # 1 query total
```

### Index Management for Bulk Loading
```python
db.drop_indexes_for_bulk_load()    # 10-15x faster imports
# ... bulk insert ...
db.create_indexes_after_bulk_load() # Recreate indexes
db.analyze_tables(['posts', 'comments', 'users'])
```

### Resume/Checkpoint System
- Progress tracked in PostgreSQL `processing_metadata` table
- Auto-detected on restart via `detect_resume_state_and_files()`
- States: `start_fresh`, `resume_subreddits`, `resume_from_emergency`, `already_complete`

### Memory Management
```python
# Multi-tier memory monitoring in IncrementalProcessor
if memory_percent > 0.95:   # Emergency: save and exit
if memory_percent > 0.85:   # Critical: triple gc.collect()
if memory_percent > 0.70:   # Warning: gc.collect()
if memory_percent > 0.60:   # Info: log usage
```

## Environment Variables

### Required
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/reddarchiver
```

### Docker Configuration
```bash
POSTGRES_PASSWORD=CHANGE_THIS     # Database password
DATA_PATH=./data                  # Input .zst files
OUTPUT_PATH=./output              # Generated HTML
FLASK_SECRET_KEY=<generate>       # Required for production
```

### Instance Metadata (for /api/v1/stats)
```bash
REDDARCHIVER_SITE_NAME="My Archive"
REDDARCHIVER_BASE_URL="https://example.com"
REDDARCHIVER_CONTACT="admin@example.com"
REDDARCHIVER_TEAM_ID="team-id"
REDDARCHIVER_DONATION_ADDRESS="..."
```

### Performance Tuning
```bash
REDDARCHIVER_MAX_DB_CONNECTIONS=8
REDDARCHIVER_MAX_PARALLEL_WORKERS=4
REDDARCHIVER_USER_BATCH_SIZE=2000
REDDARCHIVER_MEMORY_LIMIT=15.0
```

## REST API Endpoints

Base URL: `/api/v1` - **30+ endpoints** with MCP/AI optimization

### System Endpoints (5)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with database status |
| `/stats` | GET | Archive statistics + instance metadata |
| `/schema` | GET | API capability discovery (MCP-optimized) |
| `/openapi.json` | GET | OpenAPI 3.0.3 specification |

### Posts Endpoints (13)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/posts` | GET | Paginated posts with filtering, sorting, field selection, truncation, export |
| `/posts/{id}` | GET | Single post with full details |
| `/posts/{id}/comments` | GET | Post comments (paginated) |
| `/posts/{id}/context` | GET | Post + top comments in one call (MCP-optimized) |
| `/posts/{id}/comments/tree` | GET | Hierarchical comment tree structure |
| `/posts/{id}/related` | GET | Similar posts via FTS similarity |
| `/posts/random` | GET | Random post sampling (with optional seed) |
| `/posts/aggregate` | GET | Aggregate by author/subreddit/time |
| `/posts/batch` | POST | Batch lookup by IDs |

### Comments Endpoints (7)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/comments` | GET | Paginated comments with filtering, truncation, export |
| `/comments/{id}` | GET | Single comment with full text |
| `/comments/random` | GET | Random comment sampling |
| `/comments/aggregate` | GET | Aggregate by author/subreddit/time |
| `/comments/batch` | POST | Batch lookup by IDs |

### Users Endpoints (8)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/users` | GET | Paginated users with sorting, field selection, export |
| `/users/{username}` | GET | User profile with activity breakdown |
| `/users/{username}/summary` | GET | Quick user overview (MCP-optimized) |
| `/users/{username}/posts` | GET | User's posts (paginated) |
| `/users/{username}/comments` | GET | User's comments (paginated) |
| `/users/aggregate` | GET | Aggregate user statistics |
| `/users/batch` | POST | Batch lookup by usernames |

### Subreddits Endpoints (4)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/subreddits` | GET | Subreddit list with statistics and export |
| `/subreddits/{name}` | GET | Subreddit detailed statistics |
| `/subreddits/{name}/summary` | GET | Quick subreddit overview (MCP-optimized) |

### Search Endpoints (3)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/search` | GET | Full-text search with Google-style operators |
| `/search/explain` | GET | Query parsing debugger |

**Common Parameters (most list endpoints)**:
- `?fields=id,title,score` - Select specific fields (token optimization)
- `?max_body_length=500` - Truncate long text
- `?include_body=false` - Exclude body fields
- `?format=csv|ndjson` - Export format (default: json)
- `?limit=25&page=1` - Pagination (10-100 per page)

Rate limit: 100 requests/minute per IP. CORS enabled for all origins.

## Search Operators

The search server supports Google-style operators:

```
"exact phrase"           # Phrase search
word1 OR word2           # Boolean OR
-excluded                # Exclude term
sub:subreddit            # Filter by subreddit
author:username          # Filter by author
score:100                # Minimum score
type:post | type:comment # Result type
sort:score | sort:date   # Sort order
```

## Key Files for Common Tasks

### Adding a new CLI flag
- `reddarc.py:562-645` - ArgumentParser setup

### Modifying database queries
- `core/postgres_database.py` - All database operations

### Adding a new API endpoint
- `api/routes.py` - REST API routes

### Modifying HTML output
- `html_modules/html_pages_jinja.py` - Page generation
- `templates_jinja2/pages/` - Jinja2 templates
- `templates_jinja2/macros/` - Reusable components

### Adding SEO features
- `html_modules/html_seo.py` - SEO generation (1,353 lines)

### Modifying search behavior
- `core/postgres_search.py` - PostgreSQL FTS queries
- `utils/search_operators.py` - Query parsing

## Performance Characteristics

| Operation | Performance |
|-----------|-------------|
| Post insertion | 15,000+ records/second (COPY protocol) |
| Keyset pagination | O(1) regardless of offset |
| User page generation | 2,000 users/batch with batch loading |
| Parallel subreddit pages | 86% improvement (3×5 worker pattern) |
| Jinja2 compilation | 10-100x faster with bytecode caching |

## Testing Approach

Tests require a running PostgreSQL instance:

```bash
# Set test database URL
export DATABASE_URL="postgresql://test:test@localhost:5432/reddarchiver_test"

# Run specific test categories
uv run pytest tests/test_postgres_resume.py -v      # Resume functionality
uv run pytest tests/test_streaming_user_pages.py -v # Streaming tests
```

## Documentation

- `QUICKSTART.md` - Step-by-step deployment guide (2-15 minutes)
- `ARCHITECTURE.md` - Detailed technical architecture
- `docs/API.md` - REST API reference (30+ endpoints)
- `mcp_server/README.md` - MCP Server setup and tool reference
- `docs/TOR_DEPLOYMENT.md` - Tor hidden service setup
- `docs/STATIC_DEPLOYMENT.md` - GitHub/Codeberg Pages deployment
- `docs/REGISTRY_SETUP.md` - Instance registry configuration

## MCP Server (AI Integration)

The MCP server provides 29 tools for AI assistants to query the archive:

```bash
# Start MCP server
cd mcp_server/
uv run python server.py --api-url http://localhost:5000
```

**Claude Desktop Configuration** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "reddarchiver": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp_server", "run", "python", "server.py"],
      "env": { "REDDARCHIVER_API_URL": "http://localhost:5000" }
    }
  }
}
```

See `mcp_server/README.md` for complete tool reference and setup guide.
