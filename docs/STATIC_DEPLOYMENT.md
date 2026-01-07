# Static Hosting Deployment Guide

Complete guide for deploying redd-archiver to GitHub Pages or Codeberg Pages for zero-cost static hosting.

> **⚠️ Note**: This is ONE deployment option. Redd-Archiver supports multiple deployment modes:
> - **Static Hosting** (this guide): Browse-only, no search
> - **Docker Deployment**: Full search functionality
> - **Offline Browsing**: No server needed
>
> See [Deployment Options](../README.md#-deployment-options) for complete comparison.

---

## Overview

Static hosting platforms like GitHub Pages and Codeberg Pages provide free hosting for HTML files. Redd-archiver generates static HTML that works on these platforms, though with limitations.

**What you get**:
- Zero-cost hosting
- Automatic HTTPS
- No server management
- Global CDN (GitHub Pages)

**What you lose**:
- No search functionality (browse-only - use sorted indexes instead)
- Repository size limits
- Manual updates required

---

## Platform Comparison

| Feature | GitHub Pages | Codeberg Pages |
|---------|--------------|----------------|
| **Repository Limit** | 1GB | No hard limit |
| **File Size Limit** | 100MB max | No specified limit |
| **Bandwidth** | 100GB/month (soft) | Best effort |
| **HTTPS** | ✅ Automatic | ✅ Automatic |
| **Custom Domain** | ✅ Supported | ✅ Supported |
| **Build Process** | Jekyll optional | Static only |
| **Availability** | High | Community-supported |
| **Cost** | Free (public repos) | Free |

**Recommendation**: GitHub Pages for reliability, Codeberg Pages for larger archives (no hard limits)

---

## Archive Size Optimization

### Intelligent Filtering Strategy

For static hosting with size limits, use aggressive filtering to capture high-quality content while minimizing archive size:

**Score Filtering**:
```bash
# Only archive highly-upvoted posts
python reddarc.py /data --output archive/ \
  --subreddit example \
  --min-score 100 \
  --min-comments 20
```

**Impact**:
- Reduces archive size by 70-90%
- Captures most interesting/valuable content
- Enables multi-subreddit archives within limits

**Example Optimization**:
```bash
# Without filtering: 500MB archive (3,000 posts)
# With --min-score 50: 150MB archive (800 posts)
# With --min-score 100: 80MB archive (400 posts)
# With --min-score 200: 40MB archive (150 posts)
```

### Multi-Subreddit Strategy

Fit multiple subreddits in single GitHub Pages repository:

```bash
# Archive 5 subreddits with aggressive filtering
python reddarc.py /data --output archive/ \
  --min-score 100 \
  --min-comments 10 \
  --subreddit technology,programming,webdev,datascience,machinelearning

# Result: ~300MB total (vs 2GB unfiltered)
# Captures "best of" content from all 5 subreddits
```

**Benefits**:
- Single repository for related subreddits
- Focus on high-quality discussions
- Stay within GitHub's 1GB limit
- Better signal-to-noise ratio

### Filtering Recommendations by Archive Size Goal

| Target Size | Recommended Filters | Coverage | Use Case |
|-------------|---------------------|----------|----------|
| <50MB | `--min-score 200` | Top 5% | "Best of" compilation |
| <100MB | `--min-score 100 --min-comments 10` | Top 10-15% | High-quality archive |
| <200MB | `--min-score 50 --min-comments 5` | Top 20-30% | Quality-focused |
| <500MB | `--min-score 10` | Top 40-60% | Comprehensive |

**Note**: Test filtering with `--dry-run` to preview post counts before full generation.

## Archive Size Recommendations

### Small Archives (<100MB HTML output)

**Examples**: Single small subreddit (<10,000 posts), niche communities

**GitHub Pages**: ✅ Ideal
**Codeberg Pages**: ✅ Ideal

**Pros**:
- Well within platform limits
- Fast page loads
- Manageable repository size

**Setup**: 10 minutes manual deployment

### Medium Archives (100-500MB HTML output)

**Examples**: Medium subreddits (10k-50k posts), multiple small subreddits

**GitHub Pages**: ⚠️ Approaching 1GB limit (risk of exceeding with git history)
**Codeberg Pages**: ✅ Should work (no hard limit documented)

**Pros**:
- Still feasible for static hosting
- Zero cost

**Cons**:
- Repository approaching size limits on GitHub
- No search makes navigation harder

**Recommendation**: Use Codeberg Pages or consider Docker deployment if search is needed

### Large Archives (>500MB HTML output)

**Examples**: Large subreddits (>50k posts), multiple medium subreddits

**GitHub Pages**: ❌ Will exceed 1GB repository limit
**Codeberg Pages**: ⚠️ May work but not recommended (best effort service)

**Recommendation**: **Use Docker deployment instead**
- Search becomes essential for usability
- Platform limits make static hosting impractical
- Docker provides better user experience

### Very Large Archives (>5GB HTML output)

**Examples**: r/all archives, multiple large subreddits, complete dumps

**GitHub Pages**: ❌ Not feasible
**Codeberg Pages**: ❌ Not feasible

**Recommendation**: **Docker deployment required**
- Static hosting cannot handle this scale
- Search is critical for navigation
- Self-hosted or VPS deployment only practical option

**Alternative**: Split by subreddit into separate repositories (if search not needed)

---

## GitHub Pages Deployment

### Prerequisites

- GitHub account (free)
- Generated redd-archiver HTML (<500MB recommended)
- Git installed locally

### Step 1: Generate Archive Locally

```bash
# Generate your archive with filtering for size optimization
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit example \
  --comments-file /data/example_comments.zst \
  --submissions-file /data/example_submissions.zst \
  --output /output/example-archive \
  --min-score 100 \
  --min-comments 10

# Result: Captures high-quality content, reduces size by 70-90%
# Your archive is now in: ./output/example-archive/
```

### Step 2: Create GitHub Repository

```bash
# Create new repository on GitHub:
# 1. Go to https://github.com/new
# 2. Repository name: example-archive (or your choice)
# 3. Public repository (required for free Pages)
# 4. Don't initialize with README (we'll push existing content)
# 5. Click "Create repository"
```

### Step 3: Prepare Archive for Deployment

```bash
# Navigate to your generated archive
cd output/example-archive/

# Initialize git repository
git init
git branch -M main

# Important: Add .nojekyll file to disable Jekyll processing
touch .nojekyll

# Add all files
git add .

# Create initial commit
git commit -m "Initial archive deployment"
```

### Step 4: Push to GitHub

```bash
# Add GitHub remote (replace with your repository URL)
git remote add origin https://github.com/username/example-archive.git

# Push to GitHub
git push -u origin main
```

### Step 5: Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** → **Pages** (left sidebar)
3. Under "Source", select branch: **main**
4. Select folder: **/ (root)**
5. Click **Save**

GitHub will build and deploy your site (takes 1-2 minutes).

### Step 6: Access Your Archive

Your archive will be available at:
```
https://username.github.io/example-archive/
```

**Note**: Add `/r/` to path to access subreddit listing:
```
https://username.github.io/example-archive/r/
```

### Custom Domain (Optional)

1. Purchase domain from any registrar
2. Add CNAME file to repository root:
```bash
echo "archive.example.com" > CNAME
git add CNAME && git commit -m "Add custom domain" && git push
```

3. Configure DNS at your registrar:
```
Type: CNAME
Name: archive
Value: username.github.io
```

4. Update GitHub Pages settings with custom domain
5. Enable "Enforce HTTPS" (recommended)

Wait 5-60 minutes for DNS propagation.

---

## Codeberg Pages Deployment

### Prerequisites

- Codeberg account (free, no verification required)
- Generated redd-archiver HTML
- Git installed locally

### Step 1: Generate Archive Locally

```bash
# Generate your archive with filtering (same as GitHub)
docker compose exec reddarchiver-builder python reddarc.py /data \
  --subreddit example \
  --comments-file /data/example_comments.zst \
  --submissions-file /data/example_submissions.zst \
  --output /output/example-archive \
  --min-score 100 \
  --min-comments 10
```

### Step 2: Create Codeberg Repository

**Option A: User-level Pages** (username.codeberg.page):
1. Go to https://codeberg.org/repo/create
2. Repository name: **pages** (must be exactly "pages")
3. Public repository
4. Click "Create Repository"

**Option B: Project-level Pages** (username.codeberg.page/repo):
1. Go to https://codeberg.org/repo/create
2. Repository name: **example-archive** (your choice)
3. Public repository
4. Click "Create Repository"

### Step 3: Push Archive to Codeberg

```bash
# Navigate to generated archive
cd output/example-archive/

# Initialize git repository
git init
git branch -M main

# Add all files
git add .
git commit -m "Initial archive deployment"

# Add Codeberg remote (replace with your repository URL)
git remote add origin https://codeberg.org/username/pages.git
# OR for project pages: https://codeberg.org/username/example-archive.git

# Push to Codeberg
git push -u origin main
```

### Step 4: Access Your Archive

**User-level pages** (if repo named "pages"):
```
https://username.codeberg.page/
```

**Project-level pages**:
```
https://username.codeberg.page/example-archive/
```

**Note**: Codeberg Pages updates may take 5-10 minutes after push.

### Custom Domain (Optional)

1. Create `.domains` file in repository root:
```bash
echo "archive.example.com" > .domains
git add .domains && git commit -m "Add custom domain" && git push
```

2. Configure DNS:
```
Type: CNAME
Name: archive
Value: username.codeberg.page
```

Wait 5-60 minutes for DNS propagation.

---

## Advanced: CI/CD with External Storage

For users who want automated deployment without storing .zst files in repositories.

### GitHub Actions Workflow

**Prerequisites**:
- .zst files stored externally (S3, archive.org, GitHub Releases, etc.)
- Small archive (<100MB HTML output)
- GitHub Actions enabled

**Create `.github/workflows/deploy.yml`**:

```yaml
name: Build and Deploy Archive

on:
  # Trigger manually or on schedule
  workflow_dispatch:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 360  # 6 hour limit

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install PostgreSQL
        run: |
          sudo apt-get update
          sudo apt-get install -y postgresql-client
          sudo systemctl start postgresql

      - name: Download .zst files
        run: |
          # Download from external storage
          # Example: wget https://archive.org/download/your-data.zst
          # Or: aws s3 cp s3://bucket/data.zst ./data.zst
          echo "Download your .zst files here"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Generate archive
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/archive
        run: |
          python reddarc.py /data --output ./output/

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./output
```

**Limitations**:
- 6 hour time limit (large archives will timeout)
- Requires external .zst storage setup
- Complex to debug
- Only practical for small archives

**Recommendation**: Use manual deployment unless you specifically need automation and have external storage infrastructure.

---

## Repository Management

### Keeping Repository Size Small

**Problem**: Git stores all file versions, repository grows with each update

**Solutions**:

1. **Separate Repository per Archive**:
```bash
# Don't mix multiple archives in one repo
# Create separate repos: subreddit1-archive, subreddit2-archive
```

2. **Shallow Clones for Large Archives**:
```bash
# Users can clone without full history
git clone --depth 1 https://github.com/username/archive.git
```

3. **Git LFS for Large Assets** (if needed):
```bash
# Track large images with Git LFS
git lfs track "*.png"
git lfs track "*.jpg"
```

4. **Clean History Periodically** (destructive):
```bash
# WARNING: Rewrites history, breaks existing clones
git checkout --orphan new-main
git add .
git commit -m "Reset history"
git branch -D main
git branch -m main
git push -f origin main
```

### What NOT to Commit

Add to `.gitignore`:
```
# Never commit source data
*.zst

# Never commit database files
*.db
*.sqlite
.postgres-data/

# Never commit logs
*.log

# Never commit environment files
.env
```

---

## Limitations and Trade-offs

### No Search Functionality

Static hosting cannot run the Flask search server. Users must navigate via:

**Available navigation**:
- Subreddit listing pages (`/r/index.html`)
- Individual subreddit pages (`/r/subreddit/index.html`)
- User profile pages (`/u/username/index.html`)
- Date-sorted indexes (`/r/subreddit/index-date/index.html`)
- Comment-sorted indexes (`/r/subreddit/index-comments/index.html`)

**Missing features**:
- Full-text search across all posts
- Search by author, keyword, or date range
- Search result highlighting

**Workaround**: Use browser's built-in search (Ctrl+F) on individual pages

**Better solution**: Use Docker deployment if search is important

### Platform Limitations

**GitHub Pages**:
- 1GB repository size limit (includes git history)
- 100MB max file size
- 100GB/month bandwidth (soft limit)
- Public repositories only (free tier)

**Codeberg Pages**:
- Best effort service (no SLA)
- Maintenance mode (not recommended for critical sites)
- May have undocumented limits
- Can be slow or unavailable

### Update Process

**Static hosting requires manual updates**:

```bash
# 1. Regenerate archive locally (with new data)
python reddarc.py /data --output archive/ --force-rebuild

# 2. Commit and push updates
cd archive/
git add .
git commit -m "Update archive: $(date +%Y-%m-%d)"
git push origin main

# 3. Wait for Pages to rebuild (1-5 minutes)
```

**Docker deployment has automatic updates** via database, static requires full rebuild.

---

## When to Use Static vs Docker

### Use Static Hosting When:
✅ Archive is small (<100MB HTML output)
✅ Search is not important
✅ Infrequent updates (monthly or less)
✅ Zero-cost hosting is priority
✅ Browse-only navigation is acceptable

### Use Docker Deployment When:
✅ Archive is large (>500MB HTML output)
✅ Search functionality is essential
✅ Frequent updates or dynamic content
✅ Professional/production use case
✅ Have server or VPS available

### Decision Matrix

| Your Situation | Recommended Deployment |
|----------------|------------------------|
| Small subreddit (<10k posts), no search needed | GitHub Pages |
| Medium subreddit (10k-50k posts), no search | Codeberg Pages |
| Large subreddit (>50k posts) | Docker (HTTPS or Tor) |
| Need search functionality | Docker (HTTPS or Tor) |
| Homelab sharing | Docker (Tor-only) |
| Public professional archive | Docker (HTTPS) |
| Banned/controversial content | Docker (Tor-only) |

---

## Troubleshooting

### Repository Too Large

**Symptom**: GitHub rejects push (exceeds 1GB)

**Solution**:
```bash
# Check repository size
du -sh .git/

# Solutions:
# 1. Split archive into multiple repositories (by subreddit)
# 2. Use Codeberg Pages (no hard limit)
# 3. Use Docker deployment instead
# 4. Remove large assets (if non-essential)
```

### File Exceeds 100MB

**Symptom**: GitHub rejects push (file >100MB)

**Solution**:
```bash
# Find large files
find . -type f -size +100M

# Solutions:
# 1. Use Git LFS: git lfs track "large-file.html"
# 2. Split file if possible
# 3. Use Codeberg Pages (no specified limit)
# 4. Use Docker deployment
```

### Pages Not Updating

**Symptom**: Changes pushed but site doesn't update

**GitHub Pages**:
```bash
# Check Pages build status
# Go to: https://github.com/username/repo/actions
# Look for "pages build and deployment" workflow

# Force rebuild: Make any commit
git commit --allow-empty -m "Trigger Pages rebuild"
git push
```

**Codeberg Pages**:
```bash
# Codeberg Pages can take 5-10 minutes to update
# Check repository: https://codeberg.org/username/repo
# Verify files are present
# Wait up to 10 minutes after push
```

### 404 Errors on Pages

**Symptom**: https://username.github.io/repo/ returns 404

**GitHub Pages**:
```bash
# Verify Pages is enabled
# Settings → Pages → Check source branch is set

# Verify index.html exists in root
ls -la index.html

# For redd-archiver, main index is at /r/index.html
# Create redirect in root index.html:
echo '<meta http-equiv="refresh" content="0; url=r/">' > index.html
git add index.html && git commit -m "Add redirect" && git push
```

**Codeberg Pages**:
```bash
# Verify index.html exists
# Codeberg requires index.html in repository root
# Same solution as GitHub: add redirect
```

### Search Bar Appears But Doesn't Work

**Symptom**: Search UI present but returns no results

**Cause**: Flask search server not running (static hosting doesn't support backend services)

**Solution**:
```
This is expected behavior for static hosting. Search requires the
Flask search_server.py which cannot run on static platforms.

Options:
1. Accept browse-only navigation (subreddit lists, user pages)
2. Switch to Docker deployment for search functionality
```

**Note**: Consider removing search UI from static exports (future feature)

---

## Repository Structure Best Practices

### Recommended Structure

```
username/
├── example-archive/          # Static HTML repository (public)
│   ├── r/                    # Subreddit pages
│   ├── u/                    # User pages (if generated)
│   ├── static/               # CSS, fonts, assets
│   ├── .nojekyll             # Disable Jekyll (GitHub Pages)
│   ├── .gitignore            # Exclude .zst, .db, .log
│   └── index.html            # Redirect to /r/
│
└── archive-source/           # Private repository (optional)
    ├── data/                 # .zst files (not committed)
    ├── scripts/              # Build scripts
    └── .gitignore            # Exclude .zst, output/
```

### .gitignore for Static Repository

```gitignore
# Source data (never commit)
*.zst

# Database files
*.db
*.sqlite
.postgres-data/

# Logs
*.log

# Environment
.env

# OS files
.DS_Store
Thumbs.db
```

---

## Custom Domain Setup

### GitHub Pages with Custom Domain

**Step 1: Configure GitHub**:
```bash
# Add CNAME file to repository root
echo "archive.example.com" > CNAME
git add CNAME && git commit -m "Add custom domain" && git push
```

**Step 2: Configure DNS**:

At your DNS provider, add CNAME record:
```
Type: CNAME
Name: archive
Value: username.github.io
TTL: 3600
```

**Step 3: Enable HTTPS**:
1. Go to repository Settings → Pages
2. Enter custom domain: `archive.example.com`
3. Wait for DNS check to pass (5-60 minutes)
4. Enable "Enforce HTTPS" checkbox

**Result**: Archive accessible at https://archive.example.com

### Codeberg Pages with Custom Domain

**Step 1: Configure Codeberg**:
```bash
# Add .domains file to repository root
echo "archive.example.com" > .domains
git add .domains && git commit -m "Add custom domain" && git push
```

**Step 2: Configure DNS**:
```
Type: CNAME
Name: archive
Value: username.codeberg.page
TTL: 3600
```

**Step 3: Access**:
Wait 5-60 minutes for DNS propagation, then access at:
```
https://archive.example.com
```

---

## When to Use Docker Instead

If any of these apply, use Docker deployment (HTTPS or Tor):

### Search is Essential
- Archive has >1,000 posts (browsing becomes impractical)
- Users expect search functionality
- Content discovery is important

### Archive Size is Large
- HTML output >500MB
- Exceeds GitHub Pages 1GB limit
- Multiple subreddits or large communities

### Need Dynamic Updates
- Frequent content additions
- Database-backed statistics
- Real-time search results

### Professional/Production Use
- High availability requirements
- Custom search features
- Analytics and monitoring

**Docker deployment provides**:
- Large archive support (tested with hundreds of GB)
- Full-text search (PostgreSQL FTS)
- Server-side processing
- Automated updates

See [docker/README.md](../docker/README.md) for Docker deployment guide.

---

## Comparison: All Deployment Methods

| Feature | Local HTTP | HTTPS (Let's Encrypt) | Tor Hidden Service | GitHub Pages | Codeberg Pages |
|---------|------------|----------------------|-------------------|--------------|----------------|
| **Search** | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **Max Size** | Unlimited | Unlimited | Unlimited | ~500MB | ~500MB |
| **Setup Time** | 2 min | 5 min | 2 min | 10 min | 10 min |
| **Monthly Cost** | $0 | $5-20 (VPS) | $0 | $0 | $0 |
| **Networking Setup** | None | DNS, ports | None | None | None |
| **Updates** | Automated | Automated | Automated | Manual | Manual |
| **Public Access** | ❌ LAN only | ✅ Internet | ⚠️ Tor only | ✅ Internet | ✅ Internet |
| **Best For** | Development | Public archives | Homelab, privacy | Small archives | Small archives |

---

## Additional Resources

- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [Codeberg Pages Documentation](https://docs.codeberg.org/codeberg-pages/)
- [Redd-Archiver Docker Guide](../docker/README.md)
- [Tor Deployment Guide](TOR_DEPLOYMENT.md)

---

**Last Updated**: 2025-12-27
**Recommended Archive Size**: <500MB for static hosting
**Search**: Not available on static deployments
