# Deployment Testing Guide

This document describes how to test the deployment scenarios in QUICKSTART.md before each release.

## Testing Overview

**Purpose**: Verify all deployment modes work from a fresh clone with copy-paste commands

**Test Environment Requirements**:
- Linux system (Ubuntu 22.04+ or Debian 12+ recommended)
- Docker 24.0+ and Docker Compose v2.0+
- 8GB+ RAM for full testing
- Internet connection for container downloads

## Test Matrix

| Scenario | Time Est. | Docker Required | Internet Required | Success Criteria |
|----------|-----------|-----------------|-------------------|------------------|
| Local HTTP | 5 min | Yes | Yes (first run) | http://localhost/health returns OK |
| Tor-Only | 2 min | Yes | Yes | .onion address generated, accessible via Tor Browser |
| Production HTTPS | 15 min | Yes | Yes | https://DOMAIN/health returns OK with valid cert |
| Dual-Mode | 17 min | Yes | Yes | Both HTTPS and .onion accessible |
| Example Data | Variable | Yes | No (with cached .zst) | Archive generated with both subreddits |

## Pre-Testing Checklist

Before starting tests:

```bash
# Verify Docker installation
docker --version  # Should be 24.0+
docker compose version  # Should be v2.0+

# Check available disk space (need 5GB+)
df -h .

# Check available RAM
free -h

# Verify ports available
sudo lsof -i :80    # Should be empty
sudo lsof -i :443   # Should be empty
sudo lsof -i :5432  # Should be empty
```

## Test 1: Local HTTP Deployment (5 Minutes)

### Setup (Fresh Clone Simulation)

```bash
# Create test directory
mkdir -p ~/test-deployments/test-local-http
cd ~/test-deployments/test-local-http

# Clone repository (or copy for testing)
git clone <repo-url> redd-archiver
cd redd-archiver

# Verify we have all required files
ls -la docker-compose.yml QUICKSTART.md .env.example
```

### Follow QUICKSTART.md Steps Exactly

```bash
# Step 1: Clone and Configure (2 minutes)
cp .env.example .env

# Edit .env - change POSTGRES_PASSWORD
sed -i 's/your_secure_password_here/test_password_123/g' .env

# Step 2: Start Services (2 minutes)
time docker compose up -d

# Wait for healthy status
sleep 30

# Verify services running
docker compose ps
# Expected: All services show "healthy" or "running"
```

### Step 3: Verify Installation (1 minute)

```bash
# Test nginx
curl http://localhost/health
# Expected output: OK

# Test search server
curl http://localhost:5000/health
# Expected output: {"status":"healthy"}

# Test database connection
docker compose exec postgres pg_isready -U reddarchiver
# Expected output: reddarchiver:5432 - accepting connections
```

### Success Criteria

- [x] All services start without errors
- [x] `docker compose ps` shows all containers healthy
- [x] nginx health check returns "OK"
- [x] search-server health check returns JSON
- [x] PostgreSQL accepting connections
- [x] Total time ≤ 5 minutes

### Document Results

```bash
# Record actual timing
echo "Local HTTP Test Results:" >> test-results.txt
echo "Start time: $(date)" >> test-results.txt
docker compose ps >> test-results.txt
curl http://localhost/health >> test-results.txt
echo "---" >> test-results.txt
```

### Cleanup

```bash
# Stop and remove containers
docker compose down -v

# Optional: Remove test directory
cd ../..
rm -rf test-local-http
```

## Test 2: Tor-Only Deployment (2 Minutes)

### Setup

```bash
mkdir -p ~/test-deployments/test-tor-only
cd ~/test-deployments/test-tor-only
git clone <repo-url> redd-archiver
cd redd-archiver
```

### Follow QUICKSTART.md Tor Section

```bash
# Configure
cp .env.example .env
sed -i 's/your_secure_password_here/test_password_456/g' .env

# Start with Tor profile
time docker compose -f docker-compose.yml -f docker-compose.tor-only.yml --profile tor up -d

# Wait for Tor to generate keys (60 seconds)
sleep 60

# Get .onion address
docker compose logs tor | grep "Your .onion address"

# Alternative: Read from file
cat tor-hidden-service/hostname
```

### Verification

```bash
# Verify clearnet access blocked
curl http://localhost/health 2>&1
# Expected: Connection refused or no response

# Verify .onion address exists
if [ -f tor-hidden-service/hostname ]; then
    echo "✅ .onion address generated: $(cat tor-hidden-service/hostname)"
else
    echo "❌ FAILED: No .onion address found"
fi

# Verify containers healthy
docker compose ps
```

### Manual Test: Tor Browser Access

**Manual Step** (cannot be automated):
1. Install Tor Browser: https://www.torproject.org/download/
2. Open Tor Browser
3. Visit: `http://YOUR_ONION_ADDRESS.onion`
4. Verify dashboard loads

### Success Criteria

- [x] .onion address generated in tor-hidden-service/hostname
- [x] Clearnet access blocked (curl localhost fails)
- [x] All containers healthy
- [x] Total time ≤ 2 minutes
- [x] Manual: Dashboard accessible via Tor Browser

### Cleanup

```bash
# Backup Tor keys before cleanup (for testing reuse)
cp -r tor-hidden-service tor-hidden-service-backup

docker compose down -v
```

## Test 3: Example Data Processing

**Prerequisites**: .zst files for testing (r/banned, r/RedditCensors)

### Setup

```bash
# Use existing test deployment or create new one
cd ~/test-deployments/test-local-http/redd-archiver

# Create data directory and place .zst files
mkdir -p data
# Copy your test .zst files to data/
# - banned_comments.zst
# - banned_submissions.zst
# - RedditCensors_comments.zst
# - RedditCensors_submissions.zst
```

