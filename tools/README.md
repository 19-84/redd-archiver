# Data Catalog & Scanner Tools

This directory contains **pre-generated community catalogs** and **scanner tools** for all three supported platforms. Use these resources to identify high-priority communities for targeted archiving.

## 📊 Data Catalog (Pre-Generated)

Complete scan results from full platform datasets:

| File | Platform | Communities | Posts Scanned | Size | Last Updated |
|------|----------|-------------|---------------|------|--------------|
| `subreddits_complete.json` | Reddit | 40,029 | 2.38B | 46MB | Dec 2024 |
| `subverses.json` | Voat | 22,585 | 3.81M | 14MB | Dec 2024 |
| `guilds.json` | Ruqqus | 6,217 | 500K | 3.6MB | Dec 2024 |

**Total**: 68,831 communities cataloged across all platforms

### What's Included

Each catalog file contains:
- **Archive priority scores** (0-100) for every community
- **Post counts** and activity periods
- **Status tracking** (active, restricted, inactive, quarantined)
- **Deletion/removal statistics**
- **NSFW/adult content percentages**
- **Subscriber counts** (Reddit only)

### How to Use the Catalogs

**Browse top priorities**:
```bash
# Top 20 Reddit subreddits
jq -r '.subreddits[0:20] | .[] | "\(.archive_priority_score)\t\(.subreddit)\t\(.total_posts_seen)"' \
  tools/subreddits_complete.json

# Top 20 Voat subverses
jq -r '.subverses[0:20] | .[] | "\(.archive_priority_score)\tv/\(.subverse)\t\(.total_posts_seen)"' \
  tools/subverses.json

# Top 20 Ruqqus guilds
jq -r '.guilds[0:20] | .[] | "\(.archive_priority_score)\t+\(.guild)\t\(.total_posts_seen)"' \
  tools/guilds.json
```

**Filter by status**:
```bash
# Reddit restricted subreddits only
jq -r '.subreddits[] | select(.status == "restricted") | .subreddit' \
  tools/subreddits_complete.json

# Voat inactive subverses
jq -r '.subverses[] | select(.status == "inactive") | .subverse' \
  tools/subverses.json
```

**Find specific communities**:
```bash
# Search Reddit for "privacy"
jq -r '.subreddits[] | select(.subreddit | contains("privacy")) |
  "\(.subreddit) - \(.total_posts_seen) posts"' \
  tools/subreddits_complete.json

# Check if v/technology exists
jq -r '.subverses[] | select(.subverse == "technology")' tools/subverses.json
```

**Filter by size**:
```bash
# Subreddits with 100K+ posts
jq -r '.subreddits[] | select(.total_posts_seen > 100000) |
  "\(.subreddit): \(.total_posts_seen) posts"' \
  tools/subreddits_complete.json
```

## 🔧 Scanner Tools

Re-generate catalogs or scan your own data:

### Reddit Scanner

```bash
python tools/find_banned_subreddits.py /path/to/reddit-data/ \
  --output tools/subreddits_complete.json \
  --cutoff-date 2024-10-01
```

**Features**:
- Streams 4TB+ of .zst files with minimal memory
- Parallel processing (multi-core)
- Resumable checkpointing
- Processing time: ~33 hours for full dataset

### Voat Scanner

```bash
python tools/scan_voat_subverses.py /path/to/voat-data/ \
  --output tools/subverses.json \
  --cutoff-date 2024-01-01
```

**Features**:
- Proper SQL parser with quoted string handling
- Handles 3.8M posts from SQL dumps
- Processing time: ~10 minutes

### Ruqqus Scanner

```bash
python tools/scan_ruqqus_guilds.py /path/to/ruqqus-data/ \
  --output tools/guilds.json
```

**Features**:
- Streams .7z archives with 7z command-line tool
- JSON Lines parsing with orjson
- Processing time: ~16 seconds

### Platform Metrics Aggregator

```bash
python tools/calculate_platform_metrics.py --all
```

Aggregates totals from all three scanners into `platform_metrics.json`.

## 📖 Examples

### Example 1: Archive Top 10 Reddit Subreddits by Priority

```bash
# Extract top 10
jq -r '.subreddits[0:10] | .[] | .subreddit' \
  tools/subreddits_complete.json > top10.txt

# Archive them
python reddarc.py /data \
  --subreddit $(cat top10.txt | tr '\n' ',') \
  --output priority-archive/
```

### Example 2: Archive All Restricted Reddit Subreddits

```bash
# Get list of restricted subreddits
jq -r '.subreddits[] | select(.status == "restricted") | .subreddit' \
  tools/subreddits_complete.json > restricted.txt

# Count them
wc -l restricted.txt  # 8,642 subreddits

# Archive subset (first 100)
head -100 restricted.txt | tr '\n' ',' | xargs -I {} \
  python reddarc.py /data --subreddit {} --output restricted-archive/
```

