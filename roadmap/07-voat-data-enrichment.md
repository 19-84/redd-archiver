# Feature 7: Voat Data Enrichment

**Status:** In progress (Phases 1–3 implemented)
**Last updated:** 2026-06-11

**Goal:** Import the full breadth of Voat metadata from the Voat SQL archive to enrich Voat archives with subverse descriptions, moderator lists, user profiles, post flair, post thumbnails, and subscriber history that exist in the SQL dumps but are not currently imported.

**Problem:** The current Voat importer handles only 2 of 8 available SQL tables (`submission` + `comment`). Six additional tables containing subverse metadata, user profiles, moderator relationships, subscriber history, post flair, and user badges are unused. Additionally, 14GB of already-archived post thumbnails are not integrated. Voat shut down permanently in December 2020 — this data cannot be re-collected, making comprehensive archival especially important.

---

## Data Source

The Voat SQL archive (~21GB) was assembled from the searchvoat.co database backup. It contains the complete Voat dataset (2013–2020) as MariaDB SQL dumps.

### Currently imported (by existing importer)

| File | Size | Records | Status |
|---|---|---|---|
| `submission.sql.gz` | 634 MB | ~3.8M posts | Imported (submissions only) |
| `comment.sql.gz` | 2.9 GB | ~24.1M comments | Imported |

### Not yet imported — metadata tables

Packaged in `voat-sql-tables.tar` (22MB total):

| File | Size | Records (est.) | Contents |
|---|---|---|---|
| `subverse.sql.gz` | 3.5 MB | ~22,460 | Community metadata: descriptions, sidebars, moderators, creation info |
| `user.sql.gz` | 4.7 MB | ~5,000+ | User profiles: bios, karma, registration dates, avatars |
| `subverseModerator.sql.gz` | 797 KB | ~54,000 | Moderator relationships with permission levels and date ranges |
| `subverseSubscribers.sql.gz` | 3.7 MB | ~660,000 | Daily subscriber count time-series per subverse |
| `submissionAttribute.sql.gz` | 2.6 MB | ~1,043,000 | Post flair labels and attributes |
| `userBadge.sql.gz` | 1.1 MB | ~71,000 | User achievement badges |
| `top50.sql.gz` | 5.6 MB | ~528,000 | Pre-computed top post rankings by time period |

### Not yet imported — media files

| File | Size | Contents |
|---|---|---|
| `thumbnails.tgz` | 14 GB | Post thumbnail images (UUID-named JPG/PNG in nested directories) |
| `images.tgz` | 91 MB | User avatars and screenshots |
| `www.tgz` | 9.2 MB | SearchVoat web assets (CSS, fonts, branding) |

### Not yet imported — processed metadata

| File | Size | Contents |
|---|---|---|
| `subverses.json` | 14 MB | 22,585 subverse profiles with archive priority scores, NSFW flags, activity metrics |
| `split_metadata.json` | 4 MB | Split operation statistics for 17,637 subverses |
| `post_to_subverse_mapping.json` | 86 MB | Comment-to-subverse index (used internally for splitting) |

Format: MariaDB SQL dumps (`.sql.gz`), JSON, and compressed tar archives. All SQL uses `utf8mb4_unicode_520_ci` collation with backslash escaping.

---

## Available Fields

### Subverse metadata (`subverse.sql.gz` — 20 columns)

Verified from actual CREATE TABLE and INSERT statements:

```sql
CREATE TABLE `subverse` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(21) NOT NULL,              -- Community name
  `createdBy` varchar(21) NOT NULL,         -- Founder username
  `creationDate` datetime NOT NULL,         -- When community was created
  `description` text NOT NULL,              -- Short tagline
  `formattedSidebar` mediumtext NOT NULL,   -- Pre-rendered HTML sidebar (rules, about)
  `isAdult` tinyint(4) NOT NULL,            -- NSFW flag
  `isAnonymized` tinyint(4) NOT NULL,       -- Anonymous-only submissions
  `isDefault` tinyint(4) NOT NULL,          -- Default subverse
  `isDeleted` tinyint(4) NOT NULL,          -- Deleted community
  `moderators` mediumtext NOT NULL,         -- Semicolon-separated usernames
  `sidebar` mediumtext NOT NULL,            -- Raw markdown sidebar
  `subscriberCount` int(11) NOT NULL,       -- Subscriber count at time of scrape
  `title` text NOT NULL,                    -- Display title (e.g., "/v/technology")
  `type` varchar(10) NOT NULL,              -- Community type (link, text, etc.)
  `lastFetched` datetime NOT NULL,
  `fetchCount` int(11) NOT NULL,
  `hideTop50` tinyint(4) NOT NULL,
  `lastPosted` datetime DEFAULT NULL,       -- Last activity date
  `isUnauthorised` tinyint(4) NOT NULL
);
```

