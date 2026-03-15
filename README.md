# Redd-Archiver

[![License: Unlicense](https://img.shields.io/badge/license-Unlicense-blue.svg)](http://unlicense.org/)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL Required](https://img.shields.io/badge/PostgreSQL-required-blue.svg)](https://www.postgresql.org/)
[![Version 1.0.0](https://img.shields.io/badge/version-1.0.0-brightgreen.svg)]()
[![Multi-Platform](https://img.shields.io/badge/platforms-Reddit%20%7C%20Voat%20%7C%20Ruqqus-orange.svg)]()
[![MCP Server](https://img.shields.io/badge/MCP-29%20tools-purple.svg)]()
[![Codeberg Mirror](https://img.shields.io/badge/mirror-Codeberg-2185D0.svg?logo=codeberg)](https://codeberg.org/19-84/redd-archiver)
[![GitGud Mirror](https://img.shields.io/badge/mirror-GitGud-FC6D26.svg?logo=gitlab)](https://gitgud.io/1984/redd-archiver)

> **⭐ If you find this project useful, please star the repo!** It helps others discover the tool and motivates continued development.

Transform compressed data dumps into browsable HTML archives with flexible deployment options. Redd-Archiver supports offline browsing via sorted index pages OR full-text search with Docker deployment. Features mobile-first design, multi-platform support, and enterprise-grade performance with PostgreSQL full-text indexing.

**Supported Platforms**:
| Platform | Format | Status | Available Posts | Data |
|----------|--------|--------|----------------|------|
| **Reddit** | .zst JSON Lines (Pushshift) | ✅ Full support | 2.38B posts (40,029 subreddits, through Dec 31 2025) | [Download](https://academictorrents.com/details/3e3f64dee22dc304cdd2546254ca1f8e8ae542b4) |
| **Voat** | SQL dumps | ✅ Full support | 3.81M posts, 24.1M comments (22,637 subverses, complete archive) | [Download](https://archive.org/details/voat-archive-2021) |
| **Ruqqus** | .7z JSON Lines | ✅ Full support | 500K posts (6,217 guilds, complete archive) | [Download](https://archive.org/details/ruqqus-archive-2021) |

*Tracked content: **2.384 billion posts across 68,883 communities** (Reddit full Pushshift dataset through Dec 31 2025, Voat/Ruqqus complete archives)*

**Version 1.0** features multi-platform archiving, REST API with 30+ endpoints, MCP server for AI integration, and PostgreSQL-backed architecture for large-scale processing.

## 🚀 Quick Start

**Archive internet history before it disappears** - Deploy in 2 minutes, no domain required.

**Try the live demo:** [Browse Example Archive →](https://online-archives.github.io/redd-archiver-example/)

**→ [QUICKSTART.md](QUICKSTART.md)** - Step-by-step deployment:
- **2 min**: Tor hidden service (no domain, no port forwarding, works behind CGNAT)
- **5 min**: Local testing (HTTP on localhost)
- **15 min**: Production HTTPS (automated Let's Encrypt)

**Why now?** Communities get banned, platforms shut down, discussions vanish. Start preserving today.

---

## Documentation

**→ First time here?** [QUICKSTART.md](QUICKSTART.md) - Deploy in 2-15 minutes

**→ Quick answers?** [FAQ](docs/FAQ.md) - Common questions answered in 30 seconds

**→ Need help?** [Troubleshooting](docs/TROUBLESHOOTING.md) - Fix common issues

**→ Using the API?** [API Reference](docs/API.md) - 30+ REST endpoints

**→ How it works?** [Architecture](ARCHITECTURE.md) - Technical deep-dive

**→ Deployment guides:**
- [Tor Hidden Service](docs/TOR_DEPLOYMENT.md) - .onion setup (2 min, no domain needed)
- [HTTPS Production](QUICKSTART.md#production-https-15-minutes) - Let's Encrypt SSL (15 min)
- [Static Hosting](docs/STATIC_DEPLOYMENT.md) - GitHub/Codeberg Pages (browse-only)
- [Docker Reference](docker/README.md) - Complete Docker guide

**→ Advanced:**
- [MCP Server](mcp_server/README.md) - AI integration (Claude Desktop/Code)
- [Scanner Tools](docs/SCANNER_TOOLS.md) - Data discovery utilities
- [Registry Setup](docs/REGISTRY_SETUP.md) - Instance leaderboard

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

**Prerequisites**: Python 3.7+, PostgreSQL 12+, 4GB+ RAM

**Quick Install** (Docker):
```bash
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver

# Create required directories
mkdir -p data output/.postgres-data logs tor-public

# Configure environment (IMPORTANT: change passwords!)
cp .env.example .env
nano .env  # Edit POSTGRES_PASSWORD and DATABASE_URL

# Start services
docker compose up -d

# Generate archive (after downloading .zst files to data/)
python reddarc.py data/ \
  --subreddit privacy \
  --comments-file data/privacy_comments.zst \
  --submissions-file data/privacy_submissions.zst \
  --output output/
```

**Detailed installation procedures** (Docker, Ubuntu/Debian, macOS, Windows WSL2):
- **[Installation Guide](docs/INSTALLATION.md)** - Platform-specific setup and troubleshooting

## 📊 Usage

**Quick workflow**: Download data → Run archive generator → Deploy

### Basic Example
```bash
# Generate archive (assumes .zst files in data/ directory)
python reddarc.py data/ \
  --subreddit privacy \
  --comments-file data/privacy_comments.zst \
  --submissions-file data/privacy_submissions.zst \
  --output output/

# Deploy with Docker
docker compose up -d
# Access at http://localhost
```

### Multi-Platform Support
- **Reddit**: `.zst` files from [Pushshift](https://academictorrents.com/details/3e3f64dee22dc304cdd2546254ca1f8e8ae542b4) (3.28TB, 2.38B posts)
- **Voat**: SQL dumps from [Archive.org](https://archive.org/details/voat-archive-2021) (15GB, 3.8M posts) - Use [pre-split files](tools/README_VOAT_SPLITTER.md) for 1000x speedup
- **Ruqqus**: `.7z` files from [Archive.org](https://archive.org/details/ruqqus-archive-2021) (752MB, 500K posts)

### Detailed Guides
- **[QUICKSTART.md](QUICKSTART.md)** - Step-by-step deployment (2-15 min)
- **[Scanner Tools](tools/README.md)** - Identify high-priority communities
- **[Installation Guide](docs/INSTALLATION.md)** - Detailed setup procedures
- **[Deployment Guides](#-additional-resources)** - Docker, Tor, Static hosting

**CLI options** and advanced workflows: See QUICKSTART.md for complete reference.

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

**Modular PostgreSQL-backed design** with 18 specialized HTML modules and multi-platform import support:

**Core Components:**
- `reddarc.py` - Main CLI entry point with platform auto-detection
- `core/` - PostgreSQL backend, streaming importers (Reddit/Voat/Ruqqus), HTML generation
- `api/` - REST API v1 with 30+ endpoints
- `mcp_server/` - MCP server for AI integration (29 tools)
- `html_modules/` - 18 specialized modules (Jinja2 rendering, SEO, statistics, CSS minification)
- `templates_jinja2/` - 15 Jinja2 templates with inheritance system
- `processing/` - Parallel user processing, batch optimization, statistics
- `monitoring/` - Performance tracking, auto-tuning, system optimization

**Key Features:**
- Streaming architecture with constant memory (4GB regardless of dataset size)
- PostgreSQL COPY protocol for 15K+ inserts/sec
- Keyset pagination for O(1) queries
- Resume capability with database checkpoints
- Multi-platform unified search with FTS GIN indexing

**Learn more**: [ARCHITECTURE.md](ARCHITECTURE.md) - Complete technical deep-dive


## 🌐 REST API & Search

**30+ REST API Endpoints** for programmatic access with MCP/AI optimization:
- **System** (5): Health checks, stats, schema, OpenAPI spec  
- **Posts** (13): List, single, comments, context, tree, related, random, aggregate, batch  
- **Comments** (7): List, single, random, aggregate, batch  
- **Users** (8): Profiles, summary, activity, aggregate, batch  
- **Subreddits** (4): List, statistics, summary  
- **Search** (3): Full-text search with Google-style operators, query debugging

**AI-Optimized Features**: Field selection, truncation controls, export formats (CSV/NDJSON), batch endpoints, context endpoints. Rate limited to 100 req/min.

**PostgreSQL Full-Text Search**: Lightning-fast GIN-indexed search with relevance ranking, highlighted excerpts, and advanced filters (subreddit, author, date, score). Sub-second results for large datasets.

**Instance Registry**: Distributed leaderboard system for tracking archive instances. Configure metadata, automate scoring, group teams for coordinated archiving.

**Learn more**: [API Documentation](docs/API.md) · [Search Setup](docs/SEARCH.md) · [Registry Guide](docs/REGISTRY_SETUP.md)


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

---

## 🚨 Get Involved: Help Preserve Internet History

Internet content disappears every day. Communities get banned, platforms shut down, and valuable discussions vanish. **You can help prevent this.**

### 📥 Download & Mirror Data Now

**Don't wait for content to disappear.** Download these datasets today:

| Platform | Size | Posts | Download |
|----------|------|-------|----------|
| **Reddit** | 3.28TB | 2.38B posts | [Academic Torrents](https://academictorrents.com/details/3e3f64dee22dc304cdd2546254ca1f8e8ae542b4) · [Magnet Link](magnet:?xt=urn:btih:3e3f64dee22dc304cdd2546254ca1f8e8ae542b4&tr=https%3A%2F%2Facademictorrents.com%2Fannounce.php&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce) |
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

## 📚 Additional Resources

### Deployment Guides
- **[Docker Deployment Guide](docker/README.md)** - Complete Docker setup including PostgreSQL, nginx, HTTPS, and Tor
- **[Tor Deployment Guide](docs/TOR_DEPLOYMENT.md)** - Tor hidden service setup for homelab and privacy deployments
- **[Static Deployment Guide](docs/STATIC_DEPLOYMENT.md)** - GitHub Pages and Codeberg Pages deployment (browse-only, no search)

### Technical Guides
- **[Installation Guide](docs/INSTALLATION.md)** - Detailed installation procedures (Docker, Ubuntu/Debian, macOS, Windows WSL2)
- **[Search Setup](docs/SEARCH.md)** - PostgreSQL full-text search configuration and usage
- **[Performance Guide](docs/PERFORMANCE.md)** - Memory usage, storage calculations, and tuning
- **[Scaling Guide](docs/SCALING.md)** - Horizontal scaling for large archives (multi-instance deployments)

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

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=19-84/redd-archiver&type=Date)](https://star-history.com/#19-84/redd-archiver&Date)

---

This software is provided "as is" under the Unlicense. See [LICENSE](LICENSE) for details. Users are responsible for compliance with applicable laws and terms of service when processing data.