### Example 3: Find Largest Voat Communities

```bash
# Sort by post count
jq -r '.subverses | sort_by(.total_posts_seen) | reverse | .[0:20] |
  .[] | "\(.subverse)\t\(.total_posts_seen)\t\(.status)"' \
  tools/subverses.json
```

Output:
```
whatever    252,623    inactive
news        235,779    inactive
QRV         213,392    inactive
politics    200,002    inactive
```

### Example 4: Archive All Ruqqus Content (Small Dataset)

```bash
# Ruqqus is small enough to archive completely
python reddarc.py /ruqqus-data/ --output ruqqus-archive/
```

## 🎯 Archive Planning Strategies

### Strategy 1: Priority-Based

Archive highest-scoring communities first (at-risk content):

1. Extract top N by priority score from each platform
2. Archive restricted/quarantined communities first
3. Move to high-activity communities next

### Strategy 2: Size-Based

Archive largest communities for maximum content preservation:

1. Sort by `total_posts_seen` descending
2. Archive top 100 communities per platform
3. Covers majority of content with minimal communities

### Strategy 3: Topic-Based

Target specific topics across all platforms:

```bash
# Find all privacy-related communities
jq -r '.subreddits[] | select(.subreddit | test("privacy|surveillance|crypto"; "i")) | .subreddit' \
  tools/subreddits_complete.json

jq -r '.subverses[] | select(.subverse | test("privacy|surveillance|crypto"; "i")) | .subverse' \
  tools/subverses.json

jq -r '.guilds[] | select(.guild | test("privacy|surveillance|crypto"; "i")) | .guild' \
  tools/guilds.json
```

### Strategy 4: NSFW Content Preservation

Archive adult/NSFW communities before potential removal:

```bash
# Reddit NSFW subreddits
jq -r '.subreddits[] | select(.is_nsfw == true) | .subreddit' \
  tools/subreddits_complete.json

# Voat adult subverses
jq -r '.subverses[] | select(.is_adult == true) | .subverse' \
  tools/subverses.json
```

## 📈 Statistics

### Reddit Dataset

- **40,029 subreddits** from 39,937 .zst files
- **2.38 billion posts** processed
- **Status**: 26,552 active, 8,642 restricted, 4,803 inactive, 32 quarantined
- **Date range**: Through December 31, 2024

### Voat Dataset

- **22,585 subverses** from complete SQL archive
- **3.81 million posts** processed
- **Status**: All inactive (platform shutdown)
- **Date range**: 2013-2020 (Voat lifespan)

**Top 5 by Post Count**:
1. v/whatever (252,623 posts)
2. v/news (235,779 posts)
3. v/QRV (213,392 posts)
4. v/politics (200,002 posts)
5. v/GreatAwakening (113,802 posts)

### Ruqqus Dataset

- **6,217 guilds** from shutdown archive
- **500,619 posts** processed
- **Status**: All inactive (platform shutdown Oct 2021)
- **Date range**: Platform lifespan through Oct 2021

**Top 5 by Post Count**:
1. +News (15,337 posts)
2. +Conservative (14,677 posts)
3. +Politics (12,896 posts)
4. +Conservatives (8,313 posts)
5. +OccidentalEnclave (8,188 posts)

## 🔍 Data Quality

All scanners track data quality metrics:

| Scanner | Posts Processed | Bad Lines | Accuracy |
|---------|----------------|-----------|----------|
| Reddit | 2,380,030,458 | 0 | 100.0% |
| Voat | 3,813,216 | 1 | 99.99997% |
| Ruqqus | 500,619 | Unknown | ~100% |

"Bad lines" represent unparseable records - extremely rare in practice.

## 🚀 Quick Start

**Browse the catalog without running scanners**:

```bash
# View Reddit catalog structure
jq '.scan_metadata' tools/subreddits_complete.json

# Count communities by status
jq '.subreddits | group_by(.status) | map({status: .[0].status, count: length})' \
  tools/subreddits_complete.json

# Find communities with specific keywords
jq -r '.subreddits[] | select(.subreddit | contains("tech")) |
  "\(.subreddit) - \(.total_posts_seen) posts"' \
  tools/subreddits_complete.json | head -20
```

## 📚 See Also

- [SCANNER_TOOLS.md](../docs/SCANNER_TOOLS.md) - Complete scanner documentation
- [QUICKSTART.md](../QUICKSTART.md) - Archive generation guide
- [REGISTRY_SETUP.md](../docs/REGISTRY_SETUP.md) - Leaderboard with coverage tracking
