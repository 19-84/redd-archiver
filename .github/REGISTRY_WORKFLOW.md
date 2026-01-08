# Registry Submission Workflow

This document explains how to submit and process Redd Archiver instance registrations.

## For Instance Operators: Submitting Your Archive

### Step 1: Create a GitHub Issue

1. Go to the Issues tab
2. Click "New Issue"
3. Select "Register Archive Instance" template
4. Fill out the form with your archive details
5. Submit the issue

**That's it!** No need to edit JSON files manually. A maintainer will process your submission.

### What You Need

- **At least one URL**: Your archive must be accessible via HTTPS (clearnet) or Tor (.onion)
- **API Endpoint**: The `/api/v1/stats` endpoint must work
- **Maintenance**: Commit to reasonable uptime (>90%)

### Auto-Populated Fields

The following fields are automatically fetched from your `/api/v1/stats` endpoint:

| Field | Source | Override |
|-------|--------|----------|
| Instance name | `instance.name` | Form field (optional) |
| Team ID | `instance.team_id` | Form field (optional) |
| Tor URL | `instance.tor_url` | Form field (optional) |
| Subreddits | `content.subreddits[]` | Always from API |
| Features | `features.tor`, API availability, user pages | Auto-detected |
| User Pages | `/api/v1/users` endpoint check | Form checkbox (optional) |

### Optional Enhancements

- Tor hidden service (.onion address)
- IPFS hosting (CID)
- Team affiliation
- Preferred contact method (Simplex, Matrix, Telegram, email, etc.)
- Server region and country (for redundancy tracking)
- User pages feature checkbox

### Tor-Only Instances

If your archive is only accessible via Tor (no clearnet URL):

1. Leave the "Clearnet URL" field blank
2. Enter your `.onion` URL in the "Tor Hidden Service URL" field
3. The maintainer will use `torify curl` to validate your API

**Privacy Protection:** Geolocation fields (region/country) are automatically excluded for Tor-only instances to protect operator privacy.

**Note:** Tor-only instances are fully supported. The script will fetch your API via Tor.

---

## For Maintainers: Processing Submissions

### Prerequisites

```bash
# Required: gh CLI for fetching issues
gh auth login

# Required for tor-only instances: Tor and torify
# Ubuntu/Debian:
sudo apt install tor torsocks

# Verify torify works:
torify curl -s https://check.torproject.org/api/ip
```

### Processing a Submission

#### Method 1: Automated (gh CLI)

```bash
# Navigate to the repository root
cd redd-archiver

# Run the conversion script
python .github/scripts/issue-to-registry.py --issue-number 123

# This will:
# 1. Fetch the issue from GitHub
# 2. Parse the form fields
# 3. Fetch /api/v1/stats from the instance (auto-detects Tor)
# 4. Auto-populate instance name, team_id, subreddits, features
# 5. Generate instances/<instance-id>.json
# 6. Display data sources (form vs API)
# 7. Display validation checklist
```

#### Method 2: Manual Processing

```bash
# Copy the issue body
# Save to a file: issue-body.txt

python .github/scripts/issue-to-registry.py --from-file issue-body.txt

# Or use clipboard (requires pyperclip):
python .github/scripts/issue-to-registry.py --from-clipboard
```

### Script Output

The script will show:

1. **API Data Summary**: Instance name, team ID, Tor URL, subreddit count, post/comment counts
2. **Data Sources**: Which fields came from the form vs API
3. **Generated JSON**: The registry entry to be created
4. **Validation Checklist**: Manual checks to perform

Example output:
```
📊 API Data Summary:
   Instance name: Privacy Archive
   Team ID: privacy-team
   Tor URL: http://abc123.onion
   Subreddits: 5
   Total posts: 125000
   Total comments: 890000

📋 DATA SOURCES:
Instance name: Privacy Archive
   └─ Source: API
Team ID: privacy-team
   └─ Source: API
Subreddits: 5
   └─ Source: API
Features: ['api', 'tor']
   └─ Source: API (auto-detected)
```

### Validation Steps

Before merging the registration:

1. **Review API Data**
   - The script already fetched and displayed the API response
   - Verify subreddit count makes sense
   - Check total posts/comments > 0

2. **Verify Clearnet URL** (if provided)
   ```bash
   curl https://archive.example.com
   # Should return HTML
   ```

3. **Verify Tor URL** (if provided)
   ```bash
   torify curl http://abc123xyz.onion
   # Should return HTML
   ```

4. **Verify IPFS** (if provided)
   ```bash
   curl https://ipfs.io/ipfs/<CID>
   # Should return content
   ```

5. **Review JSON Accuracy**
   - Instance name is appropriate
   - Maintainer GitHub username valid
   - Team ID matches existing team (if applicable)
   - Subreddit list looks correct

### Approving the Registration

```bash
# Review the generated JSON
cat instances/<instance-id>.json

# If everything checks out:
git add instances/<instance-id>.json
git commit -m "registry: add <Instance Name>"
git push

# Close the issue with a comment:
# "✓ Registered! Your instance will appear on the leaderboard within 24 hours."
```

