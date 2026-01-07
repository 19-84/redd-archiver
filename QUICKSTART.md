# Redd-Archiver Quick Start Guide

⏱️ **Get running in 2-15 minutes depending on deployment mode**

This guide provides copy-paste-friendly instructions for deploying redd-archiver. Choose your deployment mode below and follow the steps.

---

## Prerequisites Check

Run these commands to verify your system is ready:

```bash
# Check Docker version (need 24.0+)
docker --version

# Check Docker Compose version (need v2.0+)
docker compose version

# Check available ports
sudo lsof -i :80  # Should be empty
sudo lsof -i :443 # Should be empty (for HTTPS)
sudo lsof -i :5432 # Should be empty
```

---

## Choose Your Deployment

> **📌 Important Note**: Redd-Archiver supports two modes:
> - **Offline Browsing**: Generated HTML files work without a server (browse via sorted index pages, no search)
> - **Server Deployment** (below): Required for full-text search functionality (PostgreSQL FTS)
>
> See [Deployment Options](README.md#-deployment-options) for complete comparison.

| Mode | Time | Prerequisites | Use Case | Search |
|------|------|---------------|----------|--------|
| [Local Testing](#local-testing-5-minutes) | 5 min | Docker only | Development, testing | ✅ Yes |
| [Tor Homelab](#tor-homelab-deployment-2-minutes) | 2 min | Docker only | Share archives privately, no networking config | ✅ Yes |
| [Production HTTPS](#production-https-15-minutes) | 15 min | Docker + Domain + DNS | Public archives | ✅ Yes |
| [Dual-Mode](#dual-mode-https--tor) | 17 min | Docker + Domain + DNS | Public + private access | ✅ Yes |

---

## Local Testing (5 Minutes)

Perfect for trying out redd-archiver on your local machine.

### Step 1: Clone and Configure (2 minutes)

```bash
# Clone repository
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver

# Create environment file
cp .env.example .env

# Edit configuration (change YOUR_SECURE_PASSWORD)
nano .env
```

**Required changes in .env**:
```bash
# Change the password in BOTH places:
POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD
DATABASE_URL=postgresql://reddarchiver:YOUR_SECURE_PASSWORD@/reddarchiver?host=/var/run/postgresql
```

**Important**: The password must match in both `POSTGRES_PASSWORD` and `DATABASE_URL`!

### Step 2: Start Services (2 minutes)

```bash
# Start all services
docker compose up -d

# Wait for services to become healthy
sleep 30

# Verify services are running
docker compose ps
# All services should show "healthy"
```

### Step 3: Verify Installation (1 minute)

```bash
# Test nginx
curl http://localhost/health
# Expected: OK

# Test search server
curl http://localhost:5000/health
# Expected: {"status":"healthy"}

# Test database connection
docker compose exec postgres pg_isready -U reddarchiver
# Expected: reddarchiver:5432 - accepting connections

# Visit in browser (will show placeholder until archive generated)
# Open: http://localhost/
# Expected: "Redd-Archiver Deployment Successful" page
```

**Note**: You'll see a placeholder page until you generate an archive (Step 4).

### Where to Get Data Files

Redd-Archiver processes data dumps from multiple platforms:

| Platform | Format | Data Sources |
|----------|--------|--------------|
| **Reddit** | .zst JSON Lines | [Pushshift Complete Dataset](https://academictorrents.com/details/1614740ac8c94505e4ecb9d88be8bed7b6afddd4) (magnet link below) |
| **Voat** | SQL dumps | [Voat Archive 2021](https://archive.org/details/voat-archive-2021) (22,637 subverses, 3.8M posts, 24M comments) |
| **Ruqqus** | .7z JSON Lines | [Ruqqus Archive 2021](https://archive.org/details/ruqqus-archive-2021) (6,217 guilds, complete archive) |

**Reddit Magnet Link**:
```
magnet:?xt=urn:btih:1614740ac8c94505e4ecb9d88be8bed7b6afddd4&tr=https%3A%2F%2Facademictorrents.com%2Fannounce.php&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce
```
Size: 3.28 TB compressed (2005-06 through 2024-12) | Content: 2.38B posts, 40K subreddits

Place downloaded files in the `./data/` directory before running Step 4.

**Platform Auto-Detection**: Redd-Archiver automatically detects the platform from file extensions:
- `.zst` → Reddit (Pushshift format)
- `.sql` / `.sql.gz` → Voat (SQL dumps)
- `.7z` → Ruqqus (JSON Lines)

### Step 4: Generate Your First Archive (Required for Content)

**Reddit (.zst files):**
```bash
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit YOUR_SUBREDDIT_NAME \
  --comments-file /data/YOUR_SUBREDDIT_comments.zst \
  --submissions-file /data/YOUR_SUBREDDIT_submissions.zst \
  --output /output/ \
  --min-score 5 \
  --min-comments 2
```

**Voat (SQL dumps):**

*Option 1: Using Pre-Split Files (Recommended - 2-5 minutes)*
```bash
# Import from pre-split Voat files (1000x faster than full dump)
docker compose exec reddarchiver-builder python reddarc.py /data/voat_split/submissions/ \
  --subverse privacy \
  --comments-file /data/voat_split/comments/privacy_comments.sql.gz \
  --submissions-file /data/voat_split/submissions/privacy_submissions.sql.gz \
  --platform voat \
  --output /output/ \
  --import-only

# Generate HTML
docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --export-from-database
```

> **💡 Tip**: Pre-split files import in 2-5 minutes vs 30+ minutes for full dump. See [Voat Splitter Tool](tools/README_VOAT_SPLITTER.md) for details.

*Option 2: Full Dump (Slower - imports all subverses)*
```bash
# Import from complete Voat dump (scans all 22,637 subverses)
docker compose exec reddarchiver-builder python reddarc.py /data/voat/ \
  --subverse voatdev,pics \
  --output /output/ \
  --import-only
```

**Ruqqus (.7z files):**
```bash
# Import Ruqqus data (p7zip included in Docker - no manual setup required)
docker compose exec reddarchiver-builder python reddarc.py /data/ruqqus/ \
  --guild technology \
  --comments-file /data/ruqqus/comments.fx.2021-10-30.txt.sort.2021-11-08.7z \
  --submissions-file /data/ruqqus/submissions.f1.2021-10-30.txt.sort.2021-11-10.7z \
  --platform ruqqus \
  --output /output/ \
  --import-only

# Generate HTML
docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --export-from-database
```

> **📦 Note**: Docker image includes p7zip for .7z decompression. Explicit file paths ensure correct files are used.

**Multi-Platform Archive (all three platforms):**
```bash
# Import Reddit
docker compose exec reddarchiver-builder python reddarc.py /data/reddit/ \
  --subreddit banned \
  --comments-file /data/reddit/banned_comments.zst \
  --submissions-file /data/reddit/banned_submissions.zst \
  --output /output/multi-platform/ \
  --import-only

# Import Voat (pre-split recommended)
docker compose exec reddarchiver-builder python reddarc.py /data/voat_split/submissions/ \
  --subverse privacy \
  --comments-file /data/voat_split/comments/privacy_comments.sql.gz \
  --submissions-file /data/voat_split/submissions/privacy_submissions.sql.gz \
  --platform voat \
  --output /output/multi-platform/ \
  --import-only

# Import Ruqqus
docker compose exec reddarchiver-builder python reddarc.py /data/ruqqus/ \
  --guild technology \
  --comments-file /data/ruqqus/comments.fx.2021-10-30.txt.sort.2021-11-08.7z \
  --submissions-file /data/ruqqus/submissions.f1.2021-10-30.txt.sort.2021-11-10.7z \
  --platform ruqqus \
  --output /output/multi-platform/ \
  --import-only

# Export unified HTML archive with all three platforms
docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/multi-platform/ \
  --export-from-database \
  --base-url https://archive.example.com \
  --site-name "Multi-Platform Archive"
```

> **🌐 Multi-Platform**: All three platforms coexist in one PostgreSQL database. Search works across all platforms with correct prefixes (r/, v/, g/).

### Success Criteria
- ✅ http://localhost/health returns "OK"
- ✅ http://localhost/ shows placeholder page (before archive generation)
- ✅ All containers showing "healthy" status
- ✅ After Step 4: Dashboard with subreddit(s) visible

---

## Tor Homelab Deployment (2 Minutes)

**Perfect for**: Sharing archives privately without port forwarding, domain names, or internet exposure.

### Why Tor?
- ✅ No port forwarding or router configuration
- ✅ No domain name purchase ($0/year saved)
- ✅ Works behind CGNAT and restrictive ISPs
- ✅ Share with friends securely via .onion address

### Step 1: Start Tor-Only Mode (1 minute)

```bash
# Clone and configure (same as Local Testing Step 1)
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver
cp .env.example .env
nano .env  # Change POSTGRES_PASSWORD

# Start with Tor profile
docker compose -f docker-compose.yml -f docker-compose.tor-only.yml --profile tor up -d
```

### Step 2: Get Your .onion Address (1 minute)

```bash
# Wait for Tor to generate keys
sleep 60

# Display your .onion address
docker compose logs tor | grep "Your .onion address"

# Or read directly from file
cat tor-hidden-service/hostname
```

Example output:
```
abcdefghijklmnopqrstuvwxyz1234567890abcdefghijklmnopqr.onion
```

**Important**: The .onion address will show a placeholder page until you generate an archive (see Step 5 below).

### Step 3: Access Via Tor Browser

1. Download Tor Browser: https://www.torproject.org/download/
2. Open Tor Browser
3. Visit: `http://YOUR_ONION_ADDRESS.onion`
4. You should see your archive dashboard

### Step 4: Verify Tor Access

1. Open Tor Browser: https://www.torproject.org/download/
2. Visit: `http://YOUR_ONION_ADDRESS.onion`
3. You should see: "Redd-Archiver Deployment Successful" placeholder page

**This is correct!** The placeholder appears until you generate an archive (Step 5).

### Step 5: Generate Your First Archive (Required for Content)

```bash
# Place your .zst files in data/ directory, then:
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit YOUR_SUBREDDIT_NAME \
  --comments-file /data/YOUR_SUBREDDIT_comments.zst \
  --submissions-file /data/YOUR_SUBREDDIT_submissions.zst \
  --output /output/ \
  --min-score 5 \
  --min-comments 2

# After processing: Refresh your .onion address to see the archive
```

### Step 6: Share With Others

Share your .onion address via:
- Email
- Encrypted messaging (Signal, etc.)
- Direct message

Recipients need Tor Browser to access.

### Success Criteria
- ✅ .onion address generated in tor-hidden-service/hostname
- ✅ Placeholder page accessible via Tor Browser (shows "Deployment Successful")
- ✅ After Step 5: Archive dashboard replaces placeholder
- ✅ All services healthy

**Common Issue**: If you see 403 Forbidden instead of the placeholder, the `output/index.html` file may have been created with wrong permissions. Run: `chmod 644 output/index.html`

### Backup Your Keys

**CRITICAL**: Backup `./tor-hidden-service/` directory immediately!

```bash
# Create encrypted backup
tar -czf tor-keys-backup-$(date +%Y%m%d).tar.gz tor-hidden-service/
gpg --symmetric --cipher-algo AES256 tor-keys-backup-*.tar.gz

# Store encrypted file securely
# If you lose these keys, your .onion address changes forever
```

---

## Production HTTPS (15 Minutes)

For public-facing archives with Let's Encrypt SSL certificates.

### Prerequisites
- ✅ Domain name pointing to your server (e.g., archive.YOUR_DOMAIN.com)
- ✅ DNS A record configured
- ✅ Ports 80 and 443 open in firewall

### Step 1: Verify DNS (2 minutes)

```bash
# Check your server's public IP
curl ifconfig.me

# Check DNS resolution
dig +short archive.YOUR_DOMAIN.com

# These should match!
```

### Step 2: Configure Environment (2 minutes)

```bash
# Clone and create .env
git clone https://github.com/19-84/redd-archiver.git
cd redd-archiver
cp .env.example .env
nano .env
```

**Required changes in .env**:
```bash
# Change password in BOTH places:
POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD
DATABASE_URL=postgresql://reddarchiver:YOUR_SECURE_PASSWORD@/reddarchiver?host=/var/run/postgresql

# Set domain and email:
DOMAIN=archive.YOUR_DOMAIN.com
EMAIL=YOUR_EMAIL@YOUR_DOMAIN.com
CERTBOT_TEST_CERT=true  # Start with staging
```

**Important**: The password must match in both `POSTGRES_PASSWORD` and `DATABASE_URL`!

### Step 3: Run HTTPS Setup Script (10 minutes)

```bash
# Make script executable
chmod +x docker/scripts/init-letsencrypt.sh

# Run automated setup
./docker/scripts/init-letsencrypt.sh
```

The script will:
1. Verify DNS configuration
2. Start services in HTTP mode
3. Request staging certificate (for testing)
4. Switch to HTTPS mode
5. Verify HTTPS works

### Step 4: Verify HTTPS (1 minute)

```bash
# Test HTTPS (use -k for staging cert)
curl -k https://archive.YOUR_DOMAIN.com/health
# Expected: OK

# Test HTTP redirect
curl -I http://archive.YOUR_DOMAIN.com/
# Expected: 301 redirect to HTTPS
```

### Step 5: Switch to Production Certificate (Optional)

After verifying staging works:

```bash
# Update .env
sed -i 's/CERTBOT_TEST_CERT=true/CERTBOT_TEST_CERT=false/' .env

# Remove staging certificates
sudo docker run --rm -v reddarchiver-certbot-certs:/etc/letsencrypt alpine rm -rf /etc/letsencrypt

# Re-run setup (will use production)
./docker/scripts/init-letsencrypt.sh
```

### Success Criteria
- ✅ https://YOUR_DOMAIN.com returns dashboard (no warnings)
- ✅ http://YOUR_DOMAIN.com redirects to HTTPS
- ✅ Certificate valid and trusted
- ✅ SSL Labs test scores A/A+

### Certificate Renewal
Certificates auto-renew every 90 days. Monitor with:
```bash
docker compose logs certbot
docker compose exec certbot certbot certificates
```

---

## Dual-Mode (HTTPS + Tor)

Combine public HTTPS access with private Tor access.

### Prerequisites
- Production HTTPS already working (follow steps above)

### Step 1: Add Tor to Existing Deployment (2 minutes)

```bash
# Add Tor profile (no downtime)
docker compose --profile production --profile tor up -d

# Wait for Tor keys
sleep 60

# Get .onion address
docker compose logs tor | grep "Your .onion address"
```

### Step 2: Verify Both Access Methods

```bash
# Test HTTPS
curl https://archive.YOUR_DOMAIN.com/health

# Test Tor (from Tor Browser)
# Visit: http://YOUR_ONION_ADDRESS.onion
```

### Success Criteria
- ✅ Archive accessible via HTTPS (clearnet)
- ✅ Archive accessible via .onion (Tor)
- ✅ Both show identical content
- ✅ All services healthy

---

## Testing With Example Data

Use the same data and settings as the example instance (r/banned, r/RedditCensors).

### Using Example Data

```bash
# Place your .zst files in data/
ls data/
# Should show:
#   banned_comments.zst
#   banned_submissions.zst
#   RedditCensors_comments.zst
#   RedditCensors_submissions.zst

# Process both subreddits
docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --base-url https://YOUR_SITE.github.io/ \
  --site-name "YOUR SITE Archive" \
  --min-score 5 \
  --min-comments 2
```

### Expected Results

After processing:
- Archive in ./output/
- Both subreddits visible on dashboard
- Search functionality working
- User pages generated
- Static files (CSS, JS) present

---

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker compose logs

# Verify ports available
sudo lsof -i :80
sudo lsof -i :443
sudo lsof -i :5432

# Check resources
docker stats
```

### Database Connection Failed
```bash
# Verify PostgreSQL healthy
docker compose ps postgres

# Test connection
docker compose exec reddarchiver-builder \
  psql -h /var/run/postgresql -U reddarchiver -d reddarchiver -c "SELECT 1"

# Common issue: Password mismatch in .env
# Verify POSTGRES_PASSWORD and DATABASE_URL have same password
grep POSTGRES_PASSWORD .env
grep DATABASE_URL .env
# The password should match in both lines!
```

### HTTPS Certificate Failed
```bash
# Verify DNS
dig +short YOUR_DOMAIN

# Check certbot logs
docker compose logs certbot

# Test with staging first
# Set CERTBOT_TEST_CERT=true in .env
```

### Tor .onion Not Generated
```bash
# Check Tor logs
docker compose logs tor

# Common issues:
# 1. Directory ownership - must be owned by UID 100 (tor user)
sudo chown -R 100:100 tor-hidden-service/

# 2. Directory permissions - must be 700 (not readable by others)
sudo chmod 700 tor-hidden-service/

# 3. Restart Tor after fixing
docker compose restart tor
sleep 60
cat tor-hidden-service/hostname
```

### 403 Forbidden When Visiting Archive
```bash
# This is NORMAL if you haven't generated an archive yet!
# The deployment creates infrastructure but no content.

# Solution: Generate an archive
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit YOUR_SUBREDDIT \
  --comments-file /data/SUBREDDIT_comments.zst \
  --submissions-file /data/SUBREDDIT_submissions.zst \
  --output /output/

# After processing completes, refresh your browser
# You should see the archive dashboard instead of 403
```

### Placeholder Page Shows "No Archives Yet"
```bash
# This means deployment is working correctly!
# Generate your first archive to see actual content:

docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/

# The placeholder will be replaced with the archive dashboard
```

---

## MCP Server Quick Start (AI Integration)

After your archive is running, you can enable AI integration with the MCP server:

### Start MCP Server
```bash
# Start MCP server alongside other services
docker compose up -d mcp-server

# Or run locally
cd mcp_server/
uv run python server.py --api-url http://localhost:5000
```

### Configure Claude Desktop
Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "reddarchiver": {
      "command": "uv",
      "args": ["--directory", "/path/to/redd-archiver/mcp_server", "run", "python", "server.py"],
      "env": { "REDDARCHIVER_API_URL": "http://localhost:5000" }
    }
  }
}
```

### Verify Connection
Restart Claude Desktop and you should have access to 29 MCP tools for querying your archive.

See [MCP Server Documentation](mcp_server/README.md) for complete setup and tool reference.

---

## Next Steps

- **Detailed Configuration**: See `docker/README.md` for advanced options
- **Tor Security Guide**: See `docs/TOR_DEPLOYMENT.md` for operational security
- **Static Hosting**: See `docs/STATIC_DEPLOYMENT.md` for GitHub/Codeberg Pages
- **REST API Reference**: See `docs/API.md` for 30+ API endpoints
- **MCP Server Setup**: See `mcp_server/README.md` for AI integration
- **Performance Tuning**: See `.env.example` for all configuration options

---

**Last Tested**: 2025-12-27 (Local HTTP deployment successful, all services verified healthy)
**Test Environment**: Docker 28.5.2, Docker Compose v2.40.3
**Docker Compose**: 3.8
**PostgreSQL**: 18-alpine
**Python**: 3.12

**Test Status**: ✅ Local HTTP deployment verified working. All verification tests passed (nginx, search-server, PostgreSQL).
