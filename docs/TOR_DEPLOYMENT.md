# Tor Hidden Service Deployment Guide for Redd-Archiver

Complete guide for deploying redd-archiver as a Tor hidden service (.onion) for maximum privacy, anonymity, and censorship resistance.

> **Quick Start**: For quick Tor deployment, see the [Tor Homelab section in QUICKSTART.md](../QUICKSTART.md#tor-homelab-deployment-2-minutes). This document provides comprehensive Tor deployment documentation.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Tor Network Overview](#tor-network-overview)
3. [Deployment Modes](#deployment-modes)
4. [Prerequisites](#prerequisites)
5. [Dual-Mode Deployment](#dual-mode-deployment-https--tor)
6. [Tor-Only Deployment](#tor-only-deployment-maximum-privacy)
7. [Hidden Service Key Management](#hidden-service-key-management)
8. [Troubleshooting](#troubleshooting)
9. [Security Considerations](#security-considerations)
10. [Advanced Topics](#advanced-topics)

---

## Introduction

Tor hidden services allow you to host your redd-archiver instance on the Tor network, making hosting accessible and private without complex networking setup.

**Why Tor is Perfect for Homelab Users**:

Tor eliminates traditional hosting complexity:
- ✅ **No Port Forwarding**: No router configuration or NAT traversal
- ✅ **No Domain Name**: Save $10-15/year, no DNS management
- ✅ **No Dynamic IP**: Works regardless of IP changes
- ✅ **No Internet Exposure**: Home server stays behind firewall
- ✅ **Works Behind CGNAT**: Even restrictive ISPs work
- ✅ **Instant Sharing**: Just share .onion address via email/chat

**Practical Use Cases**:
- Archive and share banned/quarantined subreddits privately
- Distribute archives of controversial or at-risk communities
- Research deleted content without revealing researcher identity
- Share subreddit backups with community members securely
- Preserve niche communities without hosting infrastructure
- Test production deployments before configuring HTTPS

**Privacy Benefits**:
- **Anonymity**: Users access without revealing IP address
- **Censorship Resistance**: Works even if clearnet is blocked
- **Location Privacy**: Server location cannot be determined
- **End-to-End Encryption**: Tor provides encryption automatically

### Why Redd-Archiver Works Well on Tor

Redd-archiver's architecture provides better Tor performance than traditional archive systems:

**Server-Side Search**:
- PostgreSQL processes queries server-side, returning HTML results
- Optimized for low-latency networks including Tor

**Zero JavaScript**:
- Full functionality without JavaScript (works on Tor Browser "Safest" mode)
- Theme switching, navigation, and UI implemented via CSS

**Local Assets**:
- All resources served from same origin (no CDN requests)
- Single Tor circuit handles all requests

**Performance**: Optimized for low-latency networks. Theme switching is instant via CSS.

### When to Use Each Mode

**Tor-Only Mode** (recommended for homelabs):
- Personal/homelab Reddit archive hosting
- Sharing banned or quarantined subreddit archives
- Distributing backups to community members privately
- Research on controversial communities without exposure
- Maximum privacy and security
- Simplest deployment (2 commands)

**Dual-Mode** (HTTPS + Tor):
- Public archives with privacy option
- Serve both regular and Tor users
- Maximum reach with privacy choice
- Professional/production deployments

---

## Tor Network Overview

### What is Tor?

Tor (The Onion Router) is a network that provides:
- Anonymous communication
- Censorship circumvention
- Location privacy for servers
- Encrypted multi-hop routing

### How Hidden Services Work

```
Tor Browser ──► Entry Node ──► Middle Node ──► Rendezvous ──► Your Server
     (user)       (relay)         (relay)         (point)     (.onion)

1. User connects to Tor network via Tor Browser
2. Traffic routes through 3 random Tor relays
3. Rendezvous point connects user to hidden service
4. Neither user nor server knows other's IP address
5. End-to-end encryption throughout
```

### .onion Addresses

**.onion v3** (current standard):
- 56 characters + ".onion" suffix
- Cryptographically derived from ED25519 public key
- Format: `http://[56-chars].onion`
- Example: `http://thehiddenwiki7fhdx5h4gnkpj...xyz.onion`

**Why so long?**
- Strong cryptography (ED25519 instead of RSA)
- Collision-resistant (practically impossible to generate duplicate)
- Self-authenticating (address IS the public key hash)

---

## Deployment Modes

### Comparison Matrix

| Feature | Dual-Mode | Tor-Only |
|---------|-----------|----------|
| **Clearnet HTTPS Access** | ✅ Yes | ❌ No |
| **Tor .onion Access** | ✅ Yes | ✅ Yes |
| **Domain Name Required** | ✅ Yes | ❌ No |
| **SSL Certificates Required** | ✅ Yes | ❌ No |
| **Port Forwarding Required** | ✅ Yes | ❌ No |
| **Router Configuration** | ✅ Yes | ❌ No |
| **Server Location Hidden** | ❌ No | ✅ Yes |
| **Works Behind CGNAT** | ❌ No | ✅ Yes |
| **Setup Complexity** | Medium | **Very Low** |
| **Cost** | ~$15/year | **$0/year** |
| **Homelab Friendly** | ⚠️ Requires work | ✅ **Perfect** |

### Tor-Only (Homelab Recommended)

**Perfect for**:
- 🏠 **Homelab Reddit archive hosting** (primary use case)
- Sharing banned/quarantined subreddit archives privately
- Distributing community backups to members
- Archiving controversial communities without exposure
- Behind restrictive ISPs (CGNAT, blocked ports)
- Research requiring operational security
- Testing before production deployment

**Benefits**:
- Zero networking configuration
- No cost (no domain name)
- Secure by default (no internet exposure)
- Works anywhere (even restrictive networks)

**Trade-offs**:
- Users need Tor Browser (5-minute install)
- Slower than clearnet (acceptable for archives)
- .onion addresses are long (56 chars)

### Dual-Mode (HTTPS + Tor)

**Best for**:
- Public archives with privacy option
- Professional/production deployments
- Serving both regular and Tor users
- Maximum accessibility

**Trade-offs**:
- Requires domain, DNS, certificates, port forwarding
- Server location exposed via clearnet
- More complex setup

---

## Prerequisites

### System Requirements

**Same as standard deployment** (see docker/README.md):
- Docker Engine 24.0+
- Docker Compose v2.0+
- 8GB RAM minimum
- 10GB free disk space

**Additional for Tor**:
- Tor Browser for testing (download: https://www.torproject.org/download/)

### No Additional Requirements

Unlike HTTPS deployment, Tor does NOT require:
- ❌ Domain name
- ❌ DNS configuration
- ❌ Firewall port opening (80/443)
- ❌ Public IP address
- ❌ SSL certificates

Tor works entirely within the Tor network!

---

## Dual-Mode Deployment (HTTPS + Tor)

### Step 1: Setup HTTPS

If not already configured, setup HTTPS first:

```bash
# See "Production HTTPS Deployment" in docker/README.md
./docker/scripts/init-letsencrypt.sh
```

Verify HTTPS works:
```bash
curl https://your-domain.com/health
# Should return: OK
```

### Step 2: Prepare Tor Directories

```bash
# Create and configure Tor directories (one-time setup)
mkdir -p ./tor-hidden-service
mkdir -p ./tor-public
sudo chown 100:100 ./tor-hidden-service ./tor-public
sudo chmod 700 ./tor-hidden-service
sudo chmod 755 ./tor-public
```

### Step 3: Start Tor Service

```bash
# Add Tor to running HTTPS deployment (no downtime)
docker compose --profile production --profile tor up -d

# Verify services
docker compose ps
# Should show: postgres, builder, search-server, nginx, certbot, tor (all healthy)
```

### Step 4: Get Your .onion Address

```bash
# Wait for Tor to generate keys and copy to public location
sleep 20

# View .onion address from logs
docker compose logs tor | grep "✓ Hostname copied"

# OR read from public location (recommended)
cat ./tor-public/hostname
```

Example output:
```
abcdefgh12345678ijklmnop90qrstuvwxyz1234567890abcdefgh.onion
```

### Step 5: Test Tor Access

1. Download and install Tor Browser: https://www.torproject.org/download/
2. Open Tor Browser
3. Visit: `http://[your-address].onion`
4. Verify archive loads correctly
5. Test search functionality
6. Test navigation between pages

### Step 6: Verify Dual-Mode Operation

```bash
# Test clearnet HTTPS
curl https://your-domain.com/health
# Should return: OK

# Test Tor (from within Tor container)
docker compose exec tor wget -O- http://nginx/health
# Should return: OK

# Both should serve identical content
```

---

## Tor-Only Deployment (Maximum Privacy)

### Step 0: Prepare Tor Directories (REQUIRED)

**⚠️ IMPORTANT**: Run these commands BEFORE starting Tor to avoid permission issues.

```bash
# Create directories
mkdir -p ./tor-hidden-service
mkdir -p ./tor-public

# Set ownership to Tor user (UID 100)
sudo chown 100:100 ./tor-hidden-service
sudo chown 100:100 ./tor-public

# Set permissions
sudo chmod 700 ./tor-hidden-service  # Secure (Tor requirement)
sudo chmod 755 ./tor-public           # Public (API detection)
```

**Why this matters**:
- Tor daemon runs as UID 100, requires 700 permissions on hidden service directory
- If directories created by Docker as root, Tor cannot write keys
- This setup ensures reproducible, secure deployments

### Step 1: Start Tor-Only Mode

```bash
# Start with Tor-only configuration
docker compose -f docker-compose.yml -f docker-compose.tor-only.yml --profile tor up -d

# Verify services
docker compose ps
# Should show: postgres, builder, search-server, nginx, tor (all healthy)
# Note: certbot not running (not needed)
# Note: nginx ports empty (not exposed to host)
```

### Step 2: Get Your .onion Address

```bash
# Wait for Tor to generate keys and copy to public location
sleep 20

# View .onion address from logs
docker compose logs tor | grep "✓ Hostname copied"

# OR read from public location (recommended)
cat ./tor-public/hostname

# Example output:
# u7bntvsfci4cwwjk5cfj6vs4xewqzl6ykpim2pdgyd5nmi6uzvn4jvyd.onion
```

### Step 3: Test Tor-Only Access

1. Open Tor Browser
2. Visit: `http://[your-address].onion`
3. Verify archive loads
4. Test search and navigation

### Step 4: Verify Clearnet Blocked

```bash
# Verify clearnet access is blocked
curl http://localhost
# Should fail: Connection refused

curl http://your-server-ip
# Should fail: Connection refused

# Ports not exposed to host
docker compose ps nginx
# Ports column should be empty

# This confirms maximum privacy configuration
```

---

## Hidden Service Key Management

### Key Files Explained

```
tor-hidden-service/
├── hostname                    # Your .onion address (56 chars)
├── hs_ed25519_public_key      # Public key (32 bytes)
└── hs_ed25519_secret_key      # Private key (64 bytes) - SECRET!
```

**hostname**:
- Your public .onion address
- Safe to share (users need this to access your archive)
- Example: `abcd...xyz.onion`

**hs_ed25519_public_key**:
- Public portion of ED25519 key pair
- Used to derive .onion address
- Safe to share (part of cryptographic identity)

**hs_ed25519_secret_key**:
- Private portion of ED25519 key pair
- **NEVER SHARE THIS FILE**
- Loss = permanent .onion address change
- Theft = attacker can impersonate your hidden service

### Backup Procedures

#### Create Encrypted Backup

```bash
# 1. Create compressed archive
tar -czf tor-keys-backup-$(date +%Y%m%d).tar.gz tor-hidden-service/

# 2. Encrypt with GPG (recommended)
gpg --symmetric --cipher-algo AES256 tor-keys-backup-$(date +%Y%m%d).tar.gz

# 3. Store encrypted backup securely
# Options: encrypted USB drive, encrypted cloud storage, offline backup

# 4. Delete unencrypted backup
rm tor-keys-backup-$(date +%Y%m%d).tar.gz
```

#### Restore from Backup

```bash
# 1. Decrypt backup
gpg --decrypt tor-keys-backup-20250101.tar.gz.gpg > tor-keys-backup-20250101.tar.gz

# 2. Stop Tor
docker compose down

# 3. Remove current keys (if any)
rm -rf tor-hidden-service/

# 4. Extract backup
tar -xzf tor-keys-backup-20250101.tar.gz

# 5. Verify permissions
chmod 700 tor-hidden-service/
chmod 600 tor-hidden-service/*

# 6. Restart Tor
docker compose --profile tor up -d

# 7. Verify .onion address restored
cat tor-hidden-service/hostname
docker compose logs tor | grep "Your .onion address"
```

### Key Rotation (Advanced)

**Should you rotate keys?**

Generally: **NO**

Rotating keys means:
- New .onion address
- All existing links break
- Users lose access (no redirect possible)

**Only rotate if**:
- Private key compromised
- Migrating to new infrastructure
- Deliberate address change for security reasons

---

## Troubleshooting

### Tor Container Issues

#### Container Exits Immediately

**Diagnostic**:
```bash
docker compose logs tor
```

**Common causes**:
1. **torrc syntax error**: Verify with `docker compose run --rm tor tor --verify-config`
2. **Permission denied**: `chmod 700 tor-hidden-service/`
3. **Missing directory**: Tor will create it automatically

#### Keys Not Generating

**Symptom**: hostname file doesn't exist after 60+ seconds

**Solution**:
```bash
# Check if Tor is actually running
docker compose ps tor
# Status should be: Up (healthy)

# Check Tor logs
docker compose logs tor | tail -50

# Manually check key generation
docker compose exec tor ls -la /var/lib/tor/hidden_service/

# If directory empty, Tor hasn't started hidden service
# Check torrc syntax
docker compose run --rm tor tor --verify-config
```

#### Permission Issues (CRITICAL - Read This First!)

**Symptom**: Tor logs show permission errors

```
[warn] /var/lib/tor/hidden_service is not owned by this user (tor, 100) but by root (0)
[warn] Permissions on directory /var/lib/tor/hidden_service are too permissive
[err] Reading config failed
```

**Root Cause**: Directory ownership/permissions incorrect for Tor daemon (runs as UID 100)

**Solution** (reproducible setup for fresh deployments):

```bash
# Step 1: Create required directories
mkdir -p ./tor-hidden-service
mkdir -p ./tor-public

# Step 2: Set ownership to Tor user (UID 100)
sudo chown 100:100 ./tor-hidden-service
sudo chown 100:100 ./tor-public

# Step 3: Set permissions
# - Secure directory: 700 (Tor requires this for security)
# - Public directory: 755 (world-readable for API detection)
sudo chmod 700 ./tor-hidden-service
chmod 755 ./tor-public

# Step 4: Start Tor
docker compose --profile tor up -d

# Step 5: Verify keys generated (wait 20 seconds)
sleep 20
docker compose logs tor | grep "✓ Hostname copied"

# Step 6: Verify hostname accessible
cat ./tor-public/hostname
# Should show your .onion address

# Step 7: Test API detection
curl http://localhost:5000/api/v1/stats | jq '.features.tor'
# Should return: true
```

**Why Two Directories?**

1. **`./tor-hidden-service/`** (PRIVATE):
   - Contains private keys (hs_ed25519_secret_key)
   - Requires 700 permissions (Tor security requirement)
   - Owned by UID 100 (tor user)
   - NEVER share or expose these files

2. **`./tor-public/`** (PUBLIC):
   - Contains only hostname file (your .onion address)
   - Permissions 755 (world-readable)
   - Hostname is PUBLIC info (users need it to connect)
   - Safe to share, no security risk

**Security Model**:
- ✅ Private keys stay secure (700/600, never copied)
- ✅ Hostname copied to public location (it's public info anyway)
- ✅ API can detect Tor without accessing private keys
- ✅ Reproducible across fresh deployments

**File Structure After Setup**:
```
./tor-hidden-service/          # 700 permissions, UID 100
├── hostname                    # Original (644)
├── hs_ed25519_public_key      # 600 (never share)
└── hs_ed25519_secret_key      # 600 (CRITICAL - never share!)

./tor-public/                   # 755 permissions, UID 100
└── hostname                    # 644 (copy, world-readable)
```

### Tor Network Issues

#### Can't Access .onion Address

**Symptom**: Tor Browser shows "Unable to connect"

**Diagnostic steps**:

```bash
# 1. Verify Tor container is healthy
docker compose ps tor
# Should show: Up (healthy)

# 2. Check hidden service is configured
docker compose exec tor cat /var/lib/tor/hidden_service/hostname

# 3. Verify nginx is accessible from Tor
docker compose exec tor wget -O- http://nginx/health

# 4. Check Tor network connectivity
# In Tor Browser: visit https://check.torproject.org/
# Should confirm Tor is working

# 5. Review Tor logs for errors
docker compose logs tor | grep -E "(warn|err)"
```

#### 403 Forbidden Error

**Symptom**: Tor Browser shows "403 Forbidden" when visiting .onion address

**Root Cause**: No archive has been generated yet, or file permissions are incorrect

**Solution**:

```bash
# Scenario 1: No archive generated (most common)
# The deployment creates infrastructure but no content
# Generate your first archive:

docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit YOUR_SUBREDDIT \
  --comments-file /data/SUBREDDIT_comments.zst \
  --submissions-file /data/SUBREDDIT_submissions.zst \
  --output /output/

# After processing: Refresh .onion address in Tor Browser

# Scenario 2: Placeholder page has wrong permissions
# Check file permissions
ls -la output/index.html

# Should be: -rw-r--r-- (644)
# If showing: -rw------- (600), fix with:
chmod 644 output/index.html

# Test locally first
curl http://localhost/
# Should show placeholder page, not 403

# Then test via Tor Browser
```

**Expected Behavior**:
- **Before archive generation**: Placeholder page "Redd-Archiver Deployment Successful"
- **After archive generation**: Dashboard with subreddit list and search

**Verification**:
```bash
# Check what files exist
ls -la output/
# Should have: index.html (placeholder or dashboard)

# Check nginx can read files
docker compose exec nginx ls -la /usr/share/nginx/html/index.html
# Permissions should allow nginx (UID 101) to read
```

#### Slow .onion Access

**Symptom**: Pages load very slowly via Tor

**Causes**:
- Tor network congestion (normal, can't fix)
- Multiple circuit builds (first access is always slower)
- Large images/assets (optimize your content)

**Mitigations**:
```bash
# 1. Increase max streams
# Edit docker/tor/torrc:
HiddenServiceMaxStreams 200  # Increase from 100

# 2. Monitor Tor resource usage
docker stats reddarchiver-tor

# 3. Consider OnionBalance for high traffic
```

### Nginx Issues

#### nginx Can't Resolve "nginx" Hostname

**Symptom**: Tor logs show "Could not resolve nginx"

**Solution**:
```bash
# Verify nginx is on same Docker network
docker compose ps nginx
docker network inspect reddarchiver-network

# Restart Tor
docker compose restart tor
```

---

## Security Considerations

### Threat Model

**What Tor provides**:
- ✅ User anonymity (IP addresses hidden)
- ✅ Censorship circumvention
- ✅ Server location privacy (in Tor-only mode)
- ✅ Traffic encryption
- ✅ Content integrity

**What Tor does NOT provide**:
- ❌ Protection against correlation attacks (dual-mode)
- ❌ Protection against malicious exit nodes (not applicable for hidden services)
- ❌ Protection against compromised Tor nodes
- ❌ Protection against timing attacks (advanced threat)

### Operational Security Best Practices

#### For Archive Operators

1. **Key Management**:
   - Backup keys immediately after generation
   - Store backups encrypted and offline
   - Never commit keys to version control (.gitignore configured)
   - Test backup restoration regularly

2. **Correlation Prevention** (dual-mode):
   - Consider different styling for .onion vs clearnet
   - Don't link .onion address from clearnet site
   - Use separate analytics (if any)
   - Document privacy considerations for users

3. **Monitoring**:
   - Monitor Tor logs for unusual activity
   - Set up alerts for container restarts
   - Monitor disk space (logs can grow)
   - Track .onion address changes (should never change)

4. **Server Security**:
   - Keep Docker and images updated
   - Review Tor logs periodically
   - Limit SSH access (VPN, key-only auth)
   - Consider full disk encryption

#### For Archive Users

Document these recommendations for your users:

1. **Always use Tor Browser**:
   - Never access .onion via regular browser
   - Keep Tor Browser updated
   - Don't mix Tor and clearnet browsing

2. **Verify .onion address**:
   - Get address from trusted source
   - Check address matches exactly (no typos)
   - Bookmark for future access

3. **Privacy considerations**:
   - Don't log in with real accounts
   - Disable JavaScript (Tor Browser default)
   - Clear browser data regularly

### Threat Scenarios

#### Scenario 1: Private Key Theft

**Attack**: Attacker gains access to hs_ed25519_secret_key

**Impact**:
- Attacker can impersonate your hidden service
- Users connect to attacker's server (thinking it's yours)
- No way to revoke compromised key

**Mitigation**:
- Secure key permissions: `chmod 600 tor-hidden-service/hs_ed25519_secret_key`
- Encrypt backups
- Limit SSH access to server
- Consider full disk encryption
- If compromised: Generate new key, communicate new address via out-of-band channel

#### Scenario 2: Correlation Attack (Dual-Mode)

**Attack**: Attacker correlates clearnet and .onion access

**Method**:
- Same content on both channels
- Unique identifiers (CSS, images, typos)
- Timing analysis (content updates)

**Impact**:
- User anonymity compromised
- Server location revealed (via clearnet)

**Mitigation**:
- Use Tor-only mode if correlation is concern
- Different styling for .onion
- Don't advertise .onion on clearnet site
- Use separate hosting for truly sensitive archives

#### Scenario 3: Traffic Analysis

**Attack**: Advanced adversary monitors network traffic

**Method**:
- Timing correlation between Tor entry and hidden service
- Volume analysis
- Requires monitoring both user and server

**Impact**:
- May deanonymize users
- May locate hidden service server

**Mitigation**:
- This is an advanced attack requiring significant resources
- Use bridges/obfuscation for users
- Consider VPN on server (in addition to Tor)
- For truly sensitive content: consult security professionals

---

## Advanced Topics

### OnionBalance (High Availability)

For archives with high traffic (>100 concurrent users):

```yaml
# Future implementation - load balance across multiple Tor instances
services:
  onionbalance:
    image: onionbalance/onionbalance:latest
    volumes:
      - ./onionbalance-config:/etc/onionbalance
    networks:
      - reddarchiver-network

  tor-backend-1:
    image: leplusorg/tor:latest
    # Backend instance 1

  tor-backend-2:
    image: leplusorg/tor:latest
    # Backend instance 2
```

**Benefits**:
- Single .onion address
- Load distributed across multiple backends
- Redundancy (if one fails, others continue)

**Complexity**: Requires OnionBalance configuration, multiple Tor instances

### Client Authorization

Restrict access to authorized users only:

**Use case**: Private archives, limited distribution

**Implementation**:
```bash
# Generate client key
docker compose exec tor onionservice-auth

# Add to authorized_clients/
mkdir -p tor-hidden-service/authorized_clients/
echo "descriptor:x25519:[client-public-key]" > tor-hidden-service/authorized_clients/user1.auth

# Restart Tor
docker compose restart tor

# Users need client private key to access
```

**Trade-off**: Users must configure Tor Browser with client key (complex)

### Vanity .onion Addresses

**Warning**: Extremely computationally expensive

Generate .onion addresses with custom prefix:

```bash
# Install mkp224o (vanity address generator)
# Example: Generate address starting with "archive"
# Time: Days to weeks on modern hardware

# This is generally NOT recommended
# v3 addresses are already hard to remember
# Use descriptive landing page instead
```

**Recommendation**: Don't bother with vanity addresses, focus on usability

### Monitoring and Analytics

**Traditional analytics don't work well with Tor**:
- No IP addresses (all appear as 127.0.0.1)
- No geolocation
- No reliable user tracking

**Tor-friendly metrics**:
- Page views (server-side logs)
- Popular content (view counts)
- Search queries (anonymized)
- Connection count (concurrent users)

**Respect user privacy**: Don't try to deanonymize Tor users

---

## Performance Optimization

### Tor-Specific Optimizations

```bash
# Increase max streams (higher concurrency)
# Edit docker/tor/torrc:
HiddenServiceMaxStreams 200  # Default: 100

# Increase nginx worker connections
# Edit docker/nginx/nginx.conf.http:
worker_connections 2048;  # Default: 1024
```

### Content Optimization

Tor is slower than clearnet, optimize accordingly:

1. **Compress assets**: gzip enabled by default
2. **Optimize images**: Use WebP, reduce sizes
3. **Minimize requests**: Combine CSS/JS files
4. **Cache effectively**: Leverage browser caching
5. **Lazy load images**: Load images on demand

---

## Migration and Maintenance

### Adding Tor to Existing Deployment

**No downtime**:
```bash
# Add Tor to running deployment
docker compose --profile [current] --profile tor up -d

# current = production (for HTTPS) or none (for HTTP)
```

### Removing Tor

```bash
# Remove Tor, keep other services
docker compose down
docker compose --profile [current] up -d

# Tor container stops, keys remain in ./tor-hidden-service/
```

### Updating .onion Address

**Only if absolutely necessary** (breaks all existing links):

```bash
# 1. Stop Tor
docker compose down

# 2. Backup old keys
mv tor-hidden-service/ tor-hidden-service-old/

# 3. Start Tor (generates new keys)
docker compose --profile tor up -d

# 4. Communicate new .onion address to users
# Use out-of-band channels (email, social media, etc.)
```

---

## Additional Resources

- [Tor Project Official Site](https://www.torproject.org/)
- [Tor Hidden Service Documentation](https://community.torproject.org/onion-services/)
- [Tor Browser Download](https://www.torproject.org/download/)
- [Redd-Archiver Docker Guide](../docker/README.md)
- [Operational Security Guide](https://www.whonix.org/wiki/DoNot)

---

## Support and Community

**Issues**: Report bugs at https://github.com/19-84/redd-archiver/issues

**Tor-Specific Issues**:
Include in bug reports:
- Deployment mode (dual-mode or Tor-only)
- Tor version: `docker compose exec tor tor --version`
- Hidden service directory contents (DON'T include private key!)
- Tor logs: `docker compose logs tor`

**Security Issues**:
For security vulnerabilities, see SECURITY.md

---

**Last Updated**: 2025-12-27
**Tor Version**: Latest (via leplusorg/tor:latest)
**Hidden Service**: v3 only (ED25519)
