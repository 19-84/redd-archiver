# Redd-Archiver Data Catalog

This document tracks all known data sources for archival platforms, both implemented and proposed by the community.

## Supported Platforms (Implemented)

Redd-Archiver currently supports the following platforms with full import/export functionality:

### Reddit (Pushshift Dataset)

**Status**: ✅ Fully Implemented

**Data Source**: [Pushshift Complete Dataset](https://academictorrents.com/details/1614740ac8c94505e4ecb9d88be8bed7b6afddd4)

**Details**:
- **Size**: 3.28TB (compressed)
- **Posts**: 2.38 billion posts
- **Communities**: 40,029 subreddits
- **Date Range**: Through December 31, 2024
- **Format**: .zst compressed JSON Lines
- **Download**: [Academic Torrents](https://academictorrents.com/details/1614740ac8c94505e4ecb9d88be8bed7b6afddd4) · [Magnet Link](magnet:?xt=urn:btih:1614740ac8c94505e4ecb9d88be8bed7b6afddd4&tr=https%3A%2F%2Facademictorrents.com%2Fannounce.php&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce)

**Importer**: [`core/importers/reddit_importer.py`](../core/importers/reddit_importer.py)

**Usage**: See [QUICKSTART.md](../QUICKSTART.md) and [README.md Usage Section](../README.md#-usage)

### Voat (Complete Archive)

**Status**: ✅ Fully Implemented

**Data Source**: [Voat Archive 2021](https://archive.org/details/voat-archive-2021)

**Details**:
- **Size**: ~15GB (SQL dumps)
- **Posts**: 3.81 million posts
- **Comments**: 24.1 million comments
- **Communities**: 22,585 subverses
- **Date Range**: 2013-2020 (complete platform lifespan)
- **Format**: SQL INSERT statements
- **Download**: [Archive.org](https://archive.org/details/voat-archive-2021)

**Importer**: [`core/importers/voat_importer.py`](../core/importers/voat_importer.py) + [`voat_sql_parser.py`](../core/importers/voat_sql_parser.py)

**Usage**: See [QUICKSTART.md](../QUICKSTART.md) and [README.md Usage Section](../README.md#-usage)

### Ruqqus (Complete Archive)

**Status**: ✅ Fully Implemented

**Data Source**: [Ruqqus Archive 2021](https://archive.org/details/ruqqus-archive-2021)

**Details**:
- **Size**: ~752MB (.7z archive)
- **Posts**: 500,619 posts
- **Communities**: 6,217 guilds
- **Date Range**: Platform lifespan through October 2021
- **Format**: .7z compressed JSON Lines
- **Download**: [Archive.org](https://archive.org/details/ruqqus-archive-2021)

**Importer**: [`core/importers/ruqqus_importer.py`](../core/importers/ruqqus_importer.py)

**Usage**: See [QUICKSTART.md](../QUICKSTART.md) and [README.md Usage Section](../README.md#-usage)

---

## Community Data Sources (Raw Data Submissions)

**Philosophy**: Raw data comes first. Before implementing support for new platforms, we need to collect and catalog the data sources themselves.

**Current Status**: No community data sources submitted yet.

**How it works**:
1. Community members submit data sources via [the template](../.github/ISSUE_TEMPLATE/submit-data-source.yml)
2. Data sources are cataloged here with download links and metadata
3. Once sufficient data is available, implementation is considered
4. Developers can pick up implementation when ready

### Platforms of Interest

These platforms are good candidates for data submission, but **we need the raw data first**:

**Lemmy** - Federated Reddit alternative (JSON API exports available)
**Hacker News** - 15+ years of technical discussions (BigQuery dataset exists)
**Lobsters** - Quality-focused link aggregator (database exports possible)
**Kbin** - Fediverse Reddit alternative (ActivityPub protocol)

**Don't see your platform?** Submit any link aggregator or discussion platform data source. We're interested in:
- Platform shutdown archives (high priority)
- Historical backups of at-risk communities
- Alternative dumps of existing platforms
- New link aggregator platforms

---

## How to Submit a Data Source

Found a dataset for a new platform or an alternative source for existing platforms?

**Submit it here**: [Submit Data Source Template](../.github/ISSUE_TEMPLATE/submit-data-source.yml)

**What we need**:
- Platform name and type
- Dataset size and post count
- Download links (direct, torrent, Archive.org, IPFS)
- Data format (JSON, SQL, CSV, etc.)
- Date range covered
- Platform status (active, shutdown, at-risk)
- Urgency level

**Processing workflow** (for maintainers): See [REGISTRY_WORKFLOW.md](../.github/REGISTRY_WORKFLOW.md#data-source-submissions)

---

## Alternative Sources for Existing Platforms

If you have alternative data sources for Reddit, Voat, or Ruqqus (e.g., newer dumps, mirrors, IPFS pins), please submit them via the template so the community can discover them.

---

## Data Preservation Best Practices

**For Data Submitters**:
- ✅ Host on Archive.org or Academic Torrents (permanent)
- ✅ Create torrents with multiple seeders
- ✅ Include checksums (SHA256) in descriptions
- ✅ Document data format and schema
- ✅ Include sample data for validation

**For Archivers**:
- ✅ Verify checksums before importing
- ✅ Store raw data before processing
- ✅ Keep backups of rare/at-risk content
- ✅ Seed torrents after downloading
- ✅ Document your archive in the registry

---

## Statistics

**Total Archived Data** (Implemented):
- **Posts**: 2,384,311,619 across all platforms
- **Communities**: 68,831 (40,029 subreddits + 22,585 subverses + 6,217 guilds)
- **Storage**: ~3.3TB compressed

**Last Updated**: January 2025

---

## Questions?

- **Submit a data source**: [Use the template](../.github/ISSUE_TEMPLATE/submit-data-source.yml)
- **Request platform support**: [Open a feature request](../.github/ISSUE_TEMPLATE/feature_request.md)
- **General questions**: [GitHub Discussions](https://github.com/19-84/redd-archiver/discussions)
