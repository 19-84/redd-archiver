# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Redd-Archiver is a PostgreSQL-backed archive generator that transforms compressed data dumps from multiple link aggregator platforms (**Reddit**, **Voat**, **Ruqqus**) into browsable static HTML websites with optional server-side full-text search and MCP/AI integration.

**Key Characteristics:**
- **Multi-Platform Support**: Reddit (.zst), Voat (SQL), Ruqqus (.7z)
- Streaming architecture with constant memory usage regardless of dataset size
- PostgreSQL-only backend (DATABASE_URL required)
- Hybrid output: Static HTML for offline browsing + optional Flask search server
- **REST API v1** with MCP/AI optimization (see `docs/API.md`)
- **MCP Server** for Claude Desktop/Claude Code integration (see `mcp_server/README.md`)
- Zero JavaScript design for maximum compatibility

## Deviations from Global Standards

This project intentionally deviates from the global `~/.claude/docs/` conventions in these areas. Do not "fix" these to match global standards without explicit permission.

| Area | Global Standard | This Project | Rationale |
|------|----------------|--------------|-----------|
| Line length | 88 | 120 | HTML string literals, SQL queries, and template paths cause excessive wrapping at 88 |
| Type checker | pyright (standard) | Not yet configured | Legacy codebase; planned addition (see `roadmap/08-pyright-type-checking.md`) |
| Logging | structlog | stdlib `logging` | Predates structlog adoption; migration low priority |
| Project layout | `src/` | Flat (packages at root) | Historical; changing breaks all Docker COPY paths and imports |
| Source control | jj preferred | git only | jj not configured for this repo |
| Pre-commit | Expected | Not yet activated | `pre-commit` in dev deps but no `.pre-commit-config.yaml`; CI gates enforce quality. Planned (see `roadmap/10-pre-commit-hooks.md`) |
| Ruff rules | includes SIM, RUF | Missing SIM, RUF | Being added incrementally (see `roadmap/09-ruff-sim-ruf-rules.md`) |

## Build & Run Commands

### Docker Development (Primary Method)

```bash
# Start all services (postgres, builder, search-server, nginx)
sudo docker compose up -d --build

# Run archive generator (Reddit)
sudo docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst

# Voat (pre-split files)
sudo docker compose exec reddarchiver-builder python reddarc.py /data/voat_split/submissions/ \
  --subverse privacy \
  --comments-file /data/voat_split/comments/privacy_comments.sql.gz \
  --submissions-file /data/voat_split/submissions/privacy_submissions.sql.gz \
  --platform voat \
  --output /output/

# Ruqqus (.7z files)
sudo docker compose exec reddarchiver-builder python reddarc.py /data/ruqqus/ \
  --guild technology \
  --comments-file /data/ruqqus/comments.fx.2021-10-30.txt.sort.2021-11-08.7z \
  --submissions-file /data/ruqqus/submissions.f1.2021-10-30.txt.sort.2021-11-10.7z \
  --platform ruqqus \
  --output /output/

# View logs / health
sudo docker compose logs -f search-server
curl http://localhost/health       # nginx
curl http://localhost:5000/health  # search-server
```

### Deployment Modes

```bash
docker compose up -d                                       # Development (HTTP)
docker compose --profile production up -d                  # HTTPS (Let's Encrypt)
docker compose --profile tor up -d                         # Tor Hidden Service
docker compose --profile production --profile tor up -d    # HTTPS + Tor
```