**Key advantage over Reddit (Feature 6):** `formattedSidebar` is **pre-rendered HTML** from Voat's own rendering pipeline. No markdown-to-HTML conversion needed. Feature 6's Reddit data requires `markdown` + `bleach` for sidebar rendering; Feature 7 Phase 1 only needs `bleach` for XSS sanitization of the existing HTML.

**`moderators` field format:** Semicolon-separated usernames. Verified from actual data:
- Single moderator: `'DaMan123456'`
- Multiple moderators: `'DerpyPigSauce;T4C0M4ST3R'`
- Empty: `''` (no moderators)

The `subverseModerator` table provides more structured moderator data (permission levels, date ranges).

### User profiles (`user.sql.gz` — 31 columns)

```sql
CREATE TABLE `user` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `userName` varchar(40) NOT NULL,
  `bio` text NOT NULL,                           -- User biography
  `commentPointsDownCount` int(11) NOT NULL,
  `commentPointsSum` int(11) NOT NULL,           -- Comment karma (net)
  `commentPointsUpCount` int(11) NOT NULL,
  `commentVotingDownCount` int(11) NOT NULL,
  `commentVotingSum` int(11) NOT NULL,
  `commentVotingUpCount` int(11) NOT NULL,
  `generationDate` datetime NOT NULL,
  `profilePicture` text NOT NULL,                -- Avatar URL (voat.co CDN)
  `registrationDate` datetime NOT NULL,          -- Account creation date
  `submissionPointsDownCount` int(11) NOT NULL,
  `submissionPointsSum` int(11) NOT NULL,        -- Post karma (net)
  `submissionPointsUpCount` int(11) NOT NULL,
  `submissionVotingDownCount` int(11) NOT NULL,
  `submissionVotingSum` int(11) NOT NULL,
  `submissionVotingUpCount` int(11) NOT NULL,
  `lastFetched` datetime NOT NULL,
  `fetchCount` int(11) NOT NULL,
  `hideTop50` tinyint(4) NOT NULL,
  `isBot` tinyint(4) NOT NULL,                   -- Bot flag
  `isDeleted` tinyint(4) NOT NULL,               -- Deleted account
  `noPing` tinyint(4) NOT NULL,
  `noCrosslinker` tinyint(4) NOT NULL,
  `noCrosslinkee` tinyint(4) NOT NULL,
  `fetchOldCommentsDate` datetime DEFAULT NULL,
  `fetchOldCommentsPage` int(11) NOT NULL,
  `fetchOldCommentsLast` datetime DEFAULT NULL,
  `fetchOldCommentsError` text,
  `svpassword` text NOT NULL                     -- ALWAYS EMPTY — must be excluded
);
```

**Security note:** The `svpassword` field is always an empty string in the data but MUST be explicitly excluded from storage. Add to `SENSITIVE_FIELDS` constant.

### Moderator relationships (`subverseModerator.sql.gz` — 6 columns)

```sql
CREATE TABLE `subverseModerator` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(20) NOT NULL,
  `subverse` varchar(20) NOT NULL,
  `level` varchar(10) NOT NULL,     -- Permission level (e.g., "owner", "mod")
  `firstDate` datetime NOT NULL,     -- When became moderator
  `lastDate` datetime NOT NULL       -- Last activity as moderator
);
```

### Subscriber time-series (`subverseSubscribers.sql.gz` — 4 columns)