### Process Archive

```bash
# Process both subreddits
time docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ \
  --base-url https://example.github.io/ \
  --site-name "Test Archive" \
  --min-score 5 \
  --min-comments 2
```

### Verify Results

```bash
# Check output directory
ls -lh output/

# Verify expected structure
test -d output/r/banned && echo "✅ banned subreddit processed"
test -d output/r/RedditCensors && echo "✅ RedditCensors subreddit processed"
test -f output/index.html && echo "✅ Dashboard generated"
test -d output/static && echo "✅ Static files copied"

# Check database
docker compose exec postgres psql -U reddarchiver -d reddarchiver -c \
  "SELECT subreddit, COUNT(*) FROM posts GROUP BY subreddit;"
```

### Success Criteria

- [x] Processing completes without errors
- [x] Both subreddits visible in output/r/
- [x] Dashboard (index.html) generated
- [x] Static files present
- [x] Search functionality works (manual check)
- [x] User pages generated

## Test 4: Production HTTPS (Advanced)

**Prerequisites**:
- Domain name with DNS configured
- Server with public IP
- Ports 80/443 accessible from internet

**Note**: This test requires a real domain and cannot be fully automated.

### Setup

```bash
mkdir -p ~/test-deployments/test-production-https
cd ~/test-deployments/test-production-https
git clone <repo-url> redd-archiver
cd redd-archiver
```

### Configure

```bash
cp .env.example .env

# Edit .env with production values
nano .env
# Set:
#   POSTGRES_PASSWORD=secure_production_password
#   DOMAIN=archive.yourdomain.com
#   EMAIL=your-email@domain.com
#   CERTBOT_TEST_CERT=true  # Start with staging
```

### Run Setup Script

```bash
# Verify DNS first
dig +short archive.yourdomain.com
curl ifconfig.me
# These should match!

# Run HTTPS setup
chmod +x docker/scripts/init-letsencrypt.sh
time ./docker/scripts/init-letsencrypt.sh
```

### Verify HTTPS

```bash
# Test staging certificate (use -k for self-signed)
curl -k https://archive.yourdomain.com/health

# Test HTTP redirect
curl -I http://archive.yourdomain.com/

# Check certificate
docker compose exec certbot certbot certificates
```

### Success Criteria

- [x] DNS resolves correctly
- [x] Staging certificate obtained
- [x] HTTPS endpoint responds
- [x] HTTP redirects to HTTPS
- [x] All services healthy
- [x] Total time ≤ 15 minutes

## Test Results Template

Copy this template to document your test results:

```markdown
# Deployment Test Results

**Test Date**: YYYY-MM-DD
**Tester**: Name/Username
**Environment**: Ubuntu 22.04 / Debian 12 / Other
**Docker Version**: X.Y.Z
**Docker Compose Version**: vX.Y.Z

## Test 1: Local HTTP

- Start time: HH:MM
- End time: HH:MM
- Duration: X minutes
- Result: ✅ PASS / ❌ FAIL
- Notes:

## Test 2: Tor-Only

- Start time: HH:MM
- End time: HH:MM
- Duration: X minutes
- Result: ✅ PASS / ❌ FAIL
- .onion address: xxxxx.onion
- Tor Browser access: ✅ PASS / ❌ FAIL
- Notes:

## Test 3: Example Data

- Processing time: X minutes
- Archive size: X GB
- Post count (banned): X
- Post count (RedditCensors): X
- Result: ✅ PASS / ❌ FAIL
- Notes:

## Test 4: Production HTTPS (Optional)

- Domain: archive.example.com
- Certificate: Staging / Production
- Result: ✅ PASS / ❌ FAIL
- Notes:

## Issues Found

List any issues, errors, or missing documentation:
1.
2.

## Recommendations

Suggested improvements to QUICKSTART.md or documentation:
1.
2.

## Overall Status

- [ ] All tests passed
- [ ] Ready for release
- [ ] Issues need resolution

**Sign-off**: [Tester Name]
```

## Continuous Testing

### Before Each Release

1. Run Test 1 (Local HTTP) - mandatory
2. Run Test 2 (Tor-Only) - mandatory
3. Run Test 3 (Example Data) - if data available
4. Update "Last Tested" date in QUICKSTART.md
5. Document any changes needed

### After Major Changes

Re-run affected tests:
- Docker changes → All tests
- Documentation → Manual review
- Core processing → Test 3 (Example Data)
- Networking → Tests 1, 2, 4

## Troubleshooting Common Test Issues

### Issue: Containers won't start

```bash
# Check logs
docker compose logs

# Verify ports available
sudo lsof -i :80
sudo lsof -i :443
sudo lsof -i :5432

# Check disk space
df -h

# Check memory
free -h
```

### Issue: Health checks fail

```bash
# Wait longer (services may need time)
sleep 60
docker compose ps

# Check individual service logs
docker compose logs nginx
docker compose logs search-server
docker compose logs postgres
```

### Issue: Tor .onion not generated

```bash
# Check Tor logs
docker compose logs tor

# Verify directory permissions
ls -la tor-hidden-service/

# Restart Tor
docker compose restart tor
sleep 60
cat tor-hidden-service/hostname
```

## Updating QUICKSTART.md

After successful testing, update QUICKSTART.md:

```bash
# Update Last Tested line
sed -i "s/Last Tested.*/Last Tested: $(date +%Y-%m-%d) (Ubuntu 22.04, Docker 24.0.7)/" QUICKSTART.md

# Commit update
git add QUICKSTART.md
git commit -m "docs: update QUICKSTART.md last tested date"
```

---

**Maintainer Notes**:
- Keep this guide updated with any new test scenarios
- Document environment-specific issues discovered
- Add automation scripts as testing matures
- Consider CI/CD integration for automated testing
