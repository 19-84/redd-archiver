# Frequently Asked Questions

Quick answers to common questions. For detailed guides, see [Documentation Hub](../README.md#documentation).

[Home](../README.md) | [Docs](../README.md#documentation) | [Troubleshooting](TROUBLESHOOTING.md)

---

## Table of Contents

- [Setup & Deployment](#setup--deployment)
- [Usage](#usage)
- [Data Sources](#data-sources)
- [Performance](#performance)
- [Advanced](#advanced)

---

## Setup & Deployment

### Q1: Getting 'Connection refused' when connecting to PostgreSQL

**Quick Answer:** Password mismatch in `.env` file.

**Solution:** Ensure password matches in BOTH places:
```bash
POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD
DATABASE_URL=postgresql://reddarchiver:YOUR_SECURE_PASSWORD@/reddarchiver?host=/var/run/postgresql
```

The password must be identical in `POSTGRES_PASSWORD` and in the `DATABASE_URL` connection string.

**Common causes:**
- Forgot to change default password in `.env`
- Changed password in one place but not the other
- PostgreSQL container not healthy yet (wait 30 seconds after `docker compose up`)

**See also:** [TROUBLESHOOTING.md - Database Connection Problems](TROUBLESHOOTING.md#database-connection-problems)

---

### Q2: Do I need a domain name to deploy Redd-Archiver?

**Quick Answer:** NO for Tor or local testing. YES only for public HTTPS.

| Deployment Mode | Domain Needed? | Time | Cost | Port Forwarding? |
|----------------|----------------|------|------|------------------|
| Tor Hidden Service | ❌ No | 2 min | $0/year | ❌ No |
| Local Testing | ❌ No | 5 min | $0 | ❌ No |
| Production HTTPS | ✅ Yes | 15 min | $10-15/year | ✅ Yes |
| Dual-Mode (HTTPS + Tor) | ✅ Yes | 17 min | $10-15/year | ✅ Yes |

**Why Tor is perfect for homelabs:**
- No domain registration or DNS configuration
- No port forwarding or router configuration
- Works behind CGNAT (restrictive ISPs)
- Share .onion address privately via email/chat
- Perfect for banned/quarantined subreddit archives

**See also:** 
- [TOR_DEPLOYMENT.md](TOR_DEPLOYMENT.md) - Complete Tor guide
- [QUICKSTART.md - Choose Your Deployment](../QUICKSTART.md#choose-your-deployment) - All modes comparison

---

### Q3: How do I deploy to Tor without a domain name or port forwarding?

**Quick Answer:** Use Tor profile - takes 2 minutes, zero networking config.

**Copy-paste deployment:**
```bash
# 1. Clone and setup
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD

# 2. Deploy with Tor
docker compose --profile tor up -d

# 3. Get your .onion address (wait 30 seconds)
cat tor-hidden-service/hostname
# Example output: abc123def456ghi789.onion
```

Share the `.onion` address with anyone who should access your archive. They need Tor Browser to visit it.

**Perfect for:**
- Homelab Reddit archive hosting
- Sharing banned subreddit archives privately
- Distributing backups to community members
- Research on controversial communities
- Testing before setting up HTTPS

**See also:** [QUICKSTART.md - Tor Homelab Deployment](../QUICKSTART.md#tor-homelab-deployment-2-minutes)

---

### Q4: I see 403 Forbidden when visiting my archive

**Quick Answer:** You haven't generated an archive yet - only deployed the infrastructure.

**Solution:**
```bash
# Generate your first archive
docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst
```

**Common causes:**
1. **No archive generated yet** (most common) - Run the command above
2. **Permissions issue** - Run `chmod 644 output/index.html`
3. **Empty output directory** - Check `ls -la output/` shows HTML files

**See also:** [QUICKSTART.md - Testing With Example Data](../QUICKSTART.md#testing-with-example-data)

---

### Q5: How do I get Let's Encrypt certificates working?

**Quick Answer:** Run the automated setup script.

**Solution:**
```bash
# 1. Configure domain in .env
nano .env
# Set: DOMAIN=your-domain.com
#      CERTBOT_EMAIL=admin@example.com
#      CERTBOT_TEST_CERT=true  # Use staging first!

# 2. Run automated setup
sudo ./docker/scripts/init-letsencrypt.sh

# 3. If successful with staging, switch to production
# Edit .env: CERTBOT_TEST_CERT=false
docker compose --profile production down
docker compose --profile production up -d
```

**Requirements:**
- Domain name pointing to your server (A record)
- Ports 80 and 443 open in firewall
- No other services using ports 80/443

**Pro tip:** Always test with `CERTBOT_TEST_CERT=true` first to avoid rate limits (50 certs/week).

**See also:** [QUICKSTART.md - Production HTTPS](../QUICKSTART.md#production-https-15-minutes)

---

## Usage

### Q6: How do I add more than one subreddit to my archive?

**Quick Answer:** Two options - import multiple times, or use comma-separated lists (if data available).

**Option 1: Multiple imports → Single export (recommended)**
```bash
# Import subreddit 1
docker compose exec reddarchiver-builder python reddarc.py /data \
  --import-only \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst

# Import subreddit 2
docker compose exec reddarchiver-builder python reddarc.py /data \
  --import-only \
  --subreddit technology \
  --comments-file /data/Technology_comments.zst \
  --submissions-file /data/Technology_submissions.zst

# Generate HTML for all imported data
docker compose exec reddarchiver-builder python reddarc.py /data \
  --export-from-database \
  --output /output/
```

**Option 2: Comma-separated (if you have combined files)**
```bash
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit privacy,technology,linux \
  --comments-file /data/all_comments.zst \
  --submissions-file /data/all_submissions.zst \
  --output /output/
```

**See also:** [ARCHITECTURE.md - Import/Export Workflow](../ARCHITECTURE.md#data-flow)

---

### Q7: Can I archive Reddit, Voat, AND Ruqqus in the same archive?

**Quick Answer:** YES - all three platforms coexist in one PostgreSQL database.

**Example multi-platform archive:**
```bash
# Import Reddit
docker compose exec reddarchiver-builder python reddarc.py /data \
  --import-only \
  --subreddit privacy \
  --comments-file /data/reddit/Privacy_comments.zst \
  --submissions-file /data/reddit/Privacy_submissions.zst

# Import Voat (using pre-split files for speed)
docker compose exec reddarchiver-builder python reddarc.py /data/voat_split/submissions/ \
  --import-only \
  --platform voat \
  --subverse privacy \
  --comments-file /data/voat_split/comments/privacy_comments.sql.gz \
  --submissions-file /data/voat_split/submissions/privacy_submissions.sql.gz

# Import Ruqqus
docker compose exec reddarchiver-builder python reddarc.py /data/ruqqus/ \
  --import-only \
  --platform ruqqus \
  --guild privacy \
  --comments-file /data/ruqqus/comments.7z \
  --submissions-file /data/ruqqus/submissions.7z

# Generate unified HTML
docker compose exec reddarchiver-builder python reddarc.py /data \
  --export-from-database \
  --output /output/
```

**Features:**
- Each platform gets URL prefix: `/r/` (Reddit), `/v/` (Voat), `/g/` (Ruqqus)
- Search works across all platforms automatically
- Single unified homepage shows all content
- Browse by platform or search across all

**See also:** [README.md - Multi-Platform Support](../README.md#multi-platform-support)

---

### Q8: How do I use Voat data? The full dump takes 30+ minutes per subverse!

**Quick Answer:** Use pre-split files for 1000x speed improvement (2-5 minutes instead of 30+).

**Problem:** Full Voat SQL dumps are 1.8GB and must be parsed line-by-line to extract specific subverses.

**Solution:** Use pre-split files (already separated by subverse):
```bash
# Clone pre-split repository
git clone https://github.com/yourusername/voat-pre-split /data/voat_split

# Fast import (2-5 minutes)
docker compose exec reddarchiver-builder python reddarc.py /data/voat_split/submissions/ \
  --platform voat \
  --subverse privacy \
  --comments-file /data/voat_split/comments/privacy_comments.sql.gz \
  --submissions-file /data/voat_split/submissions/privacy_submissions.sql.gz \
  --output /output/
```

**Speed comparison:**
- Full dump: 30-45 minutes per subverse
- Pre-split files: 2-5 minutes per subverse
- **1000x faster!**

**See also:** [tools/README_VOAT_SPLITTER.md](../tools/README_VOAT_SPLITTER.md) - How to create pre-split files

---

### Q9: Do I need p7zip installed to process Ruqqus .7z files?

**Quick Answer:** NO - Docker image includes p7zip automatically. Local installs need it.

**Docker deployment:** p7zip is pre-installed in the container. Just use `--platform ruqqus`:
```bash
docker compose exec reddarchiver-builder python reddarc.py /data/ruqqus/ \
  --platform ruqqus \
  --guild technology \
  --comments-file /data/ruqqus/comments.7z \
  --submissions-file /data/ruqqus/submissions.7z \
  --output /output/
```

**Local installation (without Docker):**
```bash
# Ubuntu/Debian
sudo apt install p7zip-full

# macOS
brew install p7zip

# Verify
7z --version
```

**See also:** [README.md - Ruqqus Support](../README.md#multi-platform-support)

---

### Q10: How do I force a complete rebuild instead of resuming?

**Quick Answer:** Use `--force-rebuild` flag.

**Solution:**
```bash
docker compose exec reddarchiver-builder python reddarc.py /data \
  --force-rebuild \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst \
  --output /output/
```

**When to use:**
- Source data has changed
- Want to regenerate with different filters (`--min-score`, `--min-comments`)
- Database got corrupted
- Testing different configuration options

**Warning:** This clears the database and starts fresh. All previous import progress is lost.

**Alternative:** If you just want to regenerate HTML without re-importing data:
```bash
# Keep database, regenerate HTML only
docker compose exec reddarchiver-builder python reddarc.py /data \
  --export-from-database \
  --output /output/
```

**See also:** [ARCHITECTURE.md - Resume Capability](../ARCHITECTURE.md#key-architectural-principles)

---

## Data Sources

### Q11: Where do I download Reddit data? The Academic Torrents link seems huge (3.28TB)!

**Quick Answer:** You can download specific subreddits only, not the entire 3.28TB dataset.

**How Reddit data is organized:**
```
Pushshift Archive (3.28TB total)
├── Subreddit1_comments.zst
├── Subreddit1_submissions.zst
├── Subreddit2_comments.zst
├── Subreddit2_submissions.zst
└── ... (40,029 subreddits)
```

**Download specific subreddits:**
1. Open [Academic Torrents magnet link](magnet:?xt=urn:btih:1614740ac8c94505e4ecb9d88be8bed7b6afddd4)
2. In your torrent client, **deselect all files**
3. Search for your subreddit (e.g., "Privacy")
4. Select only: `Privacy_comments.zst` and `Privacy_submissions.zst`
5. Download (typically 100MB-2GB per subreddit)

**Example sizes:**
- Small subreddit (<10K posts): 50-200MB
- Medium subreddit (10K-50K posts): 200MB-1GB
- Large subreddit (>50K posts): 1GB-10GB
- r/AskReddit (huge): ~100GB

**Pro tip:** Use `--dry-run` flag to preview files before downloading:
```bash
# Shows what would be processed
python reddarc.py /data --dry-run --subreddit privacy
```

**See also:** [README.md - Data Sources](../README.md#data-sources)

---

### Q12: How do I know if my .zst files are valid before processing?

**Quick Answer:** Use `--dry-run` flag to preview without importing.

**Solution:**
```bash
docker compose exec reddarchiver-builder python reddarc.py /data \
  --dry-run \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst
```

**Output shows:**
- Discovered files and their sizes
- Estimated post/comment counts
- Compression format validation
- Platform detection

**No data is imported** - just validation and preview.

**Common issues detected:**
- Corrupted .zst files (incomplete downloads)
- Wrong file format (plain .json instead of .zst)
- Mismatched subreddit names
- Missing files

**See also:** [TROUBLESHOOTING.md - Import Errors](TROUBLESHOOTING.md#importprocessing-errors)

---

## Performance

### Q13: How long does it take to archive a typical subreddit?

**Quick Answer:** 5-30 minutes for most subreddits, depending on size.

**Time estimates:**

| Subreddit Size | Posts | Time | Hardware |
|---------------|-------|------|----------|
| Small | <10K | 5-10 min | 4 CPU, 8GB RAM, SSD |
| Medium | 10K-50K | 10-20 min | 4 CPU, 8GB RAM, SSD |
| Large | 50K-200K | 20-40 min | 8 CPU, 16GB RAM, SSD |
| Very Large | >200K | 1-2 hours | 8 CPU, 16GB RAM, SSD |

**Factors affecting speed:**
- **CPU cores**: More cores = faster parallel processing
- **RAM**: 16GB+ enables parallel user page generation
- **Storage**: SSD is 3-5x faster than HDD
- **Database connection**: Unix socket is 15-30% faster than TCP

**Real-world example (r/privacy - 45K posts):**
- Import phase: 8 minutes (15K posts/sec)
- HTML generation: 4 minutes
- **Total: 12 minutes**

**See also:** [ARCHITECTURE.md - Performance Architecture](../ARCHITECTURE.md#performance-architecture)

---

### Q14: Why is my archive generation slower than the baseline?

**Quick Answer:** Check database connection type, RAM, and storage.

**Common bottlenecks:**

1. **Using TCP instead of Unix socket** (15-30% slower)
   ```bash
   # In .env, use Unix socket:
   DATABASE_URL=postgresql://user:pass@/db?host=/var/run/postgresql
   # NOT: postgresql://user:pass@localhost:5432/db
   ```

2. **HDD instead of SSD** (3-5x slower)
   - Move data and output directories to SSD
   - Move PostgreSQL data directory to SSD

3. **Low RAM** (forces more disk I/O)
   ```bash
   # Check RAM usage
   docker stats
   
   # If RAM constrained, use:
   --no-user-pages  # Skip user pages (saves 40% memory)
   --memory-limit 4.0  # Set explicit limit
   ```

4. **Docker RAM limit too low**
   ```yaml
   # In docker-compose.yml, increase:
   services:
     postgres:
       deploy:
         resources:
           limits:
             memory: 4G  # Increase from 2G
   ```

5. **Network latency** (database on different machine)
   - Keep database and builder on same machine
   - Use Unix sockets if possible

**Monitor performance:**
```bash
# Watch import speed
docker compose logs -f reddarchiver-builder | grep "posts/sec"

# Check database connection
docker compose exec reddarchiver-builder python -c "import os; print(os.getenv('DATABASE_URL'))"
```

**See also:** [TROUBLESHOOTING.md - Performance Issues](TROUBLESHOOTING.md#performance-issues)

---

### Q15: How much RAM do I need? I only have 4GB.

**Quick Answer:** 4GB works with `--no-user-pages` flag. 8GB is optimal.

**RAM requirements:**

| RAM | Configuration | Limitations |
|-----|---------------|-------------|
| 4GB | `--no-user-pages --memory-limit 2.0` | No user pages, slower |
| 8GB | Default settings | Full functionality |
| 16GB+ | Parallel user pages | Fastest performance |

**4GB configuration:**
```bash
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst \
  --output /output/ \
  --no-user-pages \
  --memory-limit 2.0
```

**What `--no-user-pages` does:**
- Skips user profile page generation
- Reduces memory usage by ~40%
- Posts and comments still work normally
- User links lead to simple user list

**PostgreSQL memory tuning** (for 4GB systems):
```yaml
# In docker-compose.yml
services:
  postgres:
    command:
      - -c
      - shared_buffers=256MB  # Default: 1GB
      - -c
      - work_mem=16MB  # Default: 64MB
```

**See also:** [TROUBLESHOOTING.md - Memory Issues](TROUBLESHOOTING.md#memory-issues)

---

### Q16: My container keeps getting killed (OOM). How do I reduce memory usage?

**Quick Answer:** Reduce PostgreSQL settings and use `--no-user-pages`.

**Solution (all three steps):**

**Step 1: Reduce container memory limits**
```yaml
# In docker-compose.yml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 2G  # Reduce from 4G
```

**Step 2: Reduce PostgreSQL memory settings**
```yaml
# In docker-compose.yml
services:
  postgres:
    command:
      - -c
      - shared_buffers=512MB  # Reduce from 1GB
      - -c
      - work_mem=32MB  # Reduce from 64MB
      - -c
      - maintenance_work_mem=128MB  # Reduce from 256MB
      - -c
      - effective_cache_size=1GB  # Reduce from 4GB
```

**Step 3: Use memory-saving flags**
```bash
docker compose exec reddarchiver-builder python reddarc.py /data \
  --no-user-pages \
  --memory-limit 2.0 \
  --subreddit privacy \
  --comments-file /data/Privacy_comments.zst \
  --submissions-file /data/Privacy_submissions.zst \
  --output /output/
```

**Monitor memory:**
```bash
# Watch container memory
docker stats

# Check system memory
free -h

# Check OOM kills
dmesg | grep -i "killed process"
```

**Process one subreddit at a time** instead of multiple:
```bash
# Good (low memory)
./import_subreddit.sh privacy
./import_subreddit.sh technology
./import_subreddit.sh linux

# Bad (high memory)
./import_all.sh privacy,technology,linux
```

**See also:** [TROUBLESHOOTING.md - Memory Issues](TROUBLESHOOTING.md#memory-issues)

---

## Advanced

### Q17: I see permission errors with Tor hidden service keys

**Quick Answer:** Set correct ownership BEFORE starting Tor.

**Solution:**
```bash
# Create directory with correct permissions BEFORE docker compose up
mkdir -p tor-hidden-service
sudo chown 100:100 tor-hidden-service
sudo chmod 700 tor-hidden-service

# Now start Tor
docker compose --profile tor up -d
```

**Why this happens:**
- Tor container runs as UID 100 (debian-tor user)
- Requires 700 permissions on hidden service directory
- If directory created by Docker, it's owned by root
- Tor can't write keys → permission denied

**Fix existing installation:**
```bash
# Stop Tor
docker compose --profile tor down

# Fix permissions
sudo chown -R 100:100 tor-hidden-service
sudo chmod 700 tor-hidden-service

# Restart
docker compose --profile tor up -d
```

**See also:** [TOR_DEPLOYMENT.md - Troubleshooting](TOR_DEPLOYMENT.md#troubleshooting)

---

## See Also

- [QUICKSTART.md](../QUICKSTART.md) - Step-by-step deployment guide
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Detailed error solutions
- [ARCHITECTURE.md](../ARCHITECTURE.md) - How Redd-Archiver works
- [API Documentation](API.md) - REST API reference
- [README.md](../README.md) - Main documentation hub