### Rejection Reasons

Common reasons to reject a submission:

- ❌ Archive not publicly accessible (API fetch failed)
- ❌ API endpoint returns errors or invalid JSON
- ❌ No content (0 posts/0 subreddits)
- ❌ Spam or inappropriate content
- ❌ Duplicate submission (same URL already registered)
- ❌ Neither clearnet nor Tor URL provided

**Always comment on the issue explaining the rejection reason.**

---

## Team Registrations

If the submitter specified a team name (or API returned team_id):

1. Check if `teams/<team-id>.json` exists
2. If not, create it:

```json
{
  "team_id": "privacy-advocates",
  "name": "Privacy Advocates Network",
  "description": "Brief description",
  "founded": "2025-01-23",
  "members": ["github_username"],
  "archives": ["<instance-id>"]
}
```

3. If team exists, add the instance to `archives` array
4. Add submitter to `members` array if not present

---

## Data Source Submissions

When a user submits a new data source via the template:

### Processing Workflow

1. **Verify Data Accessibility**
   - Check all download links work
   - Verify file sizes and formats match description
   - Test sample data structure

2. **Add to Data Catalog**
   - Create entry in `docs/DATA_CATALOG.md`
   - Include platform type, size, format, download links
   - Add urgency/risk indicators

3. **Tag for Implementation**
   - Label as `enhancement` if new platform support needed
   - Link to relevant importer documentation
   - Estimate implementation complexity

4. **Update README**
   - Add to data sources table if major dataset
   - Update platform support section if new type

---

## Registry Structure

```
instances/
├── privacy-main.json
├── privacy-archive.json
└── ...

teams/
├── privacy-advocates.json
├── academic-research.json
└── ...
```

### Instance JSON Format

```json
{
  "instance_id": "unique-identifier",
  "name": "Human Readable Name",
  "team_id": "team-identifier",
  "maintainer": "github_username",
  "registered": "2025-01-23",
  "endpoints": {
    "clearnet": "https://archive.example.com",
    "tor": "http://abc.onion",
    "ipfs": "https://ipfs.io/ipfs/Qm...",
    "api": "https://archive.example.com/api/v1/stats"
  },
  "static_metadata": {
    "subreddits": [
      {"name": "privacy", "url": "/r/privacy/"}
    ],
    "hosting": "Self-hosted (VPS/dedicated server)",
    "location": "North America",
    "country": "United States"
  },
  "features": ["api", "tor", "user-pages"],
  "contact": {
    "preferred": "@user:matrix.org"
  },
  "notes": "Additional information"
}
```

**Notes:**
- `clearnet` is optional for tor-only instances
- `team_id` is optional
- `contact` is optional
- `notes` is optional
- `location` uses regions: North America, South America, Europe, Africa, Asia, Oceania
- `country` is optional (more specific than region)
- `features` are auto-detected: `api` (always), `tor` (if tor_url present), `user-pages` (if users endpoint works)
- **Tor-only instances**: `location` and `country` are automatically excluded for privacy

### Team JSON Format

```json
{
  "team_id": "unique-team-id",
  "name": "Team Name",
  "description": "What the team does",
  "founded": "2025-01-23",
  "members": ["username1", "username2"],
  "contact": {
    "website": "https://example.com",
    "preferred": "@team:matrix.org"
  },
  "archives": ["instance-id-1", "instance-id-2"]
}
```

---

## Leaderboard Updates

The leaderboard updates automatically via:

1. **Local Script** (manual run):
   ```bash
   python scripts/update_leaderboard.py
   ```

2. **Scheduled Job** (if using CI):
   - Runs every 6 hours
   - Checks all instance APIs
   - Updates `leaderboard/index.html`

---

## Troubleshooting

### Issue: API fetch fails for clearnet URL

**Solution**: Check that:
1. The URL is correct and accessible
2. HTTPS certificate is valid
3. Search server is running
4. API blueprint is registered

### Issue: API fetch fails for Tor URL

**Solution**: Check that:
1. `torify` is installed (`sudo apt install torsocks`)
2. Tor service is running (`sudo systemctl start tor`)
3. The .onion URL is correct
4. Try: `torify curl -s <onion-url>/api/v1/stats`

### Issue: Subreddit list empty

**Solution**: Instance hasn't imported any data yet. Ask submitter to complete import before registering.

### Issue: Script fails to parse issue

**Solution**:
1. Check that issue used the correct template
2. Verify at least one URL is provided
3. Try with `--skip-api` flag for testing (not recommended for production)

### Issue: No instance name from API

**Solution**: The instance operator hasn't configured `REDDARCHIVER_SITE_NAME`. Ask them to set this environment variable, or have them provide a name in the form.

---

## Questions?

- Open an issue with the `registry` label
- Contact maintainers via Simplex/Matrix
- Check the main README for additional documentation
