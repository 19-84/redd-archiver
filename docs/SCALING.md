[Home](../README.md) | [Docs](../README.md#documentation) | [Performance](PERFORMANCE.md) | [FAQ](FAQ.md)

---

# Scaling Guide

> **TL;DR:** Single instance handles hundreds of GB. For multi-terabyte collections, use horizontal scaling with multiple topic-based instances.

## Single Instance Limits

Redd-Archiver has been tested with archives up to **hundreds of gigabytes per instance**:

**Tested Scale**:
- Archive size: Hundreds of GB
- Memory usage: Constant 4GB RAM (regardless of dataset size)
- Database: PostgreSQL handles large datasets efficiently
- Search: Maintains sub-second performance with GIN indexes

**Optimal Single Instance**:
- Up to 500GB archive size
- Millions of posts/comments
- Thousands of communities
- Fast search across entire archive

---

## When to Scale Horizontally

Consider multiple instances when:
- Archive collection exceeds 500GB
- Search performance degrades
- Logical topic divisions exist (tech, gaming, science, etc.)
- Want to distribute load across multiple servers
- Need redundancy or geographic distribution

---

## Horizontal Scaling Strategy

Deploy **multiple instances divided by topic**:

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Instance 1     │     │  Instance 2     │     │  Instance 3     │
│  Technology     │     │  Gaming         │     │  Science        │
│  Communities    │     │  Communities    │     │  Communities    │
│                 │     │                 │     │                 │
│  PostgreSQL DB  │     │  PostgreSQL DB  │     │  PostgreSQL DB  │
│  Search Server  │     │  Search Server  │     │  Search Server  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Benefits

- **Efficient Search**: Each database stays manageable size
- **Distributed Load**: Parallel processing across instances
- **Topic Organization**: Logical grouping of related content
- **Independent Scaling**: Scale individual topics as needed
- **Fault Isolation**: One instance failure doesn't affect others

---

## Deployment Options

### Option 1: Single Server, Multiple Ports

Run multiple Docker Compose stacks on one machine:

```bash
# Instance 1: Technology (port 8080)
cd /archives/tech
docker compose up -d

# Instance 2: Gaming (port 8081)  
cd /archives/gaming
sed -i 's/8080:80/8081:80/' docker-compose.yml
docker compose up -d

# Instance 3: Science (port 8082)
cd /archives/science
sed -i 's/8080:80/8082:80/' docker-compose.yml
docker compose up -d
```

**Access**:
- Tech: http://localhost:8080
- Gaming: http://localhost:8081
- Science: http://localhost:8082

---

### Option 2: Multiple Servers

One instance per physical/virtual machine:

```
Server 1 (tech.archive.local):     Technology topics
Server 2 (gaming.archive.local):   Gaming topics
Server 3 (science.archive.local):  Science topics
```

**Benefits**: Better resource isolation, higher total capacity

---

### Option 3: Topic-Based Domains

Use separate domains or subdomains:

```
tech.yourdomain.com     → Technology instance
gaming.yourdomain.com   → Gaming instance
science.yourdomain.com  → Science instance
```

**Benefits**: Professional appearance, easy to remember, SEO-friendly

---

## Implementation Example

### Step 1: Plan Topic Division

```bash
# Analyze your archive
python tools/find_banned_subreddits.py /data --output analysis.json

# Group by topic
Technology: programming, linux, technology, coding, etc.
Gaming: gaming, games, pcgaming, etc.
Science: science, askscience, datascience, etc.
```

### Step 2: Deploy Multiple Instances

```bash
# Create separate directories
mkdir -p /archives/{tech,gaming,science}

# Copy project to each
cp -r redd-archiver /archives/tech/
cp -r redd-archiver /archives/gaming/
cp -r redd-archiver /archives/science/

# Configure each instance
cd /archives/tech && vim .env    # Set DOMAIN=tech.archive.com
cd /archives/gaming && vim .env  # Set DOMAIN=gaming.archive.com
cd /archives/science && vim .env # Set DOMAIN=science.archive.com

# Deploy each
cd /archives/tech && docker compose --profile production up -d
cd /archives/gaming && docker compose --profile production up -d
cd /archives/science && docker compose --profile production up -d
```

### Step 3: Archive Content to Each

```bash
# Archive tech communities to tech instance
cd /archives/tech
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit programming,linux,technology \
  --output /output/

# Archive gaming communities to gaming instance
cd /archives/gaming
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit gaming,games,pcgaming \
  --output /output/

# Archive science communities to science instance
cd /archives/science
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit science,askscience,datascience \
  --output /output/
```

---

## Registry Configuration

Register multiple instances with team grouping:

```bash
# Each instance configured with same team ID
REDDARCHIVER_TEAM_ID="myteam-archives"
REDDARCHIVER_SITE_NAME="Tech Archive"  # Different per instance
REDDARCHIVER_BASE_URL="https://tech.archive.com"
```

**Leaderboard**: All instances grouped under team, showing combined statistics.

See [REGISTRY_SETUP.md](REGISTRY_SETUP.md) for details.

---

## Monitoring Multiple Instances

Use centralized monitoring:

```bash
# Check all instances
for instance in tech gaming science; do
  echo "=== $instance ==="
  curl https://$instance.archive.com/health
done

# Database sizes
for instance in tech gaming science; do
  echo "=== $instance database ==="
  docker exec ${instance}_postgres_1 psql -U reddarchiver -c \
    "SELECT pg_size_pretty(pg_database_size('reddarchiver'));"
done
```

---

## See Also

- [PERFORMANCE.md](PERFORMANCE.md) - Performance tuning for single instances
- [Docker README](../docker/README.md) - Docker deployment guide
- [REGISTRY_SETUP.md](REGISTRY_SETUP.md) - Instance registry for teams
- [FAQ](FAQ.md) - Common questions

---

**Last Updated**: 2026-01-26