```sql
CREATE TABLE `subverseSubscribers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `subverse` varchar(20) NOT NULL,
  `date` date NOT NULL,
  `count` int(11) NOT NULL
);
```

Daily subscriber counts per subverse. ~660K records. Enables subscriber growth charts in dynamic mode.

### Post flair (`submissionAttribute.sql.gz` — 7 columns)

```sql
CREATE TABLE `submissionAttribute` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `submissionid` int(11) NOT NULL,
  `attributeid` int(11) NOT NULL,
  `cssClass` varchar(100) NOT NULL,
  `type` varchar(100) NOT NULL,      -- e.g., "linkflairlabel"
  `name` text NOT NULL,              -- e.g., "NSFW", "Politics", "Females"
  `description` text NOT NULL
);
```

Contains flair labels that can be mapped to the existing flair system in redd-archiver. Enables Feature 1 flair index for Voat archives.

### User badges (`userBadge.sql.gz` — 8 columns)

```sql
CREATE TABLE `userBadge` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(40) NOT NULL,
  `badgeid` int(11) NOT NULL,
  `type` varchar(100) NOT NULL,
  `creationdate` datetime NOT NULL,
  `graphic` text NOT NULL,           -- Badge image URL
  `name` text NOT NULL,              -- Badge name
  `description` text NOT NULL        -- Badge description
);
```

### Top post rankings (`top50.sql.gz` — 10 columns)

```sql
CREATE TABLE `top50` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `type` varchar(20) NOT NULL,
  `key` varchar(100) NOT NULL,
  `date` date NOT NULL,
  `period` varchar(20) NOT NULL,     -- day, week, month, year
  `rank` int(11) NOT NULL,
  `countlow` int(11) NOT NULL,
  `counthigh` int(11) NOT NULL,
  `hide` tinyint(4) NOT NULL,
  `submissionid` int(11) NOT NULL
);
```

### Priority tiers

| Tier | Tables | Value | Effort |
|---|---|---|---|
| **Tier 1: High value** | `subverse`, `user` | Subverse about pages, user bios, subscriber counts | Medium |
| **Tier 2: Enrichment** | `subverseModerator`, `submissionAttribute`, `subverseSubscribers` | Moderator credits, post flair, subscriber history | Medium |
| **Tier 3: Nice-to-have** | `userBadge`, `top50` | User achievements, historical rankings | Small |

---

## What This Data Enables

### UI features

| Data | Feature | Current Gap |
|---|---|---|
| `subverse.description` + `formattedSidebar` | Subverse "about" page with sidebar content and rules | No sidebar anywhere in Voat archives |
| `subverse.subscriberCount` | Historical subscriber count on dashboard cards | Only post/comment counts shown |
| `subverse.createdBy` + `creationDate` | Community founder and creation date | Not available |
| `subverse.moderators` + `subverseModerator` | Moderator list with permission levels on about page | No moderator info preserved |
| `user.bio` | User biography on profile pages | User pages show only activity stats |
| `user.registrationDate` | "Member since" date on user pages | Not available |
| `user.profilePicture` | Avatar display on user pages | No avatars |
| `user.commentPointsSum` + `submissionPointsSum` | Source-platform karma (vs. archive-computed stats) | Only archive-derived stats |
| `submissionAttribute` (flair) | Flair labels on post cards, flair index (Feature 1) | No Voat flair data imported |
| `subverseSubscribers` | Subscriber growth charts (dynamic mode) | No historical subscriber data |
| Post thumbnails (14GB) | Thumbnail images on index pages and post pages | Text-only post listings |
| `subverses.json` priority scores | Prioritized import ordering, community importance ranking | No priority data |

### Cross-feature synergies

- **Feature 1 (flair index):** `submissionAttribute` flair data enables flair indexing for Voat archives. Currently Feature 1 only works with Reddit flair in `json_data`.
- **Feature 2 (dynamic mode):** User profile pages with bios are most valuable in dynamic mode (rendered on-the-fly). Subscriber growth charts require dynamic mode for interactive display.
- **Feature 4 (visual themes):** No Voat equivalent of per-subreddit branding colors (Voat used a site-wide theme). The `www.tgz` CSS files could inspire a "Voat classic" theme.
- **Feature 5 (Unicode):** Voat was primarily English but some subverse sidebars contain non-English content. The `simple` regconfig fix from Feature 5 Phase 1 helps.
- **Feature 6 (shared schema):** Feature 7 shares the `subreddit_metadata` table (with `platform='voat'`) and the same about/rules page templates.

### Archival/preservation value

Voat shut down permanently in December 2020. This SQL dump from searchvoat.co is one of the only comprehensive records of:
- What communities existed and what their stated purposes were
- Who moderated them and what their policies were
- User bios and community identities
- Visual context (thumbnails, avatars) that no longer exists on any live server
- Historical growth patterns (subscriber time-series)

---

## Proposed Schema Additions

### Reuse: `subreddit_metadata` table (shared with Feature 6)

Feature 6's spec proposes the (new) `subreddit_metadata` table with `PRIMARY KEY (subreddit, platform)`. Voat subverse data maps to this table with `platform='voat'`:

| F6 Column | Voat Source | Notes |
|---|---|---|
| `display_name` | `subverse.name` | Community name |
| `title` | `subverse.title` | Display title (e.g., "/v/technology") |
| `description` | `subverse.sidebar` | Raw markdown sidebar |
| `description_html` | `subverse.formattedSidebar` | **Already rendered** — just sanitize |
| `public_description` | `subverse.description` | Short tagline |
| `subscribers` | `subverse.subscriberCount` | At time of scrape |
| `created_utc` | `subverse.creationDate` | Converted to Unix timestamp |
| `over_18` | `subverse.isAdult` | NSFW flag |
| `subreddit_type` | — (do **not** map `subverse.type` here) | F6's `subreddit_type` is an *access level* (public/private/restricted/archived); Voat's `type` is a *content type* (link/text — see line 79), a different concept. Leave NULL for Voat, or derive from a Voat private/restricted flag if one exists. Voat's `type` is preserved in `raw_json`. |
| `raw_json` | Full row as JSONB | Includes all 20 columns (incl. the unmapped `type`) |

**New columns needed on `subreddit_metadata`:**

```sql
ALTER TABLE subreddit_metadata ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE subreddit_metadata ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE subreddit_metadata ADD COLUMN IF NOT EXISTS moderators_json JSONB;
```

- `created_by`: Voat records subverse founders; Reddit does not.
- `is_deleted`: Voat tracks deleted communities; Reddit's Arctic Shift dump doesn't include this.
- `moderators_json`: Structured moderator data from both the `moderators` field (semicolon-separated) and `subverseModerator` table (with levels and dates). Stored as JSONB array: `[{"username": "...", "level": "owner", "first_date": "...", "last_date": "..."}]`

These columns are NULL for Reddit rows — no migration impact.

### New: `user_metadata` table

```sql
CREATE TABLE IF NOT EXISTS user_metadata (
    username TEXT NOT NULL,
    platform TEXT DEFAULT 'voat' NOT NULL,

    -- Profile
    bio TEXT,
    registration_date BIGINT,              -- Unix timestamp
    profile_picture TEXT,                   -- URL or local path

    -- Karma (source-platform values, not archive-computed)
    comment_karma INTEGER,                 -- commentPointsSum
    submission_karma INTEGER,              -- submissionPointsSum

    -- Flags
    is_bot BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,

    -- Full data
    raw_json JSONB,                        -- All columns except svpassword

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (username, platform)
);
```

**Relationship to existing `users` table:** The existing `users` table stores archive-computed statistics (post counts, comment counts, activity dates). `user_metadata` stores source-platform metadata (bio, karma, registration date). They are peers, not parent-child — analogous to `subreddit_statistics` vs `subreddit_metadata`.

### New: `subscriber_history` table

```sql
CREATE TABLE IF NOT EXISTS subscriber_history (
    id SERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'voat' NOT NULL,
    date DATE NOT NULL,
    count INTEGER NOT NULL,
    UNIQUE (subreddit, platform, date)
);

