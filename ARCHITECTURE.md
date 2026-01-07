# Redd-Archiver Architecture

This document describes the technical architecture of Redd-Archiver v1.0.0, a PostgreSQL-backed archive generator that transforms compressed data dumps into browsable HTML archives with optional server-side search.

## Table of Contents

- [System Overview](#system-overview)
- [Hybrid Architecture](#hybrid-architecture)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Module Organization](#module-organization)
- [Performance Architecture](#performance-architecture)
- [Database Schema](#database-schema)
- [Deployment Architecture](#deployment-architecture)
- [Design Patterns](#design-patterns)

## System Overview

Redd-Archiver follows a **streaming architecture** with PostgreSQL as the central data store. The system processes compressed .zst files, stores data in PostgreSQL with full-text indexing, and generates static HTML output.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│  .zst Files │────▶│  Streaming   │────▶│ PostgreSQL  │────▶│  HTML    │
│   (Input)   │     │  Processor   │     │  Database   │     │ Output   │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────┘
                           │                     │
                           │                     │
                           ▼                     ▼
                    ┌──────────────┐     ┌─────────────┐
                    │   Memory     │     │  PostgreSQL │
                    │  Monitoring  │     │     FTS     │
                    └──────────────┘     └─────────────┘
```

### Key Architectural Principles

1. **Streaming Processing**: Constant memory usage regardless of dataset size
2. **Database-Centric**: PostgreSQL handles aggregations, search, and state management
3. **Modular Design**: 18 specialized modules for maintainability
4. **Resume Capability**: Database-backed progress tracking enables graceful recovery
5. **Separation of Concerns**: Import/export workflow separation for large-scale operations

## Hybrid Architecture

Redd-Archiver uses a **hybrid architecture** that separates static HTML generation from dynamic search functionality:

### Static Components (Offline Browsing)

**What's Generated**:
- Complete HTML pages for posts, comments, subreddits, and user profiles
- Sorted index pages (by score, comments, date)
- Pagination (`index.html`, `index-2.html`, `index-3.html`, etc.)
- All CSS, themes, and static assets
- Full comment threading and navigation

**How it Works**:
- PostgreSQL database queries generate complete HTML files using Jinja2 templates
- Files are written to disk as self-contained static HTML
- No JavaScript required for core browsing functionality
- Pure CSS for themes, navigation, and interactivity

**Browsing Features**:
- Open HTML files directly in any browser (no server needed)
- Navigate via sorted index pages (score, comments, date)
- Pagination for large subreddits
- Full comment threads with collapsible UI
- Theme switching via CSS

**Limitations**:
- No search functionality (use sorted indexes instead)
- Cannot dynamically filter or query content

### Dynamic Components (Server Deployment)

**What Requires Server**:
- Full-text search functionality (PostgreSQL FTS)
- Search API endpoint (`/search`)
- Real-time query processing

**Architecture**:
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│  nginx (80)  │────▶│   Flask     │
│   (User)    │◀────│   Reverse    │◀────│   Search    │
└─────────────┘     │   Proxy      │     │  Server (5000) │
                    └──────────────┘     └─────────────┘
                           │                     │
                           │                     ▼
                           │              ┌─────────────┐
                           ▼              │ PostgreSQL  │
                    ┌──────────────┐     │  FTS Engine │
                    │Static HTML   │     └─────────────┘
                    │   Files      │
                    └──────────────┘
```

**Search Server Components**:
- `search_server.py` (Flask API server)
- PostgreSQL FTS with GIN indexes
- Query parsing with Google-style operators
- Result highlighting with `ts_headline()`
- Rate limiting and security features

**Deployment Options**:
1. **Offline Browsing**: No server, sorted indexes only
2. **Static Hosting** (GitHub Pages): No server, browse-only
3. **Docker Local**: Full stack on localhost (search enabled)
4. **Docker + Tor**: .onion hidden service (search enabled)
5. **Docker + HTTPS**: Production public deployment (search enabled)

**Why This Design?**

The hybrid architecture provides flexibility:
- **Researchers**: Can browse archives offline on USB drives
- **Small Archives**: Can use free static hosting (GitHub Pages)
- **Large Archives**: Can deploy with Docker for full search capabilities
- **Privacy-Focused**: Can share via Tor without port forwarding

This architecture emerged from intentional constraints:
- **Server-side search** optimized for low-latency networks including Tor
- **Static HTML** enables offline browsing and distribution
- **Zero JavaScript** ensures compatibility with Tor Browser "Safest" mode
- **PostgreSQL FTS** provides indexed search with constant memory usage

## Core Components

### Project Structure

Redd-Archiver uses a functional organization with specialized directories:

```
redd-archiver/
├── reddarc.py              # Main CLI entry point (2,355 lines)
├── search_server.py        # Flask search API server (532 lines)
├── version.py              # Version metadata
│
├── core/                   # Core processing & database
│   ├── postgres_database.py    (3,491 lines)
│   ├── postgres_search.py      (653 lines)
│   ├── write_html.py           (979 lines)
│   ├── watchful.py             (336 lines)
│   ├── incremental_processor.py (588 lines)
│   └── importers/              # Multi-platform importers
│       ├── __init__.py             (Platform registry)
│       ├── base_importer.py        (Abstract base class)
│       ├── reddit_importer.py      (.zst JSON Lines, 248 lines)
│       ├── voat_importer.py        (SQL dump coordinator, 560 lines)
│       ├── voat_sql_parser.py      (SQL INSERT statement parser)
│       └── ruqqus_importer.py      (.7z JSON Lines, 348 lines)
│
├── api/                    # REST API v1 (30+ endpoints)
│   ├── __init__.py             (Blueprint registration)
│   └── routes.py               (4,372 lines)
│
├── mcp_server/             # MCP Server for AI integration
│   ├── server.py               (FastMCP server, 29 tools)
│   ├── README.md               (MCP documentation)
│   └── tests/                  (Test suite)
│
├── utils/                  # Utility functions
│   ├── console_output.py
│   ├── error_handling.py
│   ├── input_validation.py
│   ├── regex_utils.py
│   ├── search_operators.py
│   └── simple_json_utils.py
│
├── processing/             # Data processing modules
│   ├── parallel_user_processing.py
│   ├── batch_processing_utils.py
│   └── incremental_statistics.py (796 lines)
│
├── monitoring/             # Performance & monitoring
│   ├── performance_monitor.py
│   ├── performance_phases.py
│   ├── performance_timing.py
│   ├── auto_tuning_validator.py
│   ├── streaming_config.py (181 lines)
│   └── system_optimizer.py
│
├── html_modules/           # HTML generation (18 modules)
├── templates_jinja2/       # Jinja2 templates (15 files)
├── sql/                    # Database schema & migrations
├── docker/                 # Docker deployment files
├── tests/                  # Test suite
└── static/                 # Static assets (CSS, JS, fonts)
```

### Entry Point: reddarc.py (2,202 lines)
**Location**: Root
**Purpose**: Main orchestrator and CLI interface

**Responsibilities**:
- Command-line argument parsing
- Workflow coordination (discovery → import → export)
- Progress tracking and resume logic
- Error handling and user feedback
- Environment configuration and validation

**Key Functions**:
- `main()`: Entry point with CLI argument processing
- `process_archive()`: Main workflow orchestrator
- `discover_zst_files()`: Auto-discovery of input files
- `import_data()`: Stream .zst → PostgreSQL
- `export_html()`: Generate HTML from database

### Database Layer: core/postgres_database.py (3,301 lines)
**Location**: core/
**Purpose**: PostgreSQL backend abstraction

**Responsibilities**:
- Database connection management (psycopg3 connection pooling)
- CRUD operations for posts, comments, users
- Full-text search with PostgreSQL FTS
- Statistics aggregation and caching
- Schema management and migrations
- Streaming data access with server-side cursors

**Key Classes/Functions**:
- `PostgresDatabase`: Main database interface
- `get_connection_pool()`: Connection pool management
- `insert_post_batch()`: Batch insertion with conflict handling
- `rebuild_threads_keyset()`: Keyset pagination for comment threading
- `stream_user_batches()`: Streaming user data access
- `search_content()`: Full-text search implementation

**Performance Patterns**:
- Connection pooling (8-16 connections typical)
- Batch operations (1000-5000 records/batch)
- Keyset pagination for O(1) queries
- Server-side cursors for streaming
- Prepared statements for query optimization

### HTML Generation: core/write_html.py (1,024 lines)
**Location**: core/
**Purpose**: HTML generation coordinator

**Responsibilities**:
- Coordinate page generation across modules
- Manage Jinja2 template rendering
- Handle static asset copying
- Generate SEO assets (sitemaps, robots.txt)
- Progress reporting for HTML generation

**Key Functions**:
- `generate_archive_html()`: Main generation orchestrator
- `generate_subreddit_pages()`: Subreddit listing pages
- `generate_post_pages()`: Individual post pages with comments
- `generate_user_pages()`: User profile pages (streaming)
- `generate_seo_assets()`: SEO meta files

### Streaming Utilities: core/watchful.py (336 lines)
**Location**: core/
**Purpose**: .zst file streaming and decompression

**Responsibilities**:
- Memory-efficient .zst decompression
- JSON parsing from compressed streams
- Line-by-line processing with minimal memory
- Error handling for malformed data

**Key Functions**:
- `stream_zst_file()`: Generator for streaming decompression
- `parse_json_line()`: Safe JSON parsing with error handling

### Search Server: search_server.py (442 lines)
**Location**: Root
**Purpose**: Flask-based web API for PostgreSQL FTS

**Responsibilities**:
- RESTful search API endpoints
- Rate limiting and CSRF protection
- Real-time PostgreSQL FTS queries
- Result highlighting with `ts_headline()`
- Health checks and monitoring

**Endpoints**:
- `GET /health`: Health check
- `GET /search`: Full-text search with filters
- `GET /suggestions`: Search suggestions (future)

### Configuration: monitoring/streaming_config.py (181 lines)
**Location**: monitoring/
**Purpose**: Auto-detecting system configuration

**Responsibilities**:
- CPU core detection and worker calculation
- Memory analysis and batch size tuning
- Connection pool sizing
- Environment variable parsing

**Auto-Detection Logic**:
- Workers: `min(cpu_cores, max(2, cpu_cores - 1))`
- Connections: `min(16, workers * 2)`
- Batch size: Based on available memory

## Multi-Platform Importer Architecture

Redd-Archiver supports multiple link aggregator platforms through a pluggable importer system:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Platform Detection                           │
│           (File extension → Platform → Importer class)              │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Reddit Importer │    │  Voat Importer  │    │ Ruqqus Importer │
│    (.zst files)  │    │  (SQL dumps)    │    │  (.7z files)    │
│                  │    │                 │    │                 │
│ • JSON Lines     │    │ • Regex parser  │    │ • 7z subprocess │
│ • zstandard lib  │    │ • State machine │    │ • JSON Lines    │
│ • Line-by-line   │    │ • INSERT parser │    │ • Line-by-line  │
└────────┬─────────┘    └────────┬────────┘    └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Base Importer                                │
│                    (Abstract streaming interface)                    │
│                                                                      │
│  • stream_posts() → Generator[dict]                                  │
│  • stream_comments() → Generator[dict]                               │
│  • normalize_post(raw) → dict (platform-specific → unified schema)   │
│  • normalize_comment(raw) → dict                                     │
│  • get_platform_prefix() → str ('r', 'v', 'g')                      │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       PostgreSQL Database                            │
│           (Unified schema with platform column)                      │
│                                                                      │
│  posts:    id (platform-prefixed), subreddit, platform, ...         │
│  comments: id (platform-prefixed), post_id, platform, ...           │
└─────────────────────────────────────────────────────────────────────┘
```

### Platform Importers

| Importer | Format | Method | Performance |
|----------|--------|--------|-------------|
| **RedditImporter** | .zst JSON Lines | `zstandard` streaming decompression | ~15,000 records/sec |
| **VoatImporter** | SQL dumps | Regex state machine parsing INSERT statements | ~9,000 records/sec |
| **RuqqusImporter** | .7z JSON Lines | `7z` subprocess with streaming stdout | ~3,000 records/sec |

### Platform Detection Flow

```python
# Automatic platform detection from file extension
def detect_platform(filepath: str) -> str:
    if filepath.endswith('.zst'):
        return 'reddit'
    elif filepath.endswith('.sql') or filepath.endswith('.sql.gz'):
        return 'voat'
    elif filepath.endswith('.7z'):
        return 'ruqqus'
    raise ValueError(f"Unknown format: {filepath}")

# CLI flags override auto-detection
# --platform auto|reddit|voat|ruqqus
# --subreddit (Reddit), --subverse (Voat), --guild (Ruqqus)
```

### Unified Schema

All platforms are normalized to a common schema with platform-prefixed IDs:

```sql
-- Posts table with platform column
CREATE TABLE posts (
    id TEXT PRIMARY KEY,          -- 'reddit_abc123', 'voat_12345', 'ruqqus_xyz'
    platform TEXT NOT NULL,       -- 'reddit', 'voat', 'ruqqus'
    subreddit TEXT NOT NULL,      -- Community name (subreddit/subverse/guild)
    ...
);

-- Platform-aware indexes
CREATE INDEX idx_posts_platform ON posts(platform);
CREATE INDEX idx_posts_subreddit_platform ON posts(subreddit, platform);
```

## Data Flow

### Import Workflow (Multi-Platform → PostgreSQL)

```
1. Discovery Phase
   ├─ Scan directory for data files (.zst, .sql, .7z)
   ├─ Detect platform from file extensions
   ├─ Match submissions and comments files
   └─ Select appropriate importer class

2. Streaming Import
   ├─ Platform-specific decompression/parsing
   │   ├─ Reddit: zstandard decompression
   │   ├─ Voat: SQL regex parsing
   │   └─ Ruqqus: 7z subprocess streaming
   ├─ Normalize to unified schema
   ├─ Add platform prefix to IDs
   ├─ Batch records (1000-5000/batch)
   ├─ Insert to PostgreSQL (COPY protocol)
   └─ Update progress metadata

3. Post-Processing
   ├─ Build comment threads (keyset pagination)
   ├─ Calculate statistics (SQL aggregations)
   ├─ Create search indexes (GIN indexes)
   └─ Mark import complete
```

### Export Workflow (PostgreSQL → HTML)

```
1. Data Extraction
   ├─ Query posts with filters (score, date, etc.)
   ├─ Stream users in batches (2000/batch)
   ├─ Load statistics from database
   └─ Batch load relationships (posts → comments)

2. HTML Generation
   ├─ Render subreddit pages (Jinja2)
   ├─ Render post pages with comments
   ├─ Render user pages (streaming batches)
   ├─ Generate dashboard with statistics
   └─ Copy static assets (CSS, JS, fonts)

3. SEO Generation
   ├─ Generate XML sitemaps
   ├─ Generate robots.txt
   ├─ Create meta tags and Open Graph data
   └─ Generate favicon and og-images
```

### Search Workflow (PostgreSQL FTS)

```
1. Query Processing
   ├─ Parse search query
   ├─ Build PostgreSQL tsquery
   ├─ Apply filters (subreddit, author, date)
   └─ Execute FTS query with GIN index

2. Result Processing
   ├─ Rank results with ts_rank()
   ├─ Generate excerpts with ts_headline()
   ├─ Apply pagination (LIMIT/OFFSET)
   └─ Return JSON response

3. Client Display
   ├─ Receive JSON results
   ├─ Render search results page
   └─ Highlight matching terms
```

### REST API Workflow (30+ Endpoints)

The REST API provides programmatic access to all archive data with MCP/AI optimization:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│  Flask API   │────▶│ PostgreSQL  │
│  (HTTP/MCP) │◀────│  Routes      │◀────│   Database  │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Field Filter │
                    │  Truncation  │
                    │   Export     │
                    └──────────────┘
```

**Request Pipeline**:
```
1. Rate Limiting
   ├─ Check IP-based rate limit (100 req/min)
   └─ Return 429 if exceeded

2. Input Validation
   ├─ SQL injection prevention (regex whitelists)
   ├─ XSS prevention (escaped output)
   ├─ Parameter bounds checking
   └─ Return 400 on validation failure

3. Database Query
   ├─ Get connection from pool (4-6 connections)
   ├─ Execute parameterized query
   ├─ Handle query timeout (30s for aggregations)
   └─ Return 500 on database error

4. Field Selection (if ?fields= specified)
   ├─ Validate against resource whitelist
   ├─ Filter response to requested fields
   └─ Return 400 on invalid fields

5. Body Truncation (if ?max_body_length= or ?include_body=false)
   ├─ Truncate text fields to specified length
   ├─ Add metadata: body_truncated, body_full_length
   └─ Exclude body if include_body=false

6. Format Conversion
   ├─ JSON: Standard paginated response
   ├─ CSV: Flatten nested data with dot notation
   └─ NDJSON: One JSON object per line

7. Response Headers
   ├─ CORS: Access-Control-Allow-Origin: *
   ├─ Content-Type: application/json | text/csv | application/x-ndjson
   ├─ Content-Disposition: attachment (CSV/NDJSON)
   └─ Security headers (CSP, X-Frame-Options, etc.)
```

**Optimization Patterns**:
- **Field Selection**: Whitelist validation reduces payload size for MCP token optimization
- **Batch Loading**: Single query for N resources (eliminates N+1 query problems)
- **Query Timeouts**: 30-second limit protects against expensive aggregations
- **Connection Pooling**: Auto-scaled 4-6 connections for API workload
- **Recursive CTEs**: Efficient hierarchical queries for comment trees
- **Export Formats**: CSV/NDJSON streaming for data analysis workflows

### MCP Server Architecture (AI Integration)

The MCP (Model Context Protocol) server provides AI assistants with full archive access:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Claude Desktop │     │                  │     │                 │
│  Claude Code    │────▶│   MCP Server     │────▶│  REST API v1    │
│  Other AI       │     │   (FastMCP)      │     │  (30+ endpoints) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │  29 MCP Tools    │
                        │  5 MCP Resources │
                        │  2 MCP Prompts   │
                        └──────────────────┘
```

**MCP Server Components** (`mcp_server/`):
- **FastMCP Integration**: Auto-generates tools from OpenAPI specification
- **29 Tools**: Posts, comments, users, search, aggregation, batch operations
- **5 Resources**: Quick access to stats, subreddits, top posts, recent posts, search help
- **2 Prompts**: LLM guidance for token management

**Token Overflow Prevention**:
```
┌─────────────────────────────────────────────────────────────────────┐
│                    Three-Layer Guidance System                       │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 1: Tool Descriptions                                          │
│   • Embedded warnings (⚠️ 🔴 ✅ emojis)                              │
│   • Safe parameter recommendations                                   │
│   • Response size estimates                                         │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 2: Parameter Guidance                                         │
│   • limit: 10-25 (not 50-100)                                       │
│   • max_body_length: 200 (truncate long text)                       │
│   • fields: "id,title,score" (select specific fields)               │
├─────────────────────────────────────────────────────────────────────┤
│ Layer 3: Response Validation                                        │
│   • Truncation metadata (body_truncated, body_full_length)          │
│   • Response size limits (50KB default)                             │
│   • Pagination information                                          │
└─────────────────────────────────────────────────────────────────────┘
```

**Claude Desktop Configuration**:
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

See [MCP Server Documentation](mcp_server/README.md) for complete setup and tool reference.

## Module Organization

### html_modules/ (18 Specialized Modules)

#### High-Level Modules
- **html_seo.py** (1,336 lines): SEO, meta tags, XML sitemaps, robots.txt
- **html_pages_jinja.py** (978 lines): Jinja2-based page generation
- **html_statistics.py** (830 lines): Analytics and metrics aggregation
- **dashboard_helpers.py** (535 lines): Dashboard utility functions
- **html_field_generation.py** (489 lines): Dynamic field generation

#### Rendering & Templating
- **jinja_filters.py** (365 lines): Custom Jinja2 filters (11 filters)
- **html_pages.py** (366 lines): Core page generation logic
- **html_comments.py** (305 lines): Comment threading system
- **jinja_env.py** (208 lines): Jinja2 environment configuration
- **html_dashboard_jinja.py** (165 lines): Jinja2 dashboard rendering

#### Utilities
- **html_utils.py** (175 lines): File operations, asset management
- **css_minifier.py** (154 lines): CSS minification
- **html_scoring.py** (113 lines): Dynamic score badges
- **html_templates.py** (100 lines): Template loading and management
- **html_url.py** (65 lines): URL processing, domain extraction
- **html_dashboard.py** (53 lines): Dashboard generation coordinator
- **html_constants.py** (43 lines): Configuration constants
- **__init__.py** (227 lines): Public API exports

### templates_jinja2/ (15 Templates)

**Template Hierarchy**:
```
base/
└── base.html (master template, inherited by all pages)

components/
├── dashboard_card.html (statistics cards)
├── footer.html (site footer)
├── global_summary.html (global statistics)
├── navigation.html (site navigation)
├── post_card.html (post display)
├── user_comment.html (user comment display)
└── user_post.html (user post display)

macros/
├── comment_macros.html (comment rendering macros)
└── reddit_macros.html (Reddit-specific macros)

pages/
├── global_search.html (search results page)
├── index.html (dashboard homepage)
├── link.html (individual post page)
├── subreddit.html (subreddit listing)
└── user.html (user profile page)
```

**Template Inheritance**:
- All pages extend `base/base.html`
- Components are included via `{% include %}`
- Macros imported via `{% from ... import %}`
- Blocks: `title`, `meta`, `content`, `scripts`

### sql/ (Schema & Migrations)

**Files**:
- `schema.sql`: Table definitions (posts, comments, users, processing_metadata)
- `indexes.sql`: Performance indexes (GIN for FTS, B-tree for queries)
- `fix_statistics.sql`: Statistics maintenance queries
- `migrations/003_add_total_activity_column.sql`: Schema migration example

## Performance Architecture

### Streaming Processing

**Problem**: In-memory processing fails with large datasets (>10GB)

**Solution**: Stream data in batches with constant memory usage

**Implementation**:
```python
# Server-side cursor with keyset pagination
def stream_user_batches(batch_size=2000):
    last_id = 0
    while True:
        users = db.query(
            "SELECT * FROM users WHERE id > %s ORDER BY id LIMIT %s",
            (last_id, batch_size)
        )
        if not users:
            break
        yield users
        last_id = users[-1]['id']
```

**Benefits**:
- O(1) memory usage regardless of dataset size
- O(1) query time with keyset pagination (indexed)
- Graceful resume on interruption

### Connection Pooling

**Configuration**:
- Pool size: 8-16 connections (auto-detected)
- Max overflow: 4 additional connections
- Timeout: 30 seconds
- Recycle: 3600 seconds (1 hour)

**Usage Patterns**:
- Long-lived connections for streaming operations
- Short-lived connections for batch inserts
- Separate read/write connection pools (future optimization)

### Batch Loading

**Problem**: N+1 query problem in user page generation

**Solution**: Batch load all related data upfront

**Example**:
```python
# Bad: N+1 queries (1 per user)
for user in users:
    posts = db.get_user_posts(user.id)  # 1 query each

# Good: 2 queries total
user_ids = [u.id for u in users]
all_posts = db.get_posts_by_users(user_ids)  # 1 batch query
posts_by_user = group_by(all_posts, 'author')
```

**Benefits**:
- Query reduction: 1,000,000+ → 3 queries per batch
- Database time: Variable → 60-140s per 2K batch
- Scalable architecture for millions of users

### Keyset Pagination

**Problem**: `OFFSET N` queries become O(n) as N increases

**Solution**: Keyset pagination using indexed columns

**Comparison**:
```sql
-- Slow: O(n) - must scan N rows
SELECT * FROM comments ORDER BY id LIMIT 1000 OFFSET 1000000;

-- Fast: O(1) - indexed lookup
SELECT * FROM comments WHERE id > 1000000 ORDER BY id LIMIT 1000;
```

**Performance**:
- Traditional pagination: 28-52 hours (40M comments)
- Keyset pagination: 30-60 minutes (40M comments)
- Benefit: Dramatically improved query performance

## Database Schema

### Core Tables

#### posts
**Purpose**: Submission posts

**Columns**:
- `id` (TEXT PRIMARY KEY): Post ID
- `subreddit` (TEXT): Subreddit name
- `author` (TEXT): Author username
- `title` (TEXT): Post title
- `selftext` (TEXT): Post body text
- `score` (INTEGER): Post score
- `num_comments` (INTEGER): Comment count
- `created_utc` (INTEGER): Unix timestamp
- `url` (TEXT): External URL (if link post)
- `json_data` (JSONB): Full post data
- `search_vector` (TSVECTOR): Full-text search index

**Indexes**:
- `idx_posts_subreddit_created`: B-tree on (subreddit, created_utc DESC)
- `idx_posts_author_created`: B-tree on (author, created_utc DESC)
- `idx_posts_search`: GIN on search_vector
- `idx_posts_score`: B-tree on score DESC
- `idx_posts_json_gin`: GIN on json_data (for JSONB queries)

#### comments
**Purpose**: Comment replies

**Columns**:
- `id` (TEXT PRIMARY KEY): Comment ID
- `post_id` (TEXT): Parent post ID
- `parent_id` (TEXT): Parent comment ID (NULL for top-level)
- `subreddit` (TEXT): Subreddit name
- `author` (TEXT): Author username
- `body` (TEXT): Comment text
- `score` (INTEGER): Comment score
- `created_utc` (INTEGER): Unix timestamp
- `json_data` (JSONB): Full comment data
- `search_vector` (TSVECTOR): Full-text search index
- `link_title` (TEXT): Parent post title (denormalized for performance)

**Indexes**:
- `idx_comments_post_id_created`: B-tree on (post_id, created_utc, id)
- `idx_comments_author_created`: B-tree on (author, created_utc DESC)
- `idx_comments_parent_id`: B-tree on parent_id
- `idx_comments_search`: GIN on search_vector

#### users
**Purpose**: User profile data

**Columns**:
- `id` (SERIAL PRIMARY KEY): Auto-increment ID
- `username` (TEXT UNIQUE): Username
- `total_posts` (INTEGER): Post count
- `total_comments` (INTEGER): Comment count
- `total_score` (INTEGER): Combined score
- `total_activity` (INTEGER): posts + comments
- `first_seen` (INTEGER): Earliest timestamp
- `last_seen` (INTEGER): Latest timestamp

**Indexes**:
- `idx_users_username`: UNIQUE on username
- `idx_users_activity`: B-tree on total_activity DESC
- `idx_users_id`: B-tree on id (for keyset pagination)

#### processing_metadata
**Purpose**: Progress tracking and resume capability

**Columns**:
- `key` (TEXT PRIMARY KEY): Metadata key
- `value` (TEXT): Metadata value
- `updated_at` (TIMESTAMP): Last update time

**Keys**:
- `import_status`: 'completed', 'in_progress', 'failed'
- `export_status`: 'completed', 'in_progress', 'failed'
- `last_processed_user_id`: Resume checkpoint for user pages
- `statistics_cache`: JSON-encoded statistics

### Full-Text Search (FTS)

**Configuration**:
- PostgreSQL `tsvector` columns for posts and comments
- GIN indexes for fast full-text lookups
- English text search configuration
- Weighted ranking: title > body

**Update Triggers**:
```sql
CREATE TRIGGER posts_search_update
BEFORE INSERT OR UPDATE ON posts
FOR EACH ROW EXECUTE FUNCTION
tsvector_update_trigger(search_vector, 'pg_catalog.english', title, selftext);
```

**Search Query Example**:
```sql
SELECT
    id, title,
    ts_rank(search_vector, query) AS rank,
    ts_headline('english', selftext, query) AS excerpt
FROM posts, to_tsquery('english', 'machine & learning') query
WHERE search_vector @@ query
ORDER BY rank DESC
LIMIT 50;
```

## Deployment Architecture

### Single Instance Architecture

### Docker Compose Services (5 Services)

```
┌─────────────────────────────────────────────────────────┐
│                       Nginx (Port 80)                   │
│                  Reverse Proxy & Static                 │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
┌────────▼────────┐    ┌────────▼───────────┐
│  Search Server  │    │  Static HTML Files │
│   (Flask:5000)  │    │   (Volume Mount)   │
└────────┬────────┘    └────────────────────┘
         │
         │
┌────────▼────────────────────────────────┐
│         PostgreSQL Database             │
│         (psycopg3 connection pool)      │
│         - Posts, Comments, Users        │
│         - FTS Indexes (GIN)             │
│         - Connection pool: 8-16 conns   │
└────────┬────────────────────────────────┘
         │
┌────────▼────────────┐
│  Builder Container  │
│  (reddarc.py)       │
│  - Streaming Import │
│  - HTML Export      │
└─────────────────────┘
```

### Service Descriptions

1. **postgres**: PostgreSQL 16 database
   - Stores all archive data
   - Full-text search indexes
   - Unix socket connection (15-30% faster)
   - Persistent volume for data

2. **redd-archiver-builder**: Python archive generator
   - Runs `reddarc.py` for import/export
   - Streams .zst files
   - Generates HTML output
   - One-time or scheduled operation

3. **redd-archiver-search-server**: Flask search API
   - RESTful search endpoints
   - Real-time PostgreSQL FTS queries
   - Rate limiting and security
   - Always-running service

4. **nginx**: Reverse proxy and static file server
   - Serves generated HTML
   - Proxies /search to Flask API
   - Gzip compression
   - Caching headers

5. **benchmark** (optional): Performance testing
   - Tests user page generation
   - Memory profiling
   - Timing analysis

### Volume Mounts

```
data/              → /data           (input .zst files)
output/            → /output         (generated HTML)
logs/              → /logs           (processing logs)
/var/run/postgres  → Unix socket     (DB connection)
```

### Environment Configuration

**Critical Variables**:
- `DATABASE_URL`: PostgreSQL connection string (REQUIRED)
- `POSTGRES_PASSWORD`: Database password (CHANGE IN PRODUCTION)
- `FLASK_SECRET_KEY`: Session secret (GENERATE RANDOM KEY)

**Performance Tuning**:
- `REDDARCHIVER_MAX_DB_CONNECTIONS`: Connection pool size
- `REDDARCHIVER_MAX_PARALLEL_WORKERS`: Parallel processing workers
- `REDDARCHIVER_USER_BATCH_SIZE`: Streaming batch size

See `.env.example` for complete configuration options.

### Horizontal Scaling for Very Large Archives

Redd-Archiver has been tested with archives up to hundreds of gigabytes per instance. For very large archive collections (multiple terabytes), deploy **multiple independent instances divided by topic**.

#### Scaling Architecture

```
                    Load Balancer (Optional)
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
┌────────▼────────┐ ┌──────▼──────┐ ┌───────▼────────┐
│   Instance 1    │ │ Instance 2  │ │  Instance 3    │
│   Technology    │ │   Gaming    │ │   Science      │
│   Subreddits    │ │ Subreddits  │ │  Subreddits    │
│                 │ │             │ │                │
│ ┌─────────────┐ │ │┌──────────┐ │ │┌─────────────┐ │
│ │ PostgreSQL  │ │ ││PostgreSQL│ │ ││ PostgreSQL  │ │
│ │ + Search    │ │ ││ + Search │ │ ││  + Search   │ │
│ └─────────────┘ │ │└──────────┘ │ │└─────────────┘ │
└─────────────────┘ └─────────────┘ └────────────────┘
   Port 8080          Port 8081        Port 8082
```

#### Why Horizontal Scaling?

**Single Instance Limits**:
- Tested: Hundreds of GB per instance
- Search performance optimal with manageable database size
- PostgreSQL FTS efficiency depends on index size

**Benefits of Multiple Instances**:
- **Efficient search**: Each database stays manageable (< 500GB)
- **Distributed load**: Parallel processing across instances
- **Topic organization**: Logical grouping (tech, gaming, science)
- **Independent scaling**: Scale individual topics as needed
- **Fault isolation**: One instance failure doesn't affect others

#### Deployment Strategies

**Option 1: Single Server with Multiple Ports**
```bash
# Instance 1: Technology (port 8080)
cd /archives/tech
docker compose up -d

# Instance 2: Gaming (port 8081)
cd /archives/gaming
PORT=8081 docker compose up -d

# Instance 3: Science (port 8082)
cd /archives/science
PORT=8082 docker compose up -d
```

**Option 2: Multiple Servers**
```bash
# Server 1: tech.archive.com
ssh tech-server
cd /archives && docker compose up -d

# Server 2: gaming.archive.com
ssh gaming-server
cd /archives && docker compose up -d

# Server 3: science.archive.com
ssh science-server
cd /archives && docker compose up -d
```

**Option 3: Topic-Based Domains**
```
tech.archive.com    → Instance 1 (Technology subreddits)
gaming.archive.com  → Instance 2 (Gaming subreddits)
science.archive.com → Instance 3 (Science subreddits)
```

#### When to Use Horizontal Scaling

- Archive collection exceeds 500GB
- Search performance degrades (queries > 2-3 seconds)
- Logical topic divisions exist in archive
- Want to distribute load across multiple servers
- Need fault isolation between topics

#### Topic Division Examples

**By Subject**:
- Technology: programming, linux, opensource, selfhosted
- Gaming: gaming, pcgaming, truegaming, patientgamers
- Science: science, askscience, space, physics

**By Size**:
- Large subreddits: Each gets own instance (r/AskReddit)
- Medium subreddits: Grouped by topic (5-10 per instance)
- Small subreddits: All grouped together (50+ per instance)

**By Activity**:
- High-traffic: Separate instances for frequently searched topics
- Low-traffic: Grouped instances for archival-only content

## Design Patterns

### 1. Producer-Consumer Pattern
**Usage**: Streaming user page generation

**Implementation**:
```python
queue = Queue(maxsize=10)  # Backpressure control

def producer():
    for batch in stream_user_batches():
        queue.put(batch)  # Blocks if queue full
    queue.put(None)  # Sentinel

def consumer():
    while True:
        batch = queue.get()
        if batch is None:
            break
        generate_user_pages(batch)

with ThreadPoolExecutor(max_workers=4) as executor:
    executor.submit(producer)
    for _ in range(4):
        executor.submit(consumer)
```

### 2. Batch Operations Pattern
**Usage**: Database insertions and queries

**Implementation**:
```python
def batch_insert(records, batch_size=1000):
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        db.executemany(
            "INSERT INTO table VALUES (%s, %s, %s)",
            [(r.a, r.b, r.c) for r in batch]
        )
        db.commit()
```

### 3. Template Method Pattern
**Usage**: HTML page generation

**Implementation**:
```python
class PageGenerator:
    def generate(self):
        data = self.fetch_data()      # Abstract
        context = self.prepare_context(data)
        return self.render_template(context)

    def fetch_data(self):
        raise NotImplementedError

    def prepare_context(self, data):
        return {'data': data}

    def render_template(self, context):
        return template.render(context)
```

### 4. Dependency Injection Pattern
**Usage**: Database connection management

**Implementation**:
```python
class ArchiveGenerator:
    def __init__(self, database):
        self.db = database  # Injected dependency

    def generate(self):
        posts = self.db.query_posts()
        # Use injected database
```

### 5. Checkpoint/Restart Pattern
**Usage**: Resume capability

**Implementation**:
```python
def process_with_checkpoint():
    last_checkpoint = db.get_metadata('last_checkpoint')
    for i, batch in enumerate(data_stream):
        if i <= last_checkpoint:
            continue  # Skip processed batches

        process_batch(batch)

        if i % 10 == 0:  # Checkpoint every 10 batches
            db.set_metadata('last_checkpoint', i)
```

## Future Enhancements

### Planned Improvements

1. **Read-Write Connection Splitting**
   - Separate read and write connection pools
   - Enable read replicas for scalability

2. **Parallel Batch Import**
   - Process multiple .zst files simultaneously
   - Coordinate with PostgreSQL connection pool

3. **Advanced Search Features**
   - Search suggestions (trigram similarity)
   - Trending searches (query analytics)
   - Author-specific search filters

4. **Enhanced Analytics**
   - Time-series visualizations
   - Activity heatmaps
   - Sentiment analysis integration

5. **Export Format Support**
   - JSON export for API consumption
   - Markdown export for documentation
   - RSS feeds for updates

6. **High Availability**
   - PostgreSQL replication support
   - Automatic failover
   - Load balancing for search API

## References

- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **psycopg3 Documentation**: https://www.psycopg.org/psycopg3/
- **Jinja2 Documentation**: https://jinja.palletsprojects.com/
- **Flask Documentation**: https://flask.palletsprojects.com/

---

**Document Version**: 1.0.0
**Last Updated**: 2025-12-27
**Maintainer**: Redd-Archiver Development Team