### Local Development

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/reddarchiver"
uv run python reddarc.py /path/to/data --output archive/
uv run python search_server.py
```

### Makefile Shortcuts

```bash
make setup          # uv sync + install pre-commit hooks
make test           # pytest
make test-cov       # pytest with coverage report
make lint           # ruff check
make format         # ruff format
make docker-up      # Start Docker services
make docker-logs    # Tail Docker logs
make clean          # Remove caches and temp files
```

## CLI Quick Reference

| Argument / Flag | Description |
|----------------|-------------|
| `input_dir` | (Required) Directory containing data files |
| `--output/-o DIR` | Output directory (default: `redd-archive-output`) |
| `--import-only` | Stream to PostgreSQL only (no HTML) |
| `--export-from-database` | Generate HTML from existing DB only (no import) |
| `--subreddit/-s NAME` | Reddit subreddit(s), comma-separated |
| `--subverse NAME` | Voat subverse(s), comma-separated |
| `--guild NAME` | Ruqqus guild(s), comma-separated |
| `--platform TYPE` | Force platform: `auto\|reddit\|voat\|ruqqus` |
| `--comments-file PATH` | Path to comments file (.zst/.sql.gz/.7z) |
| `--submissions-file PATH` | Path to submissions file (.zst/.sql.gz/.7z) |
| `--min-score N` | Minimum post score threshold |
| `--min-comments N` | Minimum comment count threshold |
| `--hide-deleted-comments` | Hide deleted/removed comments |
| `--resume` | Resume interrupted processing (auto-detected) |
| `--dry-run` | Show discovered files without processing |
| `--base-url URL` | Base URL for canonical links and sitemaps |

Run `reddarc --help` for the full flag reference including SEO metadata, debug tuning, and logging options.

## Architecture

### Directory Structure

```
redd-archiver/
├── reddarc.py                 # Main CLI entry point
├── search_server.py           # Flask search UI + API server
├── version.py                 # Version metadata
│
├── core/                      # Core processing (DB, search, streaming)
│   ├── postgres_database.py   # PostgreSQL backend (all DB operations)
│   ├── postgres_search.py     # Full-text search queries
│   ├── write_html.py          # HTML generation coordinator
│   ├── watchful.py            # .zst streaming utilities
│   ├── incremental_processor.py # State/memory management
│   └── importers/             # Multi-platform importers
│       ├── base_importer.py   # Abstract base class
│       ├── reddit_importer.py # .zst JSON Lines parser
│       ├── voat_importer.py   # SQL dump coordinator
│       ├── voat_sql_parser.py # SQL INSERT parser
│       └── ruqqus_importer.py # .7z JSON Lines parser
│
├── api/                       # REST API v1 (Flask blueprint)
│   └── routes.py              # All API endpoints
│
├── html_modules/              # HTML generation (Jinja2, SEO, CSS, dashboards)
├── processing/                # Parallel processing, batch engine, statistics
├── monitoring/                # Performance monitoring, auto-tuning, system optimization
├── utils/                     # Validation, regex, search operators, error handling, console output
│
├── mcp_server/                # MCP Server (separate uv project with own pyproject.toml/uv.lock)
├── templates_jinja2/          # Jinja2 templates (base, pages, components, macros)
├── static/                    # CSS, fonts, favicons, webmanifest
├── sql/                       # Database schema, indexes, migrations
│
├── tools/                     # Scanner scripts + data catalogs (see tools/README.md)
├── roadmap/                   # v2 feature specifications (see roadmap/README.md)
├── tests/                     # Test suite (conftest.py + ~22 test files)
├── docs/                      # Documentation (13 guides)
├── docker/                    # Deployment (nginx, tor, search-server, scripts)
│
├── Dockerfile                 # Builder image (Python 3.12-alpine)
├── docker-compose.yml         # Service orchestration
├── pyproject.toml             # Project config (deps, ruff, pytest, coverage)
├── Makefile                   # Dev command shortcuts
└── requirements.txt           # Used by Dockerfiles
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

### Per-File Ruff Ignores (Technical Debt)

`pyproject.toml` contains extensive per-file-ignores for ~30 files, suppressing ruff violations that predate the linting setup. When modifying these files:
- Do NOT add new ignores without understanding why existing ones are needed
- Do NOT remove ignores without verifying the underlying code is fixed
- New code in these files should still follow ruff rules

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

## CI/CD

Four GitHub Actions workflows in `.github/workflows/`:

| Workflow | File | Triggers | What it does |
|----------|------|----------|-------------|
| Lint | `lint.yml` | push, PR | `ruff check` + `ruff format --check` |
| Tests | `test.yml` | push, PR | pytest with postgres:18-alpine service, `--cov-fail-under=25` |
| Docker | `docker.yml` | push, PR | Builds all 4 images (builder, search-server, nginx, mcp-server), runs compose integration test |
| Security | `security.yml` | push, PR, weekly | CodeQL analysis + Trivy filesystem scan |
| Mirror | `mirror.yml` | push (main), manual | Push branches + tags to Forgejo and GitLab |

