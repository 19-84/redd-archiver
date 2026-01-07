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

- **Public URL**: Your archive must be accessible via HTTPS
- **API Endpoint**: The `/api/v1/stats` endpoint must work
- **Maintenance**: Commit to reasonable uptime (>90%)

### Optional Enhancements

- Tor hidden service (.onion address)
- IPFS hosting (CID)
- Team affiliation
- Contact information (email, simplex, ect)

---

## For Maintainers: Processing Submissions

### Prerequisites

```bash
# Option 1: Using gh CLI (recommended)
gh auth login

# Option 2: Manual processing
# No additional tools needed
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
# 3. Generate instances/<instance-id>.json
# 4. Display validation checklist
```

#### Method 2: Manual Processing

```bash
# Copy the issue body
# Save to a file: issue-body.txt

python .github/scripts/issue-to-registry.py --from-file issue-body.txt

# Or use clipboard (requires pyperclip):
python .github/scripts/issue-to-registry.py --from-clipboard
```

### Validation Steps

Before merging the registration:

1. **Verify Clearnet URL**
   ```bash
   curl https://archive.example.com
   # Should return HTML
   ```

2. **Verify API Endpoint**
   ```bash
   curl https://archive.example.com/api/v1/stats
   # Should return JSON with required fields
   ```

3. **Check Required Fields**
   - `total_posts` > 0
   - `total_comments` >= 0
   - `total_users` >= 0
   - `subreddits` array not empty

4. **Verify Tor URL (if provided)**
   ```bash
   torify curl http://abc123xyz.onion
   ```

5. **Review JSON Accuracy**
   - Subreddit list correct
   - Maintainer GitHub username valid
   - Team ID matches existing team (if applicable)

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

- ❌ Archive not publicly accessible
- ❌ API endpoint returns errors
- ❌ No content (0 posts)
- ❌ Spam or inappropriate content
- ❌ Duplicate submission (same URL already registered)

**Always comment on the issue explaining the rejection reason.**

---

## Team Registrations

If the submitter specified a team name:

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
  "team_id": "team-identifier",  // optional
  "maintainer": "github_username",
  "registered": "2025-01-23",
  "endpoints": {
    "clearnet": "https://archive.example.com",
    "tor": "http://abc.onion",  // optional
    "ipfs": "https://ipfs.io/ipfs/Qm...",  // optional
    "api": "https://archive.example.com/api/v1/stats"
  },
  "static_metadata": {
    "subreddits": [
      {"name": "privacy", "url": "/r/privacy/"}
    ],
    "hosting": "self-hosted",
    "location": "US-West"  // optional
  },
  "features": ["search", "dark-mode", "mobile", "tor"],
  "contact": {  // optional
    "email": "admin@example.com",
    "matrix": "@user:matrix.org"
  },
  "notes": "Additional information"  // optional
}
```

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
    "matrix": "@team:matrix.org"
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

### Issue: API endpoint returns 404

**Solution**: Ask submitter to:
1. Check that search server is running
2. Verify Flask-CORS is installed
3. Ensure API blueprint is registered
4. Check Docker container logs

### Issue: Subreddit list empty

**Solution**: Instance hasn't imported any data yet. Ask submitter to complete import before registering.

### Issue: Script fails to parse issue

**Solution**:
1. Check that issue used the correct template
2. Verify all required fields are filled
3. Try manual JSON creation as fallback

---

## Questions?

- Open an issue with the `registry` label
- Contact maintainers via Simplex/Email
- Check the main README for additional documentation
