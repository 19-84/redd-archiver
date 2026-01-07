# Registry Setup Guide

This guide explains how to set up a registry to track multiple Redd Archiver instances.

## Overview

The registry system allows you to:
- Track multiple archive instances across teams
- Aggregate statistics (posts, comments, users)
- Generate public leaderboards
- Monitor instance health and uptime

## Repository Structure

Create a separate repository for your registry:

```
reddit-archive-registry/
├── instances/
│   ├── privacy-main.json
│   ├── privacy-archive.json
│   └── ... (one file per instance)
├── teams/
│   ├── privacy-advocates.json
│   └── ... (one file per team)
├── scripts/
│   └── update_leaderboard.py
├── leaderboard/
│   ├── index.html (generated)
│   └── stats.json (generated)
├── instances.json (master registry file)
└── README.md
```

## Master Registry File

Create `instances.json`:

```json
{
  "version": "1.0",
  "last_updated": "2025-01-23T12:00:00Z",
  "teams": [
    {
      "team_id": "privacy-advocates",
      "name": "Privacy Advocates Network",
      "description": "Preserving privacy-focused communities",
      "contact": {
        "website": "https://example.com",
        "matrix": "@privacy:matrix.org"
      }
    }
  ],
  "instances": [
    {
      "instance_id": "privacy-main",
      "name": "Privacy Archive",
      "team_id": "privacy-advocates",
      "maintainer": "github_username",
      "registered": "2024-01-15",
      "endpoints": {
        "clearnet": "https://archive.example.com",
        "tor": "http://abc123xyz.onion",
        "api": "https://archive.example.com/api/v1/stats"
      },
      "static_metadata": {
        "subreddits": [
          {"name": "privacy", "url": "/r/privacy/"}
        ],
        "hosting": "self-hosted"
      }
    }
  ]
}
```

## Registry Update Script

The leaderboard generator (`scripts/update_leaderboard.py`) has been enhanced with **multi-platform support** and **accurate coverage calculation**:

### Key Features

1. **Platform-Aware Deduplication**: Communities tracked as `(platform, name)` tuples to avoid double-counting
2. **Coverage Calculation**: Uses `platform_metrics.json` to calculate accurate coverage percentages per platform
3. **Multi-Platform Display**: Shows Reddit subreddits, Voat subverses, and Ruqqus guilds separately

### Platform Totals (as of Dec 2024)

| Platform | Total Communities | Total Posts |
|----------|------------------|-------------|
| Reddit | 40,029 subreddits | 2.38B posts |
| Voat | 22,585 subverses | 3.81M posts |
| Ruqqus | 6,217 guilds | 500K posts |
| **TOTAL** | **68,831 communities** | **2.384B posts** |

### Usage

```bash
# Install dependencies
pip install -r scripts/requirements-leaderboard.txt

# Generate leaderboard (uses tools/platform_metrics.json by default)
python scripts/update_leaderboard.py

# With custom paths
python scripts/update_leaderboard.py \
  --registry .github/instances.json \
  --output leaderboard/ \
  --platform-metrics tools/platform_metrics.json
```

### Output Files

The script generates three files in the output directory:

1. **LEADERBOARD.md** - Team rankings with scores and platform breakdown
2. **COVERAGE.md** - Global community coverage index (multi-platform)
3. **registry.json** - Updated registry with uptime tracking

### Leaderboard Features

- **Platform Coverage Table**: Shows archived vs available communities per platform (Reddit/Voat/Ruqqus)
- **Deduplication**: Communities tracked as (platform, name) tuples - no double-counting
- **Coverage Percentages**: Accurate % based on platform_metrics.json totals
- **Team Breakdown**: Platform-specific statistics for each team
- **At-Risk Tracking**: Identifies banned communities with low coverage

### Example Output

**LEADERBOARD.md** includes:

```markdown
## Platform Coverage (All Teams Combined)

| Platform | Archived Communities | Total Available | Coverage % |
|----------|---------------------|-----------------|------------|
| Reddit   | 50                  | 40,029          | 0.12%      |
| Voat     | 12                  | 22,585          | 0.05%      |
| Ruqqus   | 5                   | 6,217           | 0.08%      |
| **TOTAL**| **67**              | **68,831**      | **0.10%**  |

## Top Teams

| Rank | Team | Score | Instances | Communities | Posts | Comments | Users |
|------|------|-------|-----------|-------------|-------|----------|-------|
| 🥇   | Privacy Advocates | 5,234.5 | 2/2 | 45 (0.07%) | 1.2M | 15M | 125K |
```

**COVERAGE.md** includes platform-specific sections:

