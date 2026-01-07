# Scanner Tools Documentation

Community scanners help you identify high-priority communities for targeted archiving across Reddit, Voat, and Ruqqus platforms. This guide explains how to use the scanner tools, interpret results, and apply priority scores to your archiving strategy.

## Overview

The scanner tools analyze complete platform datasets to:
1. **Calculate archive priority scores (0-100)** for each community
2. **Track community statistics**: post counts, activity periods, deletion rates
3. **Identify at-risk communities**: restricted, quarantined, banned, or high-censorship
4. **Sort by importance**: Highest-priority communities listed first

## Available Scanners

| Platform | Scanner Tool | Input Format | Output File | Communities |
|----------|--------------|--------------|-------------|-------------|
| **Reddit** | `find_banned_subreddits.py` | .zst JSON Lines | `subreddits_complete.json` | 40,029 |
| **Voat** | `scan_voat_subverses.py` | SQL dumps (.sql.gz) | `subverses.json` | 22,637 |
| **Ruqqus** | `scan_ruqqus_guilds.py` | .7z archives | `guilds.json` | 6,217 |

## Quick Start

### Reddit Scanner

```bash
# Scan Reddit Pushshift data
python tools/find_banned_subreddits.py /path/to/reddit-data/ \
  --output tools/subreddits_complete.json \
  --cutoff-date 2024-10-01
```

**Processing time**: ~33 hours for full dataset (39,937 files, 2.38B posts)

**Output**: JSON file with 40,029 subreddits sorted by priority score

**Pre-generated data**: Complete scan results available in `tools/subreddits_complete.json` (46MB)

### Voat Scanner

```bash
# Scan Voat SQL dumps
python tools/scan_voat_subverses.py /path/to/voat-data/ \
  --output tools/subverses.json \
  --cutoff-date 2024-01-01
```

**Processing time**: ~10 minutes (3.8M posts from SQL dumps with proper parsing)

**Output**: JSON file with 22,637 Voat subverses sorted by priority score

**Pre-generated data**: Complete scan results available in `tools/subverses.json` (14MB)

### Ruqqus Scanner

```bash
# Scan Ruqqus .7z archives
python tools/scan_ruqqus_guilds.py /path/to/ruqqus-data/ \
  --output tools/guilds.json
```

**Processing time**: ~16 seconds (500K posts from .7z archives)

**Output**: JSON file with 6,217 guilds sorted by priority score

**Pre-generated data**: Complete scan results available in `tools/guilds.json` (3.6MB)

## Priority Scoring Algorithm

### Reddit Scoring (0-100 points)

**1. Research/Controversy (40 points)**
- Inactive/banned: 20 pts
- Quarantined: 15 pts
- Restricted/private: 10 pts
- High removal rate: 20 pts (scaled by removal %)
- Heavy moderation: 10 pts (scaled by locked %)

**2. Historical Value (30 points)**
- Subscriber count: 15 pts (capped at 100K+ subscribers)
- Post count: 10 pts (capped at 50K+ posts)
- Active period: 5 pts (capped at 2+ years)

**3. At-Risk Bonus (15 points)**
- Ever quarantined: 10 pts
- Ad restrictions: 5 pts

**4. Virality (10 points)**
- Crosspost count: 10 pts (capped at 1K+ crossposts)

**5. NSFW Non-Porn (5 points)**
- NSFW + high moderation: 5 pts (controversial topics, not pure porn)

### Voat Scoring (0-100 points)

**1. Status (40 points)**
- Inactive: 25 pts
- Restricted: 15 pts
- High deletion rate: 15 pts (scaled by deletion %)

**2. Historical Value (35 points)**
- Post count: 20 pts (capped at 10K+ posts)
- Active period: 15 pts (capped at 2+ years)

**3. At-Risk Bonus (15 points)**
- Adult content: 10 pts
- NSFW: 5 pts

**4. Content Diversity (10 points)**
- NSFW but not adult: 10 pts (controversial topics)

### Ruqqus Scoring (0-100 points)

**1. Platform Baseline (40 points)**
- All Ruqqus content: 40 pts (platform shutdown = inherently at-risk)

**2. Historical Value (40 points)**
- Post count: 25 pts (capped at 5K+ posts)
- Active period: 15 pts (capped at 1+ year)

**3. Content Markers (20 points)**
- Deletion rate: 10 pts (scaled by deletion %)
- NSFW content: 10 pts

## Output Format

### JSON Structure