CREATE INDEX IF NOT EXISTS idx_subscriber_history_sub
    ON subscriber_history (subreddit, platform, date);
```

### Flair data: no new table

`submissionAttribute` flair data maps to the existing `json_data` JSONB column on `posts`. During enrichment, update matching posts:

```sql
UPDATE posts SET json_data = jsonb_set(json_data, '{link_flair_text}', to_jsonb(flair_name))
WHERE id = submission_id AND platform = 'voat';
```

This aligns with how Reddit flair data is stored and keeps the flair index (Feature 1) working across platforms.

---

## VoatSQLParser Extensions

The existing `VoatSQLParser.COLUMN_MAPS` dict (`core/importers/voat_sql_parser.py:30`) has entries for `"submission"` (27 columns) and `"comment"` (22 columns). New entries needed:

```python
COLUMN_MAPS = {
    "submission": [...],   # existing 27 columns
    "comment": [...],      # existing 22 columns
    # NEW entries:
    "subverse": [
        "id", "name", "createdBy", "creationDate", "description",
        "formattedSidebar", "isAdult", "isAnonymized", "isDefault",
        "isDeleted", "moderators", "sidebar", "subscriberCount",
        "title", "type", "lastFetched", "fetchCount", "hideTop50",
        "lastPosted", "isUnauthorised",
    ],
    "user": [
        "id", "userName", "bio", "commentPointsDownCount",
        "commentPointsSum", "commentPointsUpCount",
        "commentVotingDownCount", "commentVotingSum",
        "commentVotingUpCount", "generationDate", "profilePicture",
        "registrationDate", "submissionPointsDownCount",
        "submissionPointsSum", "submissionPointsUpCount",
        "submissionVotingDownCount", "submissionVotingSum",
        "submissionVotingUpCount", "lastFetched", "fetchCount",
        "hideTop50", "isBot", "isDeleted", "noPing",
        "noCrosslinker", "noCrosslinkee", "fetchOldCommentsDate",
        "fetchOldCommentsPage", "fetchOldCommentsLast",
        "fetchOldCommentsError", "svpassword",
    ],
    "subverseModerator": [
        "id", "username", "subverse", "level", "firstDate", "lastDate",
    ],
    "subverseSubscribers": [
        "id", "subverse", "date", "count",
    ],
    "submissionAttribute": [
        "id", "submissionid", "attributeid", "cssClass", "type",
        "name", "description",
    ],
    "userBadge": [
        "id", "username", "badgeid", "type", "creationdate",
        "graphic", "name", "description",
    ],
}
```

The existing `stream_rows()` method (`voat_sql_parser.py:98`) works unchanged once the new tables are registered — it handles any `table_name` **that has a `COLUMN_MAPS` entry** (it raises `ValueError: Unknown table` otherwise, `voat_sql_parser.py:112`). So the only code change is adding the `COLUMN_MAPS` entries; the parser logic itself is untouched. The SQL file must contain `INSERT INTO \`{table_name}\`` statements.