```markdown
## Reddit Communities

| Subreddit | Status | Best Coverage | Instances | Archive Links |
|-----------|--------|---------------|-----------|---------------|
| r/privacy | Active | 95.2%         | 2         | [Instance 1](...), [Instance 2](...) |

## Voat Communities

| Subverse | Status | Best Coverage | Instances | Archive Links |
|----------|--------|---------------|-----------|---------------|
| v/news   | Active | 100.0%        | 1         | [Instance A](...) |

## 🔴 Priority: At-Risk Content (Low Coverage)

| Community | Platform | Coverage | Instances | Urgency |
|-----------|----------|----------|-----------|---------|
| r/banned  | reddit   | 25.0%    | 1         | 🟠 High |
```
## Running the Registry

### Manual Update

```bash
# Install dependencies
pip install -r scripts/requirements-leaderboard.txt

# Run update (uses platform_metrics.json by default)
python scripts/update_leaderboard.py

# With custom platform metrics
python scripts/update_leaderboard.py --platform-metrics /path/to/platform_metrics.json
```

### Automated Updates (Cron)

```bash
# Edit crontab
crontab -e

# Add line (update every 6 hours):
0 */6 * * * cd /path/to/registry && python scripts/update_leaderboard.py
```

### Docker Setup

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install aiohttp
COPY scripts/ ./scripts/
COPY instances.json .
CMD ["python", "scripts/update_leaderboard.py"]
```

```bash
docker build -t registry-updater .
docker run -v $(pwd)/leaderboard:/app/leaderboard registry-updater
```

## Publishing the Leaderboard

### Option 1: GitHub Pages

```bash
# Update leaderboard
python scripts/update_leaderboard.py

# Commit and push
git add leaderboard/
git commit -m "chore: update leaderboard $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push origin main

# Enable GitHub Pages in repo settings (source: main branch, /leaderboard directory)
```

### Option 2: Static Hosting

```bash
# Copy to your server
rsync -av leaderboard/ user@server:/var/www/archive-network/

# Or use any static hosting:
# - Netlify: netlify deploy --dir=leaderboard
# - Cloudflare Pages: wrangler pages publish leaderboard
# - IPFS: ipfs add -r leaderboard
```

## Team Scoring Formula

The team score aggregates metrics across all team instances:

```python
score = (
    total_posts * 0.0001 +       # Content volume
    total_comments * 0.00001 +   # Engagement depth
    total_users * 0.001 +        # User coverage (NEW!)
    subreddit_count * 50 +       # Diversity
    online_instances * 500       # Infrastructure reliability
)
```

**Key Changes from Geographic Model**:
- ✅ **ADDED**: `total_users` metric (0.001x weight)
- ❌ **REMOVED**: Geographic location bonuses
- 📊 **Focus**: Content preservation over infrastructure distribution

## Maintenance Tasks

### Adding New Instances

1. User submits GitHub issue (via template)
2. Maintainer runs: `python .github/scripts/issue-to-registry.py --issue-number 123`
3. Verify instance is accessible
4. Commit JSON file to `instances/`
5. Next leaderboard update includes new instance

### Removing Offline Instances

If an instance has been offline for 30+ days:

1. Contact maintainer (via GitHub issue/email)
2. If no response, move to `instances/inactive/`
3. Update team's `archives` array if applicable

### Team Management

Teams are created when first member registers with a team name:

```json
{
  "team_id": "privacy-advocates",
  "name": "Privacy Advocates Network",
  "description": "Preserving privacy communities",
  "founded": "2025-01-23",
  "members": ["username1"],
  "archives": ["instance-id-1"]
}
```

New team members:
1. Add GitHub username to `members` array
2. Add their instance to `archives` array

## Troubleshooting

### Instance Not Appearing on Leaderboard

**Check**:
1. Is `/api/v1/stats` endpoint accessible?
2. Does it return valid JSON with required fields?
3. Is the instance in `instances.json`?
4. Has the leaderboard script run since registration?

### Team Score Seems Wrong

**Verify**:
1. All team instance APIs are responding
2. Team instances have correct `team_id` in their JSON
3. Stats API returns accurate numbers
4. Script completed without errors

---

## Future Enhancements

- **Uptime Tracking**: Store historical uptime data
- **Bandwidth Metrics**: Track data served (if available)
- **Content Verification**: Spot-check content integrity
- **Achievement System**: Badges for milestones
- **RSS Feed**: Notify when new instances register

---

For more information, see:
- [Redd Archiver Documentation](../README.md)
- [API Documentation](API.md)
- [Registry Workflow](.github/REGISTRY_WORKFLOW.md)
