# Redd-Archiver

[![License: Unlicense](https://img.shields.io/badge/license-Unlicense-blue.svg)](http://unlicense.org/)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL Required](https://img.shields.io/badge/PostgreSQL-required-blue.svg)](https://www.postgresql.org/)
[![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-brightgreen.svg)]()
[![Multi-Platform](https://img.shields.io/badge/platforms-Reddit%20%7C%20Voat%20%7C%20Ruqqus-orange.svg)]()
[![MCP Server](https://img.shields.io/badge/MCP-29%20tools-purple.svg)]()

Transform compressed data dumps into browsable HTML archives with flexible deployment options. Redd-Archiver supports offline browsing via sorted index pages OR full-text search with Docker deployment. Features mobile-first design, multi-platform support, and enterprise-grade performance with PostgreSQL full-text indexing.

**Supported Platforms**:
| Platform | Format | Status | Available Posts |
|----------|--------|--------|----------------|
| **Reddit** | .zst JSON Lines (Pushshift) | ✅ Full support | 2.38B posts (40,029 subreddits, through Dec 31 2024) |
| **Voat** | SQL dumps | ✅ Full support | 3.81M posts, 24.1M comments (22,637 subverses, complete archive) |
| **Ruqqus** | .7z JSON Lines | ✅ Full support | 500K posts (6,217 guilds, complete archive) |

*Tracked content: **2.384 billion posts across 68,883 communities** (Reddit full Pushshift dataset through Dec 31 2024, Voat/Ruqqus complete archives)*

**Version 1.0** features multi-platform archiving, REST API with 30+ endpoints, MCP server for AI integration, and PostgreSQL-backed architecture for large-scale processing.

## 🚀 Quick Start

**Try the live demo:** [Browse Example Archive →](https://online-archives.github.io/redd-archiver-example/)

**New to Redd-Archiver? Start here:** [QUICKSTART.md](QUICKSTART.md)

Get running in 2-15 minutes with our step-by-step guide covering:
- Local testing (5 minutes)
- Tor homelab deployment (2 minutes) - no domain or port forwarding needed!
- Production HTTPS (15 minutes)
- Example data testing

---

## 🎯 Key Features

### 🌐 Multi-Platform Support
Archive content from multiple link aggregator platforms in a single unified archive:

| Platform | Format | CLI Flag | URL Prefix |
|----------|--------|----------|------------|
| **Reddit** | .zst JSON Lines | `--subreddit` | `/r/` |
| **Voat** | SQL dumps | `--subverse` | `/v/` |
| **Ruqqus** | .7z JSON Lines | `--guild` | `/g/` |

- **Automatic Detection**: Platform auto-detected from file extensions
- **Unified Search**: PostgreSQL FTS searches across all platforms
- **Mixed Archives**: Combine Reddit, Voat, and Ruqqus in single archive

### 🤖 MCP Server (AI Integration)
29 MCP tools auto-generated from OpenAPI for AI assistants:

- **Full Archive Access**: Query posts, comments, users, search via Claude Desktop or Claude Code
- **Token Overflow Prevention**: Built-in LLM guidance with field selection and truncation
- **5 MCP Resources**: Instant access to stats, top posts, subreddits, search help
- **Claude Code Ready**: Copy-paste configuration for immediate use

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

See [MCP Server Documentation](mcp_server/README.md) for complete setup guide.

### Core Functionality
- **📱 Mobile-First Design**: Responsive layout optimized for all devices with touch-friendly navigation
- **🔍 Advanced Search System (Server Required)**: PostgreSQL full-text search optimized for Tor network. Search by keywords, subreddit, author, date, score. *Requires Docker deployment - offline browsing uses sorted index pages.*
- **⚡ JavaScript Free**: Complete functionality without JS, pure CSS interactions
- **🎨 Theme Support**: Built-in light/dark theme toggle with CSS-only implementation
- **♿ Accessibility**: WCAG compliant with keyboard navigation and screen reader support
- **🚄 Performance**: Optimized CSS (29KB), designed for low-bandwidth networks

### Technical Excellence
- **🏗️ Modular Architecture**: 18 specialized modules for maintainability and extensibility
- **🗄️ PostgreSQL Backend**: Large-scale processing with constant memory usage regardless of dataset size
- **⚡ Lightning-Fast Search**: PostgreSQL full-text search with GIN indexing
- **🌐 REST API v1**: 30+ endpoints with MCP/AI optimization for programmatic access to posts, comments, users, statistics, search, aggregations, and exports
- **🧅 Tor-Optimized**: Zero JavaScript, server-side search, no external dependencies
- **📊 Rich Statistics**: Comprehensive analytics dashboard with file size tracking
- **🔗 SEO Optimized**: Complete meta tags, XML sitemaps, and structured data
- **💾 Streaming Processing**: Memory-efficient with automatic resume capability
- **📈 Progress Tracking**: Real-time transfer rates, ETAs, and database metrics
- **🏆 Instance Registry**: Leaderboard system with completeness-weighted scoring for distributed archives

### Deployment Options
- **🏠 Local/Homelab**: HTTP on localhost or LAN (2 commands)
- **🌐 Production HTTPS**: Automated Let's Encrypt setup (5 minutes)
- **🧅 Tor Hidden Service**: .onion access, zero networking config (2 minutes)
- **🔀 Dual-Mode**: HTTPS + Tor simultaneously
- **📄 Static Hosting**: GitHub/Codeberg Pages for small archives (browse-only, no search)

## 📦 Deployment Options

Redd-Archiver generates static HTML files that can be browsed offline OR deployed with full-text search:

| Mode | Search | Server | Setup Time | Use Case |
|------|--------|--------|------------|----------|
| **Offline Browsing** | ❌ Browse-only | None | 0 min | USB drives, local archives, offline research |
| **Static Hosting** | ❌ Browse-only | GitHub/Codeberg Pages | 10 min | Free public hosting (size limits) |
| **Docker Local** | ✅ PostgreSQL FTS | localhost | 5 min | Development, testing |
| **Docker + Tor** | ✅ PostgreSQL FTS | .onion hidden service | 2 min | Private sharing, no port forwarding |
| **Docker + HTTPS** | ✅ PostgreSQL FTS | Public domain | 15 min | Production public archives |

**Offline Browsing Features**:
- Sorted index pages (by score, comments, date)
- Pagination for large subreddits
- Full comment threads and user pages
- Works by opening HTML files directly

**With Search Server**:
- PostgreSQL full-text search with GIN indexing
- Search by keywords, subreddit, author, date, score
- Sub-second results, Tor-compatible
- Requires Docker deployment

---

## 🚨 Get Involved: Help Preserve Internet History

Internet content disappears every day. Communities get banned, platforms shut down, and valuable discussions vanish. **You can help prevent this.**

### 📥 Download & Mirror Data Now

**Don't wait for content to disappear.** Download these datasets today:

| Platform | Size | Posts | Download |
|----------|------|-------|----------|
| **Reddit** | 3.28TB | 2.38B posts | [Academic Torrents](https://academictorrents.com/details/1614740ac8c94505e4ecb9d88be8bed7b6afddd4) · [Magnet Link](magnet:?xt=urn:btih:1614740ac8c94505e4ecb9d88be8bed7b6afddd4&tr=https%3A%2F%2Facademictorrents.com%2Fannounce.php&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce) |
| **Voat** | ~15GB | 3.8M posts | [Archive.org](https://archive.org/details/voat-archive-2021) † |
| **Ruqqus** | ~752MB | 500K posts | [Archive.org](https://archive.org/details/ruqqus-archive-2021) ‡ |

† **Voat Performance Tip**: Use [pre-split files](tools/README_VOAT_SPLITTER.md) for 1000x faster imports (2-5 min vs 30+ min per subverse)
‡ **Ruqqus**: Docker image includes p7zip for automatic .7z decompression

**Every mirror matters.** Store locally, seed torrents, share with researchers. Be part of the preservation network.

### 🌐 Join the Registry: Deploy Your Instance

**Already running an archive?** Register it on our public leaderboard:

1. Deploy your instance ([Quick Start](QUICKSTART.md) - 2-15 minutes)
2. Submit via [Registry Template](.github/ISSUE_TEMPLATE/register-instance.yml)
3. Join coordinated preservation efforts with other teams

**Benefits**:
- Public visibility and traffic
- Coordinated archiving to avoid duplication
- Team collaboration opportunities
- Leaderboard recognition

👉 **[Register Your Instance Now →](.github/ISSUE_TEMPLATE/register-instance.yml)**

### 🆕 Submit New Data Sources

**Found a new platform dataset?** Help expand the archive network:

- Lemmy databases
- Hacker News archives
- Alternative Reddit archives
- Other link aggregator platforms

👉 **[Submit Data Source →](.github/ISSUE_TEMPLATE/submit-data-source.yml)**

**Why submit?**
- Makes data discoverable for other archivists
- Prevents duplicate preservation efforts
- Builds comprehensive multi-platform archive ecosystem
- Tracks data availability before platforms disappear

---

## 📸 Screenshots

### Dashboard
![Dashboard](screenshots/01-dashboard.png)

Main landing page showing archive overview with statistics for 9,592 posts across Reddit, Voat, and Ruqqus. Features customizable branding (site name, project URL), responsive cards, activity metrics, and content statistics. *(Works offline)*

### Subreddit Index
![Subreddit Index](screenshots/02-subreddit-index.png)

Post listing with sorting options (score, comments, date), pagination, and badge coloring. Includes navigation and theme toggle. *(Works offline - sorted by score/comments/date)*

### Post Page with Comments
![Post Page](screenshots/03-post-page.png)

Individual post displaying nested comment threads with collapsible UI, user flair, and timestamps. Comments include anchor links for direct navigation from user pages. *(Works offline)*

### Mobile Responsive Design
<p align="center">
  <img src="screenshots/05-mobile-dashboard.png" width="375" alt="Mobile Dashboard">
</p>

Fully optimized for mobile devices with touch-friendly navigation and responsive layout.

### Search Interface
![Search Form](screenshots/07-search-form.png)

PostgreSQL full-text search with Google-style operators. Supports filtering by subreddit, author, date range, and score. *(Requires Docker deployment)*

![Search Results](screenshots/08-search-results.png)

Search results with highlighted excerpts using PostgreSQL `ts_headline()`. Sub-second response times with GIN indexing. *(Server-based, Tor-compatible)*

> **Sample Archive**: Multi-platform archive featuring programming and technology communities from Reddit, Voat, and Ruqqus · [See all screenshots →](screenshots/)

## 🛠️ Installation

### Prerequisites
- **Python 3.7 or higher**
- **PostgreSQL 12+** (required for v1.0+)
- 4GB+ RAM (PostgreSQL uses constant memory)
- Disk space: ~1.5-2x your input .zst file size for PostgreSQL database

### Python Dependencies
Redd-Archiver uses modern, performance-focused dependencies:

**Core:**
- `psycopg[binary,pool]==3.2.3` - PostgreSQL adapter with connection pooling
- `zstandard==0.23.0` - Fast .zst decompression
- `psutil==6.1.1` - System resource monitoring

**HTML Generation:**
- `jinja2>=3.1.6` - Modern template engine with inheritance
- `rcssmin>=1.1.2` - CSS minification for smaller file sizes

**Performance:**
- `orjson>=3.11.4` - Fast JSON parsing

### Quick Start

#### Option 1: Docker (Recommended)

```bash
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver

# Create required directories
mkdir -p data output/.postgres-data logs tor-public

# Copy environment template and configure
cp .env.example .env
# Edit .env with your settings (change default passwords!)

# Start PostgreSQL container
docker-compose up -d

# Install Python dependencies
pip install -r requirements.txt

# Configure database connection
export DATABASE_URL="postgresql://reddarchiver:your_password_here@localhost:5432/reddarchiver"

# Run the archive generator
python reddarc.py /path/to/data/ --output my-archive/
```

#### Option 2: Local PostgreSQL

```bash
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver

# Install PostgreSQL (Ubuntu/Debian)
sudo apt update && sudo apt install postgresql postgresql-contrib

# Or on macOS
brew install postgresql@16 && brew services start postgresql@16

# Create database
sudo -u postgres createuser redd-archiver
sudo -u postgres createdb -O redd-archiver redd-archiver
sudo -u postgres psql -c "ALTER USER redd-archiver WITH PASSWORD 'your_password_here';"

# Install Python dependencies
pip install -r requirements.txt

# Configure database connection
export DATABASE_URL="postgresql://reddarchiver:your_password_here@localhost:5432/reddarchiver"

# Run the archive generator
python reddarc.py /path/to/data/ --output my-archive/
```

#### Upgrading?

Review the CHANGELOG.md for version updates and changes.

## 📊 Usage

### 1. Prepare Your Data

Redd-Archiver processes data dumps from multiple platforms:

| Platform | Format | Data Sources |
|----------|--------|--------------|
| **Reddit** | .zst JSON Lines | [Pushshift Complete Dataset](https://academictorrents.com/details/1614740ac8c94505e4ecb9d88be8bed7b6afddd4) · [Magnet Link](magnet:?xt=urn:btih:1614740ac8c94505e4ecb9d88be8bed7b6afddd4&tr=https%3A%2F%2Facademictorrents.com%2Fannounce.php&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce) · 3.28TB · 2.38B posts · 40K subreddits |
| **Voat** | SQL dumps | [Voat Archive 2021](https://archive.org/details/voat-archive-2021) · 22,637 subverses · 3.8M posts · 24M comments · Complete archive |
| **Ruqqus** | .7z JSON Lines | [Ruqqus Archive 2021](https://archive.org/details/ruqqus-archive-2021) · 6,217 guilds · Complete archive |

### 2. Identify High-Priority Communities (Optional)

**Scanner Tools** help you identify which communities to archive first based on priority scores:

```bash
# Scan Reddit data (generates subreddits_complete.json)
python tools/find_banned_subreddits.py /path/to/reddit-data/ --output tools/subreddits_complete.json

# Scan Voat data (generates subverses.json)
python tools/scan_voat_subverses.py /path/to/voat-data/ --output tools/subverses.json

# Scan Ruqqus data (generates guilds.json)
python tools/scan_ruqqus_guilds.py /path/to/ruqqus-data/ --output tools/guilds.json
```

**What the scanners do**:
- Calculate archive priority scores (0-100) for each community
- Track post counts, activity periods, deletion rates, NSFW content
- Identify restricted, quarantined, or banned communities (highest priority)
- Sort communities by archival importance

**Example output**:
- **Reddit**: 40,029 subreddits from 2.38B posts analyzed
- **Voat**: 15,545 subverses from 3.81M posts + 24.1M comments analyzed
- **Ruqqus**: 6,217 guilds from 500K posts analyzed
- **Status breakdown** (Reddit): 26,552 active, 8,642 restricted, 4,803 inactive, 32 quarantined

**Use cases**:
- **Targeted archiving**: Archive high-risk communities first (restricted, quarantined)
- **Storage planning**: Identify largest communities before downloading
- **Historical research**: Find communities with high deletion/removal rates

**Output files** (included in `tools/` directory):
- `subreddits_complete.json` - Reddit subreddit statistics (40,029 communities, 46MB)
- `subverses.json` - Voat subverse statistics (22,585 communities, 14MB)
- `guilds.json` - Ruqqus guild statistics (6,217 communities, 3.6MB)

View the [complete data catalog](tools/README.md) to browse all communities and their priority scores.

### 3. Configure PostgreSQL

Ensure DATABASE_URL is set (see Installation above):

```bash
export DATABASE_URL="postgresql://reddarchiver:password@localhost:5432/reddarchiver"
```

### 4. Generate Your Archive

**Reddit Archives (.zst files):**
```bash
# Auto-discovery (processes all .zst files in directory)
python reddarc.py /path/to/pushshift-data/ --output my-archive/

# Single subreddit
python reddarc.py /data --subreddit privacy \
  --comments-file /data/privacy_comments.zst \
  --submissions-file /data/privacy_submissions.zst \
  --output my-archive/
```

**Voat Archives (SQL dumps):**
```bash
# Import Voat subverses
python reddarc.py /data --subverse voatdev,pics --output my-archive/ --import-only

# Export HTML after import
python reddarc.py /data --output my-archive/ --export-from-database
```

**Ruqqus Archives (.7z files):**
```bash
# Import Ruqqus guilds
python reddarc.py /data --guild Quarantine,News --output my-archive/ --import-only

# Export HTML after import
python reddarc.py /data --output my-archive/ --export-from-database
```

**Multi-Platform Mixed Archive:**
```bash
# Import from multiple platforms into single archive
python reddarc.py /reddit-data --subreddit privacy --output unified-archive/ --import-only
python reddarc.py /voat-data --subverse technology --output unified-archive/ --import-only
python reddarc.py /ruqqus-data --guild Tech --output unified-archive/ --import-only

# Generate HTML for all platforms
python reddarc.py /any-path --output unified-archive/ --export-from-database
```

**With filtering and SEO:**
```bash
python reddarc.py /data/ --output my-archive/ \
  --min-score 100 --min-comments 50 \
  --base-url https://example.com \
  --site-name "My Archive"
```

**Import/Export workflow (for large datasets):**
```bash
# Import data to PostgreSQL (no HTML generation)
python reddarc.py /data/ --output my-archive/ --import-only

# Export HTML from PostgreSQL (no data import)
python reddarc.py /data/ --output my-archive/ --export-from-database
```

### 4. Deploy Your Archive

Multiple deployment options available:

**Local/Development** (HTTP):
```bash
docker compose up -d
# Access: http://localhost
```

**Production HTTPS** (Let's Encrypt):
```bash
./docker/scripts/init-letsencrypt.sh
# Access: https://your-domain.com
```

**Homelab/Tor** (.onion hidden service):
```bash
docker compose -f docker-compose.yml -f docker-compose.tor-only.yml --profile tor up -d
# Access: http://[your-address].onion (via Tor Browser)
# No port forwarding or domain required!
```

**Dual-Mode** (HTTPS + Tor):
```bash
docker compose --profile production --profile tor up -d
# Access: Both https://your-domain.com and http://[address].onion
```

**Static Hosting** (GitHub/Codeberg Pages):
```bash
# Generate archive locally, push to GitHub/Codeberg
python reddarc.py /data --output archive/
cd archive/
git init && git add . && git commit -m "Initial archive"
git remote add origin https://github.com/username/repo.git
git push -u origin main
# Enable Pages in repository settings
```

**See deployment guides**:
- [Docker Deployment Guide](docker/README.md) - Complete Docker setup with HTTPS and Tor
- [Tor Deployment Guide](docs/TOR_DEPLOYMENT.md) - Tor hidden service for homelab and privacy
- [Static Deployment Guide](docs/STATIC_DEPLOYMENT.md) - GitHub Pages / Codeberg Pages (browse-only)

### 5. Advanced CLI Options

**Processing Control:**
```bash
--hide-deleted-comments    # Hide [deleted]/[removed] comments in output
--no-user-pages           # Skip user page generation (saves memory)
--dry-run                 # Preview discovered files without processing
--force-rebuild           # Ignore resume state and rebuild from scratch
--force-parallel-users    # Override auto-detection for parallel processing
```

**Logging:**
```bash
--log-file <path>         # Custom log file location (default: output/.archive-error.log)
--log-level DEBUG         # Set logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
```

**Performance Tuning:**
```bash
--debug-memory-limit 8.0      # Override memory limit in GB (default: auto-detect)
--debug-max-connections 8     # Override DB connection pool size (default: auto-detect)
--debug-max-workers 4         # Override parallel workers (default: auto-detect)
```

**Environment Variables:**
```bash
# Required
DATABASE_URL=postgresql://user:pass@host:5432/reddarchiver

# Optional Performance Tuning (auto-detected if not set)
REDDARCHIVER_MAX_DB_CONNECTIONS=8       # Connection pool size
REDDARCHIVER_MAX_PARALLEL_WORKERS=4     # Parallel processing workers
REDDARCHIVER_USER_BATCH_SIZE=2000       # User page batch size
REDDARCHIVER_QUEUE_MAX_BATCHES=10       # Queue backpressure control
REDDARCHIVER_CHECKPOINT_INTERVAL=10     # Progress save frequency
REDDARCHIVER_USER_PAGE_WORKERS=4        # User page generation workers
```

## 🏗️ Architecture

Redd-Archiver features a clean modular architecture with specialized components:

### Project Structure
```
reddarc.py              # Main CLI entry point
search_server.py        # Flask search API server
version.py              # Version metadata

core/                   # Core processing & database
├── postgres_database.py    # PostgreSQL backend
├── postgres_search.py      # PostgreSQL FTS implementation
├── write_html.py           # HTML generation coordinator
├── watchful.py             # .zst streaming utilities
├── incremental_processor.py # Incremental processing
└── importers/              # Multi-platform importers
    ├── base_importer.py        # Abstract base class
    ├── reddit_importer.py      # .zst JSON Lines parser
    ├── voat_importer.py        # SQL dump coordinator
    ├── voat_sql_parser.py      # SQL INSERT parser
    └── ruqqus_importer.py      # .7z JSON Lines parser

api/                    # REST API v1
├── __init__.py             # Blueprint registration
└── routes.py               # 30+ API endpoints

mcp_server/             # MCP Server for AI integration
├── server.py               # FastMCP server (29 tools)
├── README.md               # MCP documentation
└── tests/                  # MCP server tests

utils/                  # Utility functions
├── console_output.py       # Console output formatting
├── error_handling.py       # Error handling utilities
├── input_validation.py     # Input validation
├── regex_utils.py          # Regular expression utilities
├── search_operators.py     # Search query parsing
└── simple_json_utils.py    # JSON utilities

processing/             # Data processing modules
├── parallel_user_processing.py  # Parallel user page generation
├── batch_processing_utils.py    # Batch processing utilities
└── incremental_statistics.py    # Statistics tracking

monitoring/             # Performance & monitoring
├── performance_monitor.py      # Performance monitoring
├── performance_phases.py       # Phase tracking
├── performance_timing.py       # Timing utilities
├── auto_tuning_validator.py    # Auto-tuning validation
├── streaming_config.py         # Auto-detecting configuration
└── system_optimizer.py         # System optimization
```

### HTML Modules (18 specialized modules)
```
html_modules/
├── html_seo.py                # SEO, meta tags, sitemaps
├── html_pages_jinja.py        # Jinja2-based page generation
├── html_statistics.py         # Analytics and metrics
├── dashboard_helpers.py       # Dashboard utility functions
├── html_field_generation.py   # Dynamic field generation
├── jinja_filters.py           # Custom Jinja2 filters
├── html_pages.py              # Core page generation
├── html_comments.py           # Comment threading system
├── __init__.py                # Public API exports
├── jinja_env.py               # Jinja2 environment setup
├── html_utils.py              # File operations, utilities
├── html_dashboard_jinja.py    # Jinja2 dashboard rendering
├── css_minifier.py            # CSS minification
├── html_scoring.py            # Dynamic score badges
├── html_templates.py          # Template management
├── html_url.py                # URL processing, domains
├── html_dashboard.py          # Dashboard generation
└── html_constants.py          # Configuration values
```

### Jinja2 Templates (15 templates)
```
templates_jinja2/
├── base/
│   └── base.html              # Master layout template
├── components/
│   ├── dashboard_card.html    # Dashboard statistics cards
│   ├── footer.html            # Site footer
│   ├── global_summary.html    # Global statistics summary
│   ├── navigation.html        # Site navigation bar
│   ├── post_card.html         # Post display card
│   ├── user_comment.html      # User comment display
│   └── user_post.html         # User post display
├── macros/
│   ├── comment_macros.html    # Comment rendering macros
│   └── reddit_macros.html     # Reddit-specific macros
└── pages/
    ├── global_search.html     # Global search page
    ├── index.html             # Dashboard homepage
    ├── link.html              # Individual post page
    ├── subreddit.html         # Subreddit listing page
    └── user.html              # User profile page
```

### Database Schema
```
sql/
├── schema.sql                 # PostgreSQL table definitions
├── indexes.sql                # Performance indexes (GIN, B-tree)
├── fix_statistics.sql         # Statistics maintenance queries
└── migrations/
    └── 003_add_total_activity_column.sql  # Schema migration
```

## 🔍 PostgreSQL Full-Text Search

### Lightning-Fast Database Search

Redd-Archiver v1.0 uses PostgreSQL full-text search with GIN indexing for blazing-fast search capabilities:

**Key Features:**
- **Database-Powered**: Native PostgreSQL indexing with constant memory usage
- **Large-Scale**: Efficiently search large datasets (tested with hundreds of GB)
- **Relevance Ranking**: PostgreSQL `ts_rank()` for intelligent result ordering
- **Highlighted Excerpts**: `ts_headline()` shows matching content in context
- **Advanced Filters**: Search by subreddit, author, date range, score
- **Concurrent Queries**: Handle multiple search requests simultaneously

### Search API

PostgreSQL search is exposed via `postgres_search.py` (CLI) and `search_server.py` (Web API):

**Command-Line Interface:**
```bash
# Search command-line interface
python postgres_search.py "your query" --subreddit technology --limit 50

# Example: Search for posts about "machine learning" with high scores
python postgres_search.py "machine learning" --min-score 100 --limit 20
```

**Web API** (✅ Implemented):
```bash
# Start search server with Docker Compose (recommended)
docker-compose up -d reddarchiver-search-server

# Or run directly
export DATABASE_URL="postgresql://user:pass@localhost:5432/reddarchiver"
python search_server.py

# Access at http://localhost:5000
```

**Features:**
- RESTful search API with JSON responses
- Real-time search with PostgreSQL FTS
- Rate limiting and CSRF protection
- Health check endpoint: `GET /health`
- Search endpoint: `GET /search?q=query&subreddit=optional&limit=50`
- Result highlighting with `ts_headline()`
- Search suggestions and trending searches

## 🌐 REST API & Registry

### REST API v1

Full-featured API with 30+ endpoints for programmatic access and MCP/AI integration:

| Category | Endpoints | Key Features |
|----------|-----------|--------------|
| **System** (5) | `/health`, `/stats`, `/schema`, `/openapi.json` | Health checks, statistics, capability discovery, OpenAPI spec |
| **Posts** (13) | `/posts`, `/posts/{id}`, `/posts/{id}/comments`, `/posts/{id}/context`, `/posts/{id}/comments/tree`, `/posts/{id}/related`, `/posts/random`, `/posts/aggregate`, `/posts/batch` | List, single, comments, context, tree, related, random, aggregate, batch |
| **Comments** (7) | `/comments`, `/comments/{id}`, `/comments/random`, `/comments/aggregate`, `/comments/batch` | List, single, random, aggregate, batch |
| **Users** (8) | `/users`, `/users/{username}`, `/users/{username}/summary`, `/users/{username}/posts`, `/users/{username}/comments`, `/users/aggregate`, `/users/batch` | List, profiles, summary, activity, aggregate, batch |
| **Subreddits** (4) | `/subreddits`, `/subreddits/{name}`, `/subreddits/{name}/summary` | List, statistics, summary |
| **Search** (3) | `/search`, `/search/explain` | Full-text search with operators, query debugging |

**MCP/AI-Optimized Features**:
- **Field Selection**: `?fields=id,title,score` for token optimization
- **Truncation Controls**: `?max_body_length=500&include_body=false` for response size management
- **Export Formats**: `?format=csv|ndjson` for data analysis
- **Batch Endpoints**: Reduce N requests to 1 with `/posts|comments|users/batch`
- **Context Endpoints**: Single-call discussion retrieval with `/posts/{id}/context`
- **Search Operators**: Google-style syntax (`"exact"`, `OR`, `-exclude`, `sub:`, `author:`, `score:`)

Rate limited to 100 requests/minute. See [API Documentation](docs/API.md) for complete reference.

### Instance Registry & Leaderboard

Redd-Archiver supports a distributed registry system for tracking archive instances:

- **Instance Metadata**: Configure via environment variables or CLI flags (`--site-name`, `--contact`, `--team-id`)
- **Leaderboard Generator**: Automated scoring based on archive completeness and content risk
- **Team Grouping**: Group multiple instances under a team ID for coordinated archiving

See [Registry Setup Guide](docs/REGISTRY_SETUP.md) for configuration.

## 📈 Performance & Optimization

### PostgreSQL Backend Performance (v1.0+)

**Constant Memory Usage:**
- **4GB RAM**: Process large datasets efficiently (tested with hundreds of GB)
- **8GB RAM**: Optimal for concurrent operations
- **16GB+ RAM**: Ideal for parallel user page generation

**Database Storage:**
| Input (.zst) | PostgreSQL DB | HTML Output | Example |
|--------------|---------------|-------------|---------|
| 93.6MB | ~150MB | 1.4GB | r/technology |
| 100MB | ~160MB | ~1.5GB | Small archives |
| 500MB | ~800MB | ~7.5GB | Research projects |
| 2GB | ~3.2GB | ~30GB | Large collections |
| 100GB | ~160GB | ~1.5TB | Enterprise-scale |

**Processing Speed:**
- **Data Import**: Fast streaming ingestion to PostgreSQL
- **HTML Generation**: Efficient database-backed rendering
- **Search Index**: Instant with PostgreSQL GIN indexes
- **Performance**: Scales with dataset size, optimized for large archives

### Search Performance

Performance varies based on dataset size, query complexity, and hardware:

- **PostgreSQL FTS**: Fast indexed search for large datasets
- **GIN Indexes**: Optimized index lookups for text search
- **Concurrent Queries**: Supports multiple simultaneous searches with connection pooling
- **Memory Efficient**: Constant memory usage with streaming results

### Architecture Benefits

**PostgreSQL v1.0 Features**:
- **Large-Scale Processing**: Efficiently handle large datasets (tested with hundreds of GB)
- **Constant Memory**: 4GB RAM regardless of dataset size
- **Fast Search**: PostgreSQL FTS with GIN indexing
- **Resume Capability**: Database-backed progress tracking
- **Concurrent Processing**: Multi-connection pool for parallel operations

## 🔀 Scaling for Very Large Archives

### Single Instance Limits

Redd-Archiver has been tested with archives up to hundreds of gigabytes. For optimal performance:
- **Tested scale**: Hundreds of GB per instance
- **Memory usage**: Constant 4GB RAM regardless of dataset size
- **Database**: PostgreSQL handles large datasets efficiently

### Horizontal Scaling Strategy

For very large archive collections (multiple terabytes), deploy **multiple instances divided by topic**:

**Architecture**:
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Instance 1     │     │  Instance 2     │     │  Instance 3     │
│  Technology     │     │  Gaming         │     │  Science        │
│  Subreddits     │     │  Subreddits     │     │  Subreddits     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Benefits**:
- **Efficient search**: Each database stays manageable size
- **Distributed load**: Parallel processing across instances
- **Topic organization**: Logical grouping of related content
- **Independent scaling**: Scale individual topics as needed

**Deployment Options**:
1. **Single server**: Multiple Docker Compose stacks with different ports
2. **Multiple servers**: One instance per physical/virtual machine
3. **Topic-based domains**: tech.archive.com, gaming.archive.com, etc.

**Example Multi-Instance Setup**:
```bash
# Instance 1: Technology topics (port 8080)
cd /archives/tech
docker compose up -d

# Instance 2: Gaming topics (port 8081)
cd /archives/gaming
docker compose -f docker-compose.yml up -d

# Instance 3: Science topics (port 8082)
cd /archives/science
docker compose -f docker-compose.yml up -d
```

**When to Use**:
- Archive collection exceeds 500GB
- Search performance degrades with single instance
- Logical topic divisions exist in your archive
- Want to distribute load across multiple servers

## 🎯 Use Cases

### Research & Academia
- Studying online discourse and community dynamics
- Analyzing social movements and trends
- Preserving internet culture

### Community Archiving
- Backing up subreddits before potential removal
- Creating offline-accessible community resources
- Distributing knowledge repositories

### Investigation & Analysis
- Pattern analysis in deleted/removed content
- User behavior studies
- Content moderation research

## 📚 Documentation

### Deployment Guides
- **[Docker Deployment Guide](docker/README.md)** - Complete Docker setup including PostgreSQL, nginx, HTTPS, and Tor
- **[Tor Deployment Guide](docs/TOR_DEPLOYMENT.md)** - Tor hidden service setup for homelab and privacy deployments
- **[Static Deployment Guide](docs/STATIC_DEPLOYMENT.md)** - GitHub Pages and Codeberg Pages deployment (browse-only, no search)

### API & Integration
- **[REST API Documentation](docs/API.md)** - Complete API reference with 30+ endpoints
- **[MCP Server Documentation](mcp_server/README.md)** - AI integration with Claude Desktop/Claude Code
- **[Registry Setup Guide](docs/REGISTRY_SETUP.md)** - Instance registry configuration

### Project Documentation
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development guidelines and contribution procedures
- **[SECURITY.md](SECURITY.md)** - Security policy and vulnerability reporting
- **[LICENSE](LICENSE)** - Unlicense (public domain)

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines, code structure, and testing procedures.

Key areas for contribution:
- PostgreSQL query optimizations
- Additional export formats
- Enhanced search features
- Documentation improvements

See our modular architecture (18 specialized modules) for easy entry points to contribute.

---

## 📝 License

This is free and unencumbered software released into the public domain. See the [LICENSE](LICENSE) file (Unlicense) for details.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software for any purpose, commercial or non-commercial, and by any means.

## 📦 Data Sources

This project leverages public datasets from the following sources:

- **[Pushshift](https://github.com/pushshift/api)** - Reddit data access and archival infrastructure
- **[Watchful1's PushshiftDumps](https://github.com/Watchful1/PushshiftDumps)** - Comprehensive data dump tools and torrent management
- **[Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift)** - Making Reddit data accessible to researchers and the public
- **[Ruqqus Public Dataset](https://archive.org/details/ruqqus-public-dataset)** - 752 MB Ruqqus archive (comments and submissions)
- **[SearchVoat Archive](https://archive.org/details/searchvoat.co)** - 16.8 GB Voat.co complete backup

## 🙏 Acknowledgments

This project builds upon the work of several excellent archival projects:

- **[reddit-html-archiver](https://github.com/libertysoft3/reddit-html-archiver)** by libertysoft3 - Original inspiration and foundation for static HTML generation
- **[redarc](https://github.com/Yakabuff/redarc)** - Self-hosted Reddit archiving with PostgreSQL and full-text search
- **[red-arch](https://github.com/sys-nyx/red-arch)** - Static website generator for Reddit subreddit archives
- **[zst_blocks_format](https://github.com/ArthurHeitmann/zst_blocks_format)** - Efficient block-based compression format for processing large datasets

## 📧 Contact

- **GitHub Issues**: [Report bugs or request features](https://github.com/19-84/redd-archiver/issues)
- **GitHub Discussions**: [Ask questions or share ideas](https://github.com/19-84/redd-archiver/discussions)
- **Security Issues**: [Report via GitHub Security Advisories](https://github.com/19-84/redd-archiver/security/advisories/new)

## 💰 Support the Project

**Redd-Archiver was built by one person over 6 months** as a labor of love to preserve internet history before it disappears forever.

This isn't backed by a company or institution—just an individual committed to keeping valuable discussions accessible. Your support helps:

- Continue development and bug fixes
- Maintain documentation and support
- Cover infrastructure costs (servers, storage, bandwidth)
- Preserve more data sources and platforms

Every donation, no matter the size, helps keep this preservation effort alive.

### Bitcoin (BTC)

```
bc1q8wpdldnfqt3n9jh2n9qqmhg9awx20hxtz6qdl7
```

<p align="center">
  <img src="qr-codes/btc.jpg" width="400" alt="Bitcoin QR Code">
  <br>
  <em>Scan to donate Bitcoin</em>
</p>

### Monero (XMR)

```
42zJZJCqxyW8xhhWngXHjhYftaTXhPdXd9iJ2cMp9kiGGhKPmtHV746EknriN4TNqYR2e8hoaDwrMLfv7h1wXzizMzhkeQi
```

<p align="center">
  <img src="qr-codes/xmr.jpg" width="400" alt="Monero QR Code">
  <br>
  <em>Scan to donate Monero</em>
</p>

**Thank you for supporting internet archival efforts!** Every contribution helps maintain and improve this project.

---

This software is provided "as is" under the Unlicense. See [LICENSE](LICENSE) for details. Users are responsible for compliance with applicable laws and terms of service when processing data.