---

## VoatImporter Extensions

New methods on `VoatImporter` (`core/importers/voat_importer.py`):

| Method | Purpose | Filter |
|---|---|---|
| `stream_subverses(file_path, filter_communities)` | Stream subverse metadata | By tracked subverse names |
| `stream_users(file_path, filter_usernames)` | Stream user profiles | By tracked usernames |
| `stream_moderators(file_path, filter_communities)` | Stream moderator records | By tracked subverse names |
| `stream_subscribers(file_path, filter_communities)` | Stream subscriber time-series | By tracked subverse names |
| `stream_flair(file_path, filter_submissions)` | Stream flair attributes | By tracked submission IDs |
| `stream_badges(file_path, filter_usernames)` | Stream user badges | By tracked usernames |

Each method:
1. Calls `VoatSQLParser.stream_rows()` with the appropriate table name
2. Applies the filter (skip records not matching tracked entities)
3. Normalizes Voat-specific fields to the common schema
4. Yields dicts ready for database insertion

**Security:** A `SENSITIVE_FIELDS` constant strips `svpassword` before yielding user records.

**File access:** The metadata SQL files are in `voat-sql-tables.tar`. The CLI must either:
- Accept a directory path (user pre-extracts the tar), or
- Accept the tar path and extract to a temp directory automatically

Recommendation: Accept a directory path. Keep it simple. Document the extraction step.

---

## CLI Interface

```bash
# Auto-detect and import all Voat metadata from extracted tar directory
python reddarc.py --enrich-voat /path/to/voat-sql-tables/

# Individual file overrides
python reddarc.py --enrich-voat-subverses /path/to/subverse.sql.gz
python reddarc.py --enrich-voat-users /path/to/user.sql.gz
python reddarc.py --enrich-voat-moderators /path/to/subverseModerator.sql.gz
python reddarc.py --enrich-voat-flair /path/to/submissionAttribute.sql.gz

# Combined with regular Voat import
python reddarc.py /data/voat/ --subverse technology \
  --comments-file /data/technology_comments.sql.gz \
  --submissions-file /data/technology_submissions.sql.gz \
  --enrich-voat /data/voat-sql-tables/ \
  --output /output/

# Thumbnail integration (Phase 4)
python reddarc.py --enrich-voat /data/voat-sql-tables/ \
  --voat-thumbnails /data/thumbnails/ \
  --output /output/

# Combined with export
python reddarc.py --enrich-voat /data/voat-sql-tables/ \
  --export-from-database --output /var/www/html/
```

**Auto-detection:** `--enrich-voat` scans the directory for files matching:
- `subverse.sql.gz` → subverse metadata import
- `user.sql.gz` → user profile import
- `subverseModerator.sql.gz` → moderator import
- `subverseSubscribers.sql.gz` → subscriber history import
- `submissionAttribute.sql.gz` → flair attribute import
- `userBadge.sql.gz` → badge import
- `top50.sql.gz` → rankings import

**Relationship to Feature 6's `--enrich`:** Feature 6's `--enrich` auto-detects `subreddits_*.zst` (Reddit Arctic Shift dumps). Feature 7's `--enrich-voat` auto-detects `*.sql.gz` (Voat SQL dumps). They do not conflict. Both can target the same database (different `platform` values in shared tables).

**Behavior:** Only imports data for subverses/users already tracked in the database (same filter-by-tracked pattern as Feature 6 and Feature 3). Streaming architecture — constant memory regardless of table size.

---

## Codebase Integration Map

### Where metadata plugs into existing code

#### 1. Dashboard homepage