```json
{
  "scan_metadata": {
    "scan_date": "2025-12-31T07:02:52.208306+00:00",
    "cutoff_date": "2024-10-01T00:00:00+00:00",
    "files_scanned": 39937,
    "total_posts_processed": 2380030458,
    "total_subreddits": 40029,
    "status_counts": {
      "restricted": 8642,
      "active": 26552,
      "inactive": 4803,
      "quarantined": 32
    },
    "processing_time_seconds": 120432
  },
  "subreddits": [
    {
      "subreddit": "conspiracy",
      "archive_priority_score": 60.47,
      "status": "restricted",
      "last_post_date": "2024-12-31T23:48:36+00:00",
      "total_posts_seen": 5158383,
      "removed_percentage": 23.2,
      "active_period_days": 6181
    }
  ]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `archive_priority_score` | 0-100 score (higher = more important to archive) |
| `status` | `active`, `restricted`, `inactive`, `quarantined` |
| `total_posts_seen` | Total posts in community |
| `removed_percentage` | % of posts deleted/removed |
| `active_period_days` | Days from first to last post |
| `last_post_date` | Most recent post timestamp |
| `max_subscribers` | Peak subscriber count (Reddit only) |

## Interpreting Results

### Priority Score Ranges

| Score Range | Priority | Description |
|-------------|----------|-------------|
| **70-100** | Critical | Highest priority - banned, quarantined, or massive communities |
| **50-69** | High | Important - restricted or high removal rates |
| **30-49** | Medium | Moderate - active with some controversy |
| **0-29** | Low | Standard - small or uncontroversial communities |

### Reddit Example: Top Priorities

```
1. r/AmItheAsshole      | Score: 73.20 | restricted | 2.5M posts | 18.5% removed
2. r/Cuckold            | Score: 72.06 | restricted | 608K posts | NSFW
3. r/conspiracy         | Score: 60.47 | restricted | 5.2M posts | 23.2% removed
```

### Ruqqus Example: Top Communities

```
1. +News                | 15,337 posts | inactive
2. +Conservative        | 14,677 posts | inactive
3. +Politics            | 12,896 posts | inactive
```

### Voat Example: Top Communities

```
1. v/QRV                | 213,392 posts | inactive
2. v/news               | 235,779 posts | inactive
3. v/politics           | 200,002 posts | inactive
4. v/whatever           | 252,623 posts | inactive
```

## Use Cases

### 1. Targeted Archiving

Archive high-risk communities first before they disappear:

```bash
# Extract top 100 restricted subreddits
jq '.subreddits[] | select(.status == "restricted") | .subreddit' \
  tools/subreddits_complete.json | head -100 > priority_list.txt

# Archive them
for sub in $(cat priority_list.txt); do
  python reddarc.py /data --subreddit "$sub" --output archive/
done
```

### 2. Storage Planning

Identify largest communities before downloading:

```bash
# Top 20 by post count
jq -r '.subreddits | sort_by(.total_posts_seen) | reverse | .[0:20] |
  .[] | "\(.total_posts_seen)\t\(.subreddit)"' \
  tools/subreddits_complete.json
```

### 3. Historical Research

Find communities with high censorship:

```bash
# Subreddits with >30% removal rate
jq -r '.subreddits[] | select(.removed_percentage > 30) |
  "\(.archive_priority_score)\t\(.subreddit)\t\(.removed_percentage)%"' \
  tools/subreddits_complete.json | sort -rn
```

## Performance Notes

### Memory Usage

- **Reddit scanner**: ~2GB RAM (streaming architecture)
- **Voat scanner**: ~500MB RAM (SQL parsing)
- **Ruqqus scanner**: ~200MB RAM (JSON Lines streaming)

### Processing Time

| Dataset | Files | Posts | Time | Speed |
|---------|-------|-------|------|-------|
| Reddit (full) | 39,937 | 2.38B | 33.5 hours | 19,700 posts/sec |
| Voat (complete) | 1 | 3.81M | ~10 min | 6,300 posts/sec |
| Ruqqus (complete) | 1 | 500K | 16 sec | 31,000 posts/sec |

### Resumable Processing

**Reddit scanner only** supports checkpointing for interrupted scans:

```bash
# Resume interrupted scan
python tools/find_banned_subreddits.py /data --output tools/subreddits.json --resume
```

## Advanced Options

### Reddit Scanner

```bash
python tools/find_banned_subreddits.py /data \
  --output tools/subreddits.json \
  --cutoff-date 2024-10-01 \     # Inactive detection threshold
  --workers 9 \                   # Parallel workers (default: CPU count)
  --checkpoint-interval 100       # Checkpoint every N files
```

### Voat Scanner

```bash
python tools/scan_voat_subverses.py /data \
  --output tools/subverses.json \
  --cutoff-date 2024-01-01        # Inactive detection threshold
```

### Ruqqus Scanner

```bash
python tools/scan_ruqqus_guilds.py /data \
  --output tools/guilds.json
# No cutoff date needed (platform shutdown Oct 2021)
```

## Integration with Redd-Archiver

Use scanner results to target specific communities:

```bash
# Extract top 10 priority subreddits to a list
jq -r '.subreddits[0:10] | .[] | .subreddit' \
  tools/subreddits_complete.json > top10.txt

# Archive them
python reddarc.py /data \
  --subreddit $(cat top10.txt | tr '\n' ',') \
  --output priority-archive/
```

## Troubleshooting

### Scanner runs out of memory

Reddit scanner uses streaming - this shouldn't happen. For Voat/Ruqqus:
- Check available RAM (requires 500MB+ free)
- Close other applications
- Process smaller datasets

### SQL parsing errors (Voat)

```bash
# Check SQL file integrity
gunzip -c /data/voat/submission.sql.gz | head -100
```

### 7z extraction errors (Ruqqus)

```bash
# Verify 7z is installed
7z --help

# Test archive integrity
7z t /data/ruqqus/submissions.7z
```

### Bad lines reported

All scanners track `bad_lines` count. Small numbers (<0.1%) are normal due to:
- Malformed JSON in source data
- Encoding issues in SQL dumps
- Corrupted archive entries

## See Also

- [QUICKSTART.md](../QUICKSTART.md) - Basic archiving guide
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Technical details
- [API.md](API.md) - REST API for querying archives