Dependabot is configured for pip dependency updates.

## REST API

Base URL: `/api/v1`. Rate limit: 100 req/min per IP. CORS enabled.

| Category | Endpoints | Highlights |
|----------|-----------|------------|
| System | 4 | health, stats, schema discovery, OpenAPI spec |
| Posts | 9 | CRUD, context (MCP-optimized), comment tree, related, random, aggregate, batch |
| Comments | 5 | CRUD, random, aggregate, batch |
| Users | 7 | profile, summary (MCP-optimized), posts, comments, aggregate, batch |
| Subreddits | 3 | list with stats, detail, summary (MCP-optimized) |
| Search | 2 | full-text search with operators, query explainer |

**Common parameters**: `?fields=` (field selection), `?max_body_length=` (truncation), `?include_body=false`, `?format=csv|ndjson`, `?limit=&page=` (pagination, 10-100 per page)

Full endpoint reference: `docs/API.md`

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
- `reddarc.py` - ArgumentParser setup (search for `add_argument`)

### Modifying database queries
- `core/postgres_database.py` - All database operations

### Adding a new API endpoint
- `api/routes.py` - REST API routes

### Modifying HTML output
- `html_modules/html_pages_jinja.py` - Page generation
- `templates_jinja2/pages/` - Jinja2 templates
- `templates_jinja2/macros/` - Reusable components

### Adding SEO features
- `html_modules/html_seo.py` - SEO/sitemap generation

### Modifying search behavior
- `core/postgres_search.py` - PostgreSQL FTS queries
- `utils/search_operators.py` - Query parsing

### Adding a new platform importer
- `core/importers/base_importer.py` - Abstract base class to implement
- `core/importers/` - Existing implementations as reference

### Performance monitoring
- `monitoring/` - Auto-tuning, performance phases, timing, system optimization

### Scanner tools and data catalogs
- `tools/README.md` - Complete tool documentation
- `tools/` - Platform scanners, data catalogs, Voat utilities

## Performance Characteristics

| Operation | Performance |
|-----------|-------------|
| Post insertion | 15,000+ records/second (COPY protocol) |
| Keyset pagination | O(1) regardless of offset |
| User page generation | 2,000 users/batch with batch loading |
| Parallel subreddit pages | 86% improvement (3x5 worker pattern) |
| Jinja2 compilation | 10-100x faster with bytecode caching |

## Testing

Tests require a running PostgreSQL instance. CI uses `postgres:18-alpine`.

```bash
DATABASE_URL="postgresql://reddarchiver:test_password@localhost:5432/reddarchiver"
```

Coverage threshold: **25%** (enforced in CI via `--cov-fail-under=25`).

The `mcp_server/` has its own test suite under `mcp_server/tests/`.

## Documentation

### Getting Started
- `QUICKSTART.md` - Step-by-step deployment guide
- `docs/INSTALLATION.md` - Detailed installation
- `docs/FAQ.md` - Frequently asked questions
- `docs/TROUBLESHOOTING.md` - Common issues

### Architecture & Design
- `ARCHITECTURE.md` - Technical architecture
- `roadmap/README.md` - v2 feature roadmap

### Features
- `docs/API.md` - REST API reference
- `docs/SEARCH.md` - Search documentation
- `docs/DATA_CATALOG.md` - Data catalog guide
- `docs/SCANNER_TOOLS.md` - Scanner tool reference
- `mcp_server/README.md` - MCP Server setup and tools

### Operations
- `docs/PERFORMANCE.md` - Performance tuning
- `docs/SCALING.md` - Scaling guide
- `docs/STATIC_DEPLOYMENT.md` - GitHub/Codeberg Pages deployment
- `docs/TOR_DEPLOYMENT.md` - Tor hidden service setup
- `docs/DEPLOYMENT_TESTING.md` - Testing deployments
- `docs/REGISTRY_SETUP.md` - Instance registry configuration

## MCP Server (AI Integration)

The MCP server is a **separate uv project** under `mcp_server/` with its own `pyproject.toml` and `uv.lock`.

```bash
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