**Current flow:** `write_index_jinja2()` (`html_modules/html_dashboard_jinja.py:22`) → `get_all_subreddit_statistics_from_db()` → `prepare_dashboard_card_data()` (`html_modules/dashboard_helpers.py:159`) → renders `pages/index.html`.

**Enrichment:** Same path as Feature 6. After fetching statistics, also call `get_all_subreddit_metadata()`. Each dashboard card for Voat subverses gains:
- `description` (short tagline) as subtitle
- `subscriberCount` as historical context
- `createdBy` and `creationDate` for community age
- `isAdult` warning indicator

#### 2. Subverse index pages

**Current flow:** `write_subreddit_pages_jinja2()` (`html_modules/html_pages_jinja.py:20`; the context dict is assembled around line 175) builds context with `subreddit`, `posts`, `page_num`, `total_pages`, stats — then renders `pages/subreddit.html`.

**Enrichment:** Same approach as Feature 6. Fetch `get_subreddit_metadata(subverse, 'voat')`, add `description_html` for "About this community" section.

#### 3. User profile pages

**Current flow:** User pages (`templates_jinja2/pages/user.html`) display username, post count, comment count, activity period.

**Enrichment (Voat-specific):** After fetching computed stats, also call `get_user_metadata(username, 'voat')`. Add to context:
- `bio` text
- `registration_date` ("Member since")
- `comment_karma`, `submission_karma` (source-platform values)
- `is_bot` badge
- `profile_picture` (if avatar archival is implemented)

#### 4. Post cards with flair

**Current flow:** Post cards (`templates_jinja2/components/post_card.html`) display title, score, author, date. Flair display exists for Reddit posts (from `json_data.link_flair_text`).

**Enrichment:** After flair import (Phase 3), Voat post cards display flair labels from the same `json_data.link_flair_text` field. No template changes needed — the existing flair display logic works for both platforms.

#### 5. REST API

**Current:** `GET /api/v1/subreddits/<name>` (`api/routes.py:2055`) queries only `subreddit_statistics`.

**Enrichment:** Same approach as Feature 6. Merge `subreddit_metadata` into response. For `GET /api/v1/users/<username>`, merge `user_metadata` (bio, karma, registration date).

#### 6. New templates needed

| Template | Page | Content | Shared with F6? |
|---|---|---|---|
| `pages/subreddit_about.html` | `v/{sub}/about/` | Sidebar HTML, creation date, subscribers, moderators | Yes — same template, platform-aware |

No additional templates needed beyond Feature 6's about page. The moderator list and user bio sections are conditional blocks within existing templates.

#### 7. Export pipeline placement

Same location as Feature 6 — new pages slot into `process_subreddit_database_backed()` (`core/write_html.py:897`):

```
process_subreddit_database_backed()
  ├─ write_link_pages_jinja2()               # Individual post pages (existing)
  ├─ write_subreddit_pages_from_database()    # Subreddit indexes (existing)
  ├─ write_subreddit_about_jinja2()          # About page (Feature 6, shared)
  └─ (statistics calculation)
```

#### 8. Database methods needed (in `core/postgres_database.py`)

Feature 6 defines methods for `subreddit_metadata`. Feature 7 adds:

| Method | Purpose |
|---|---|
| `save_user_metadata(username, platform, metadata_dict)` | Upsert user metadata record |
| `get_user_metadata(username, platform)` | Fetch single user metadata |
| `save_moderators(subreddit, platform, moderators_list)` | Store moderator JSONB on `subreddit_metadata` |
| `save_subscriber_history(subreddit, platform, date, count)` | Insert subscriber data point |
| `get_subscriber_history(subreddit, platform)` | Fetch time-series for charting |
| `update_post_flair_batch(updates_list)` | Batch-update `json_data` with flair labels |

---

## Frontend Decisions

Shared decisions (navigation, dashboard cards, subreddit index, CSS strategy) are documented in [Feature 6 > Frontend Decisions](06-subreddit-metadata-enrichment.md#frontend-decisions). Voat-specific decisions below.

### User page: Enriched header

User metadata (bio, registration date, platform karma, bot flag) renders in the existing user page header block (`pages/user.html` lines 59-69). No sidebar or layout change.

Layout order:
- Avatar (conditional — Voat CDN is dead, only shown if locally archived)
- Username (existing)
- Activity stats (existing: posts, comments, active subverses)
- Bio text (conditional, below stats)
- Metadata row: "Member since {date} · Post karma: {n} · Comment karma: {n}"

All metadata fields are conditional — only rendered when `user_metadata` exists. Reddit user pages are unaffected (no user metadata import planned for Reddit).

### Post thumbnails: Small left thumbnail

Thumbnails display as a small image (48x36px) to the left of the score badge on post cards. Conditional — only shown when a thumbnail file exists for that post. Self-posts and posts without thumbnails render the existing text-only card layout with no empty space.

Template change: `components/post_card.html` gains a conditional `<img>` before the score badge. CSS handles the flex layout shift when the thumbnail is present vs absent.

---

## Thumbnail Integration (Phase 4)

### Current state

Post thumbnails are stored in `thumbnails.tgz` (14GB) as UUID-named files in a nested directory structure:

```
thumbnails/
├── 00/00/000003b1-a99c-4af2-b923-13b669927ae1.jpg
├── 00/00/000011b8-504d-4d29-a233-375fffcf5b66.jpg
├── 00/01/000109a4-1195-4ccc-93ac-ea5db933e1f4.jpg
└── ... (~500K+ files)
```

The `thumbnail` column in the submission SQL (`voat_sql_parser.py:46`, column index 14) contains the UUID filename. This field is currently stored only in `json_data` JSONB — not promoted to a column.

### Mapping strategy

1. During regular post import, the `thumbnail` field from `json_data` provides the UUID
2. During enrichment with `--voat-thumbnails`, match UUIDs to files in the thumbnail directory
3. Copy matching thumbnails to `output/assets/thumbnails/{XX}/{YY}/{uuid}.{ext}`
4. Post card templates conditionally display `<img>` tags when a thumbnail path exists

### Scale consideration

14GB of thumbnails is substantial. Two strategies:

- **Selective copy (recommended):** Only copy thumbnails for posts in tracked subverses. Requires joining against the `posts` table to get submission IDs and their thumbnail UUIDs.
- **Full mount:** In Docker, mount the thumbnail directory and serve directly via nginx. Zero copy cost but requires the full 14GB to be available at runtime.

---

## Implementation Phasing

| Phase | Scope | Effort | Blockers |
|-------|-------|--------|----------|
| **Phase 1: Subverse metadata** — **implemented** (`--enrich-voat`, migration 009, shared about pages; tracking is platform-scoped and prefers exact-case subverse names; API surfacing deferred) | Import subverse descriptions, sidebar HTML, creation dates, subscribers, NSFW, moderator names. Generate about pages. Integrate with dashboard and API. | Medium | None — sidebar HTML is pre-rendered |
| **Phase 2: User profiles** — **implemented** (user_metadata table via migration 011, `--enrich-voat` auto-detects user.sql.gz, svpassword stripped, user pages show bio/member-since/karma/bot badge in both static and dynamic modes; parser gained Adminer column-list INSERT support) | Import user bios, registration dates, karma breakdowns. Enrich user pages. | Medium | None |
| **Phase 3: Moderators + flair** — **implemented** (structured moderator lists with levels/dates replace the name-only list; flair from `type='Flair'` attribute rows — NOTE: the spec's `type='linkflairlabel'` was wrong, those are cssClass values on system Data labels — mapped to `json_data.link_flair_text`, enabling the F1 flair index and dynamic `?flair=` for Voat) | Import structured moderator data (levels, dates). Import submission flair attributes. Show moderators on about page, flair on post cards. | Medium | Phase 1 (about page must exist for moderator display) |
| **Phase 4: Thumbnails** | Extract and serve post thumbnails. Map UUID filenames to submissions. | Large | Phase 1 + storage decisions (14GB) |
| **Phase 5: Historical data** | Import subscriber time-series, user badges, top50 rankings. Power analytics/charts in dynamic mode. | Small–Medium | Feature 2 dynamic mode (for interactive charts) |

### Phase 1 advantage over Feature 6 Phase 1

Voat's `formattedSidebar` is already HTML. Phase 1 does NOT need the `markdown` + `bleach` rendering pipeline that Feature 6 Phase 1 requires. Only `bleach` (or equivalent) is needed for XSS sanitization of the pre-rendered HTML. This makes Feature 7 Phase 1 simpler to implement than Feature 6 Phase 1.

---

## Testing Strategy

### Unit tests
- VoatSQLParser correctly parses all 6 new table types (column count validation per table)
- `svpassword` field is stripped from user data before storage
- Semicolon-separated `moderators` field parses into structured list
- Subverse metadata normalizes to `subreddit_metadata` schema correctly
- Flair attributes map to `json_data.link_flair_text` correctly
- Thumbnail UUID extraction from `json_data` matches file paths

### Integration tests
- Import `subverse.sql.gz` → verify `subreddit_metadata` populated with `platform='voat'`
- Import `user.sql.gz` → verify `user_metadata` populated, `svpassword` absent
- Import moderators → verify `moderators_json` on `subreddit_metadata` is correct
- Import flair → verify `json_data.link_flair_text` updated on matching posts
- Dashboard shows Voat subverse descriptions and subscriber counts
- API returns Voat metadata alongside statistics
- Re-import same data → verify upsert works cleanly
- Mixed platform: Reddit + Voat in same database → correct platform isolation

### End-to-end tests
- Full pipeline: import posts + enrich metadata + export → verify about page with sidebar HTML
- User pages show bio, registration date, karma when metadata exists
- Flair labels appear on post cards after flair enrichment
- Thumbnail images display on post pages when `--voat-thumbnails` provided
- Navigation links (about, etc.) appear conditionally

---

## Scale Estimates

| Table | Records | Compressed | Import Time (est.) |
|-------|---------|-----------|-------------------|
| `subverse` | ~22,460 | 3.5 MB | < 30 seconds |
| `user` | ~5,000+ | 4.7 MB | < 30 seconds |
| `subverseModerator` | ~54,000 | 797 KB | < 10 seconds |
| `subverseSubscribers` | ~660,000 | 3.7 MB | < 2 minutes |
| `submissionAttribute` | ~1,043,000 | 2.6 MB | < 3 minutes |
| `userBadge` | ~71,000 | 1.1 MB | < 15 seconds |
| `top50` | ~528,000 | 5.6 MB | < 2 minutes |
| **Total metadata** | **~2.4M rows** | **22 MB** | **< 10 minutes** |
| Thumbnails | ~500K+ files | 14 GB | 30–60 min (selective copy) |

All metadata tables are tiny relative to the 3.8M posts and 24.1M comments already being imported. The thumbnail archive is the only large item and is entirely optional (Phase 4).

---

## Resolved Research

All questions about Voat data have been resolved by inspecting the actual SQL dumps:

| # | Question | Resolution |
|---|----------|-----------|
| 1 | Can `subreddit_metadata` be shared with F6? | **Yes.** Same PK `(subreddit, platform)`. Voat uses `platform='voat'`. Fields map cleanly. Three new nullable columns needed (`created_by`, `is_deleted`, `moderators_json`). |
| 2 | Is `formattedSidebar` safe HTML? | **Pre-rendered by Voat, needs sanitization.** Inspection shows standard HTML (`<h5>`, `<p>`, `<a>`, `<ul>`, `<li>`). Still must sanitize with `bleach` before storage (XSS prevention). |
| 3 | How do thumbnails map to posts? | **Via `thumbnail` column** (column index 14 in `submission` table, `voat_sql_parser.py:46`). Contains UUID filenames matching `thumbnails/{XX}/{YY}/{uuid}.ext` paths. |
| 4 | What does `subverse.moderators` contain? | **Semicolon-separated usernames.** Verified: `'DerpyPigSauce;T4C0M4ST3R'`. The `subverseModerator` table provides richer data (levels, dates). |
| 5 | What is `subverseSubscribers` format? | **Date-series.** `(subverse, date, count)` tuples. ~660K rows across all subverses. |
| 6 | Are there sensitive fields? | **Yes.** `user.svpassword` (always empty in data but must be excluded from storage). `user.profilePicture` contains voat.co CDN URLs that are dead. |
| 7 | Can existing VoatSQLParser handle new tables? | **Yes, with a one-line registration each.** `stream_rows()` handles any `table_name` that has a `COLUMN_MAPS` entry (it raises `ValueError: Unknown table` otherwise). Only `COLUMN_MAPS` additions needed — no parser logic changes. |
| 8 | What is `submissionAttribute` format? | **Flair data.** `type='linkflairlabel'`, `name` contains the flair text. ~1M records. Maps to `json_data.link_flair_text` on posts. |

---

## Cross-References

- See [06-subreddit-metadata-enrichment.md](06-subreddit-metadata-enrichment.md) — shares `subreddit_metadata` table and about page template. Feature 7 uses `platform='voat'`; Feature 6 uses `platform='reddit'`.
- See [01-static-index-improvements.md](01-static-index-improvements.md) — `submissionAttribute` flair data enables flair indexing for Voat archives
- See [02-dynamic-serving-mode.md](02-dynamic-serving-mode.md) — user profile pages with bios and subscriber growth charts are most valuable in dynamic mode
- See [05-unicode-foreign-language-support.md](05-unicode-foreign-language-support.md) — Voat was primarily English, but some sidebar content contains non-English text
