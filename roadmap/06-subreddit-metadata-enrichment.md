# Feature 6: Subreddit Metadata Enrichment

**Status:** Planned
**Last updated:** 2026-02-11

**Goal:** Import subreddit metadata, rules, and wiki pages from Arctic Shift's [subreddit metadata dump](https://academictorrents.com/details/5d0bf258a025a5b802572ddc29cde89bf093185c) to enrich archives with community context that doesn't exist in post/comment data alone.

**Problem:** Archives currently contain only posts, comments, and derived statistics. There's no record of what a subreddit's purpose was, what its rules were, what its sidebar said, or what community knowledge existed in its wiki pages. For defunct or quarantined communities, this context is irreplaceable.

---

## Data Source

Arctic Shift publishes a subreddit metadata dump on [Academic Torrents](https://academictorrents.com/details/5d0bf258a025a5b802572ddc29cde89bf093185c) (2.65 GB compressed, January–February 2025 retrieval):

| File | Size | Records | Contents |
|---|---|---|---|
| `subreddits_2025-01.zst` | 2.24 GB | 22M subreddits | Full metadata: description, subscribers, settings, appearance, lang, flair config, etc. |
| `subreddit_rules_2025-01.zst` | 67 MB | 345K subreddits | Posting/commenting rules with descriptions and violation reasons |
| `subreddit_wikis_2025-01.zst` | 308 MB | 323K wiki pages | Wiki content with revision history |
| `subreddits_meta_only_2025-01.zst` | 33 MB | 1.6M subreddits | Lightweight: display name, ID, earliest post/comment dates, post/comment counts |

Format: Zstandard-compressed JSONL. Schemas documented at [arctic_shift/schemas/subreddits/](https://github.com/ArthurHeitmann/arctic_shift/tree/master/schemas/subreddits).

---

## Available Fields

### Subreddit metadata (full — `subreddits_2025-01.zst`)

From the [Arctic Shift JSON schema](https://github.com/ArthurHeitmann/arctic_shift/blob/master/schemas/subreddits/subreddits_2025-01.json):

**Community identity:**
- `display_name`, `display_name_prefixed`, `title`, `id`, `name`, `url`
- `description` (sidebar markdown — **no pre-rendered `description_html` available**)
- `public_description` (short tagline — **no pre-rendered `public_description_html` available**)
- `lang` (e.g., `"en"`, `"de"`, `"ja"` — set by moderators)
- `subreddit_type` (public, private, restricted, archived, etc.)
- `created_utc`, `subscribers`, `accounts_active`, `active_user_count`

**Content policy & settings:**
- `over18`, `quarantine`, `quarantine_message`, `quarantine_message_html` (pre-rendered)
- `submission_type` (any, link, self)
- `allow_galleries`, `allow_images`, `allow_polls`, `allow_videos`
- `spoilers_enabled`, `content_category`, `advertiser_category`
- `suggested_comment_sort`, `comment_score_hide_mins`, `collapse_deleted_comments`

**Appearance (useful for Feature 4 custom branding):**
- `banner_background_color`, `banner_background_image`, `banner_img`, `banner_size`
- `icon_img`, `icon_size`, `community_icon`
- `header_img`, `header_size`, `header_title`
- `key_color`, `primary_color`

**Flair configuration (useful for Feature 1 flair index):**
- `link_flair_enabled`, `link_flair_position`
- `can_assign_link_flair`, `can_assign_user_flair`
- `user_flair_enabled_in_sr`, `user_flair_position`

**Submission prompts:**
- `submit_text` (markdown), `submit_text_html` (pre-rendered)
- `submit_text_label`, `submit_link_label`

**Arctic Shift enrichment (`_meta`):**
- `earliest_comment_at`, `earliest_post_at`
- `num_comments`, `num_posts` (with `*_updated_at` timestamps)

**Pre-rendered HTML availability (confirmed from schema):**

| Field | Markdown | Pre-rendered HTML |
|---|---|---|
| `description` (sidebar) | Yes | **No** — must render ourselves |
| `public_description` | Yes | **No** — must render ourselves |
| `submit_text` | Yes | Yes (`submit_text_html`) |
| `quarantine_message` | Yes | Yes (`quarantine_message_html`) |
| Rule descriptions | Yes | **No** — must render ourselves |
| Wiki page content | Yes | **No** — must render ourselves |

### Subreddit rules (`subreddit_rules_2025-01.zst`)

**One JSON object per subreddit** containing the full rules array:

```typescript
{
  retrieved_on: number,
  subreddit: string,
  rules: [{
    created_utc: number,
    description: string | null,  // Full rule explanation (can be lengthy markdown)
    kind: "all" | "link" | "comment",  // What the rule applies to
    priority: number,            // Display order
    short_name: string,          // Rule title (e.g., "No personal information")
    violation_reason: string,    // Text shown when reporting a violation
  }]
}
```

**Import note:** The dump format is one record per subreddit, not one record per rule. Import must unpack the `rules` array and insert individual rows. On re-import, the entire rule set for a subreddit should be replaced (delete + insert), not upserted per-priority, because rules can be reordered or removed between dumps.

### Subreddit wikis (`subreddit_wikis_2025-01.zst`)

Per-page objects:

```typescript
{
  content: string,              // Wiki page content (markdown)
  path: string,                 // Wiki page path (e.g., "index", "faq", "config/sidebar")
  retrieved_on: number,
  revision_author: string | null,
  revision_author_id: string | null,
  revision_date: string,
  revision_reason: string | null,
}
```

**Schema note:** The wiki dump does NOT include a `subreddit` field per record. The `path` field (min 14 chars, avg 39.25 chars) likely encodes subreddit info (e.g., `r/{sub}/wiki/{page}` or `{sub}/{page}`), but this must be verified by inspecting actual data. **Wiki import is Phase 2 — metadata and rules import (Phase 1) can proceed without resolving this.**

Common wiki pages: `index` (landing page), `faq`, `rules` (extended rules), `config/sidebar`, `config/description`, `config/submit_text`, community-specific pages.

---

## What This Data Enables

### Immediate value (archive enrichment)

| Data | Use Case | Current Gap |
|---|---|---|
| `description` + `public_description` | Subreddit "about" page in the archive | No sidebar/description anywhere in current output |
| `rules` | Display community rules alongside archived content | No rules preserved |
| Wiki pages | Preserve community knowledge (FAQs, guides, etc.) | No wiki content at all |
| `lang` | Per-subreddit language hint for FTS config (see [Feature 5](05-unicode-foreign-language-support.md)) | FTS hardcoded to English |
| `banner_img`, `icon_img`, `key_color` | Subreddit-specific branding in archive output | All subreddits look identical |
| `over18`, `quarantine` | Content warnings in archive UI | Not shown (data exists in post JSON but not surfaced) |
| `subscribers`, `active_user_count` | Historical context on subreddit size | Only derived post/comment counts |
| `created_utc` | Subreddit creation date on dashboard | Not available |
| `suggested_comment_sort` | Honor original comment sort order | Hardcoded sort |

### Cross-feature synergies

- **Feature 1 (flair index):** `link_flair_enabled` tells us whether to attempt flair indexing, avoiding wasted queries on subreddits that never had flair.
- **Feature 2 (dynamic mode):** Subreddit metadata can power a richer subreddit landing page with description, rules, and stats — not just a post list.
- **Feature 4 (visual themes):** `key_color`, `primary_color`, `banner_background_color` could feed per-subreddit accent color overrides.
- **Feature 5 (Unicode):** `lang` field enables per-subreddit FTS regconfig selection instead of one global config.

### Archival/preservation value

For subreddits that have been banned, quarantined, or gone private, this metadata may be the only surviving record of:
- What the community's stated purpose was
- What its rules and moderation policies were
- What community-curated knowledge existed in its wiki
- Its visual identity (icons, banners, colors)

---

## Current Schema Gap

The existing schema has no table for subreddit-level metadata beyond computed statistics. Currently:

| Table | What it stores | Source |
|---|---|---|
| `subreddit_statistics` | Post/comment counts, score averages, date ranges, file sizes | Computed from `posts`/`comments` tables |
| `processing_metadata` | Pipeline state (pending/importing/completed) | Internal tracking |

Neither table stores the subreddit's description, rules, wiki content, language, appearance, or any Reddit-sourced metadata.

**Relationship between tables:** `subreddit_metadata` (new) and `subreddit_statistics` (existing) are peers, not parent-child. Both are keyed on `(subreddit, platform)`. No foreign key between them — metadata can be imported before or after posts, and statistics are computed independently. Queries join them at read time when both are needed.

---

## Proposed Schema Additions

### `subreddit_metadata` table

```sql
CREATE TABLE IF NOT EXISTS subreddit_metadata (
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,

    -- Identity
    display_name TEXT,
    title TEXT,                          -- Subreddit display title (can be Unicode)
    description TEXT,                    -- Sidebar markdown (rendered to HTML at export time)
    description_html TEXT,               -- Pre-rendered sidebar HTML (rendered once at import, cached)
    public_description TEXT,             -- Short tagline
    subreddit_type TEXT,                 -- public, private, restricted, archived
    lang TEXT,                           -- Language code (e.g., "en", "ja")

    -- Counts (from Reddit, not computed)
    subscribers INTEGER,
    active_users INTEGER,
    created_utc BIGINT,

    -- Content policy
    over_18 BOOLEAN DEFAULT FALSE,
    quarantine BOOLEAN DEFAULT FALSE,
    quarantine_message TEXT,
    submission_type TEXT,                -- any, link, self
    suggested_comment_sort TEXT,

    -- Appearance
    icon_img TEXT,                       -- URL (Phase 1) or archived path (Phase 2)
    banner_img TEXT,
    key_color TEXT,                      -- Hex color
    primary_color TEXT,                  -- Hex color
    banner_background_color TEXT,

    -- Flair config
    link_flair_enabled BOOLEAN DEFAULT FALSE,

    -- Submission prompts
    submit_text TEXT,                    -- Markdown shown on submission page
    submit_text_html TEXT,               -- Pre-rendered HTML (from Arctic Shift)

    -- Source tracking
    retrieved_on TIMESTAMPTZ,
    raw_json JSONB,                      -- Full original JSON for fields not promoted to columns

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (subreddit, platform)
);
```

### `subreddit_rules` table

```sql
CREATE TABLE IF NOT EXISTS subreddit_rules (
    id SERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,

    priority INTEGER NOT NULL,           -- Display order
    short_name TEXT NOT NULL,            -- Rule title
    description TEXT,                    -- Full rule explanation (markdown)
    description_html TEXT,               -- Pre-rendered HTML (rendered once at import)
    kind TEXT NOT NULL,                  -- "all", "link", "comment"
    violation_reason TEXT,
    rule_created_utc BIGINT,

    retrieved_on TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- No UNIQUE constraint on priority — rules are bulk-replaced per subreddit.
-- Index for efficient querying by subreddit.
CREATE INDEX IF NOT EXISTS idx_subreddit_rules_sub
    ON subreddit_rules (subreddit, platform);
```

**Import strategy:** DELETE all existing rules for a subreddit, then INSERT the new set. This handles rule reordering, removal, and addition cleanly. Wrapped in a transaction for atomicity.

### `subreddit_wiki_pages` table

```sql
CREATE TABLE IF NOT EXISTS subreddit_wiki_pages (
    id SERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    platform TEXT DEFAULT 'reddit' NOT NULL,

    path TEXT NOT NULL,                  -- e.g., "index", "faq", "config/sidebar"
    content TEXT NOT NULL,               -- Wiki page content (markdown)
    content_html TEXT,                   -- Pre-rendered HTML (rendered once at import)
    revision_author TEXT,
    revision_date TIMESTAMPTZ,
    revision_reason TEXT,

    retrieved_on TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (subreddit, platform, path)
);
```

---

## Codebase Integration Map

### Where metadata plugs into existing code

#### 1. Dashboard homepage

**Current flow:** `write_index_jinja2()` (`html_modules/html_dashboard_jinja.py:22`) → calls `get_all_subreddit_statistics_from_db()` → passes stats to `prepare_dashboard_card_data()` (`html_modules/dashboard_helpers.py:159`) → renders `pages/index.html`.

**Enrichment:** After fetching statistics, also call `get_all_subreddit_metadata()`. Pass metadata alongside stats into `prepare_dashboard_card_data()`. Each dashboard card gains:
- `public_description` as subtitle text under the subreddit name
- `icon_img` as a visual identifier
- `lang` badge for non-English subreddits
- `over18` / `quarantine` warning indicators
- `subscribers` as historical context ("had X subscribers at time of archival")
- `created_utc` for subreddit age display

#### 2. Subreddit index pages

**Current flow:** `write_subreddit_pages_jinja2()` (`html_modules/html_pages_jinja.py:175`) builds a context dict with `subreddit`, `posts`, `page_num`, `total_pages`, stats — then renders `pages/subreddit.html`.

**Enrichment:** Before rendering, fetch `get_subreddit_metadata(subreddit)`. Add to context:
- `description_html` for a collapsible "About this community" section at the top of the first index page
- `has_about`, `has_rules`, `has_wiki` boolean flags for conditional navigation links
- In dynamic mode (Feature 2), `description_html` becomes a sidebar or header banner

#### 3. Navigation bar

**Current:** `templates_jinja2/components/navigation.html:16-27` shows: score | comments | date | search | home | theme toggle.

**Enrichment:** Add conditional links after the date sort link:
```
score | comments | date | [about] | [rules] | [wiki] | search | home | theme
```
Links are conditional on `has_about`, `has_rules`, `has_wiki` context variables. Only shown when metadata exists for the current subreddit.

#### 4. SEO meta tags

**Current:** `html_modules/html_seo.py:1461` — `extract_keywords_from_database()` mines post titles for keywords. Meta descriptions are auto-generated from stats (e.g., "Archive of X posts from r/Y").

**Enrichment:** `public_description` becomes the primary `<meta name="description">` for subreddit pages — it's literally what the moderators wrote as the community's tagline. Falls back to auto-generated description if metadata is not available.

#### 5. REST API

**Current:** `GET /api/v1/subreddits/<name>` (`api/routes.py:2055`) queries only `subreddit_statistics` and returns counts/dates.

**Enrichment:** After fetching stats, also query `subreddit_metadata`. Merge into response. Add new fields to `VALID_SUBREDDIT_FIELDS` (`routes.py:247`): `description`, `public_description`, `lang`, `subscribers`, `created_utc`, `over18`, `quarantine`, `icon_img`, `rules_count`, `wiki_pages_count`.

The MCP-optimized `/subreddits/<name>/summary` endpoint (`routes.py:3520`) should include `public_description` and `lang` — these are exactly the kind of context an AI assistant needs.

#### 6. Search server (dynamic mode)

In dynamic mode (Feature 2), subreddit landing pages `/r/<name>/` display `description_html` and rules alongside the post list. Search results can show `icon_img` next to subreddit names for visual context.

#### 7. New templates needed

| Template | Page | Content |
|---|---|---|
| `pages/subreddit_about.html` | `r/{sub}/about/` | Sidebar description, creation date, subscribers, content policy, submission prompts |
| `pages/subreddit_rules.html` | `r/{sub}/rules/` | Ordered rules list with descriptions |
| `pages/wiki_index.html` | `r/{sub}/wiki/` | Wiki page listing with last-modified dates |
| `pages/wiki_page.html` | `r/{sub}/wiki/{path}/` | Individual wiki page content |

All templates extend `base/base.html` and follow existing patterns (SEO metadata, navigation, footer).

#### 8. Export pipeline placement

New pages slot into `process_subreddit_database_backed()` (`core/write_html.py:897`):

```
process_subreddit_database_backed()
  ├─ write_link_pages_jinja2()               # Individual post pages (existing)
  ├─ write_subreddit_pages_from_database()    # Subreddit indexes (existing)
  ├─ write_title_index_jinja2()              # Title index (Feature 1)
  ├─ write_flair_index_jinja2()              # Flair index (Feature 1)
  ├─ write_subreddit_about_jinja2()          # NEW: About page (if metadata exists)
  ├─ write_subreddit_rules_jinja2()          # NEW: Rules page (if rules exist)
  ├─ write_subreddit_wiki_jinja2()           # NEW: Wiki pages (if wiki exists)
  └─ (statistics calculation)
```

#### 9. Database methods needed (in `core/postgres_database.py`)

Following the pattern of `save_subreddit_statistics()` (`postgres_database.py:3578`) and `get_all_subreddit_statistics_from_db()` (`postgres_database.py:3711`):

| Method | Purpose |
|---|---|
| `save_subreddit_metadata(subreddit, platform, metadata_dict)` | Upsert metadata record |
| `get_subreddit_metadata(subreddit, platform)` | Fetch single subreddit metadata |
| `get_all_subreddit_metadata()` | Fetch all metadata (for dashboard) |
| `save_subreddit_rules(subreddit, platform, rules_list)` | Replace rules (DELETE + INSERT in transaction) |
| `get_subreddit_rules(subreddit, platform)` | Fetch rules ordered by priority |
| `save_wiki_page(subreddit, platform, path, content, ...)` | Upsert wiki page |
| `get_wiki_pages(subreddit, platform)` | Fetch all wiki pages for subreddit |
| `get_wiki_page(subreddit, platform, path)` | Fetch single wiki page |

---

## Frontend Decisions

Resolved design decisions for how metadata surfaces in the UI. These apply to both Reddit (Feature 6) and Voat (Feature 7) metadata.

### Navigation: About-as-hub (single nav link)

Add one "about" link to the subreddit navigation bar. Rules and wiki pages are linked from within the about page, not from the main nav. This keeps the nav at 7 items (from 6) instead of 9.

```
score | comments | date | about | search | home | theme
```

The "about" link is conditional — only shown when `subreddit_metadata` exists for the current subreddit.

### Dashboard cards: Subtitle + light enrichment

Add `public_description` as a single-line italic subtitle under the subreddit name, truncated to ~120 characters via `truncate_smart()`. Add subscribers and creation date in a "metadata" section below existing stats. NSFW/quarantine badges appear next to the existing status badge in the card header.

The full `description` (sidebar) is NOT shown on dashboard cards — only the short tagline (`public_description`).

### Subreddit index: Standalone about page only

No inline "About this community" section on subreddit index pages. Metadata lives entirely on the dedicated about page (`r/{sub}/about/` or `v/{sub}/about/`). The subreddit index remains a clean post listing.

### CSS: Design tokens first (F4 Phase 1 prerequisite)

F4 Phase 1 (CSS custom property extraction) must land before metadata frontend work. New component styles for about pages, rules lists, and dashboard enrichment use `var(--token)` from the start, avoiding double-work. See [README.md > Execution Strategy](README.md#release-ordering--execution-strategy) for updated ordering.

---

## Markdown Rendering

The `description`, rule descriptions, and wiki content are Reddit Markdown. Arctic Shift provides pre-rendered HTML only for `submit_text_html` and `quarantine_message_html` — the most important fields (sidebar, rules, wiki) need rendering on our side.

**Recommended approach: Render once at import time, store both markdown and HTML.**

Both `description` + `description_html` columns exist in the proposed schema. At import time, render markdown to HTML and store the result. This avoids re-rendering on every page generation and keeps the raw markdown for future re-rendering if the renderer changes.

**Renderer options:**

| Option | Pros | Cons |
|---|---|---|
| `markdown` (Python) | Standard, well-maintained, already common | Doesn't handle Reddit-specific syntax (u/, r/ links) |
| `markdown` + custom extensions | Can add Reddit link preprocessing | More code to maintain |
| `snudown` (Reddit's own) | Exact Reddit rendering | Python 2 era, unmaintained, C extension |
| `markdown-it-py` | Fast, extensible, good plugin ecosystem | Another dependency |

**Recommendation:** `markdown` library with a thin preprocessing step to convert Reddit-specific syntax (`r/subreddit` → links, `u/username` → links) before rendering. Keep it simple — perfect fidelity to Reddit's renderer is not the goal; readable HTML is.

**Security:** All rendered HTML must be sanitized before storage to prevent XSS. Reddit sidebar content is user-authored by moderators. Use `bleach` or equivalent to strip dangerous tags/attributes after markdown rendering, before storing in `*_html` columns.

---

## CLI Interface

**Primary interface: `--enrich` flag with auto-detection.**

```bash
# Auto-detect and import all subreddit metadata files from a directory
python reddarc.py --enrich /path/to/subreddit-dumps/

# Individual file overrides (when auto-detect doesn't work)
python reddarc.py --enrich-metadata /path/to/subreddits_2025-01.zst
python reddarc.py --enrich-rules /path/to/subreddit_rules_2025-01.zst
python reddarc.py --enrich-wikis /path/to/subreddit_wikis_2025-01.zst
```

**Auto-detection:** `--enrich` scans the directory for files matching:
- `subreddits_*.zst` → metadata import
- `subreddit_rules_*.zst` → rules import
- `subreddit_wikis_*.zst` → wiki import
- `subreddits_meta_only_*.zst` → lightweight metadata (used only if full metadata file is absent)

**Behavior:** Only imports data for subreddits already tracked in the database (same filter-by-tracked-subreddits pattern as Feature 3 incremental updates). Streaming architecture — constant memory regardless of dump size.

**Combined with export:**
```bash
# Enrich + re-export (generates about/rules/wiki pages)
python reddarc.py --enrich /path/to/dumps/ --export-from-database --output /var/www/html/

# Enrich only (metadata in database, no HTML generation)
python reddarc.py --enrich /path/to/dumps/
```

---

## Implementation Phasing

| Phase | Scope | Blocker? |
|---|---|---|
| **Phase 1: Metadata + Rules** | Import `subreddits_*.zst` and `subreddit_rules_*.zst`. Generate about/rules HTML pages. Integrate with dashboard, API, navigation. | **No blockers** — can implement now. |
| **Phase 2: Wiki pages** | Import `subreddit_wikis_*.zst`. Generate wiki HTML pages. | **Blocked** on verifying wiki dump `path` field format (see Resolved Research Q3). Unblock by inspecting first 100 records of the dump. |
| **Phase 3: Image archival** | Download and archive subreddit icons/banners locally. | **Deferred** — depends on CDN persistence research. Low priority unless images are confirmed disappearing. |

Arctic Shift publishes new dumps monthly, so the enrichment import can be re-run to pick up updated metadata. The upsert (metadata) and delete+replace (rules) strategies handle re-import cleanly.

### Voat metadata pathway

Voat-specific metadata enrichment is covered in [Feature 7: Voat Data Enrichment](07-voat-data-enrichment.md). Feature 7 shares the `subreddit_metadata` table (with `platform='voat'`) and the same about page templates. The Voat SQL dumps contain far richer metadata than originally documented — subverse descriptions, pre-rendered sidebar HTML, moderator lists, user profiles, post flair, subscriber time-series, and 14GB of already-archived post thumbnails. See Feature 7 for the full data inventory and implementation plan. No equivalent metadata exists for Ruqqus guilds.

---

## Image Archival (Phase 3 — separate from metadata import)

`icon_img`, `banner_img`, `community_icon`, and `header_img` are URLs pointing to Reddit's CDN (`i.redd.it`, `styles.redditmedia.com`). These can disappear for banned/quarantined subreddits.

**Phase 1:** Store URLs as-is in `subreddit_metadata`. Templates display images via the original URLs (works as long as Reddit's CDN serves them).

**Phase 2 (optional, behind `--archive-images` flag):** Download images to `output/assets/subreddits/{name}/` and update the stored paths. This adds HTTP request complexity, error handling, rate limiting, and storage. Only worth implementing if we confirm images are disappearing for targeted subreddits.

---

## Resolved Research

All questions that previously blocked this spec have been answered or reframed:

| # | Question | Resolution |
|---|----------|------------|
| 1 | `lang` field completeness | **Non-blocking.** No public research on accuracy. Treat as optional enrichment hint for Feature 5 (per-subreddit FTS config), not a prerequisite for metadata import. If most subreddits default to `"en"`, the field is still useful for the minority that set it correctly. |
| 2 | Wiki page volume per subreddit | **Varies wildly** (0–3 for small subs, hundreds for large subs like r/AskHistorians). Non-blocking — streaming architecture handles any volume. Storage estimates in the Scale Estimates section remain valid. |
| 3 | Wiki dump subreddit association | **Unresolved — needs empirical data.** Schema confirmed: no `subreddit` field per wiki record. The `path` field has min 14 chars (avg 39.25), suggesting it may encode subreddit info (e.g., `r/{sub}/wiki/{page}` or `{sub}/{page}`). **Action required:** download and inspect first 100 records of `subreddit_wikis_2025-01.zst` to determine path format. **This blocks wiki import but not metadata/rules import.** |
| 4 | Image CDN persistence | **Uncertain.** Quarantined subreddits have documented access issues. Banned subreddit images may still work via direct CDN URL, but needs empirical verification. **Phase 2 feature anyway** — doesn't block metadata/rules import. |
| 5 | Update frequency | **Monthly.** Arctic Shift publishes new dumps monthly ([GitHub releases](https://github.com/ArthurHeitmann/arctic_shift/releases)). Supports incremental re-enrichment using the same import pattern (upsert metadata, delete+replace rules). |
| 6 | Overlap with `subreddit_statistics` | **Resolved.** Reddit-sourced metadata is canonical for subreddit-level facts (subscribers, created_utc, description). `subreddit_statistics` is canonical for archive-computed facts (posts archived, pages generated, score averages). No conflict — they are peers keyed on `(subreddit, platform)`, joined at read time. |
| 7 | Voat/Ruqqus equivalents | **Voat: comprehensive.** SQL dumps contain subverse descriptions, pre-rendered sidebar HTML, moderator lists, user profiles, post flair, subscriber time-series, and 14GB of post thumbnails. See [Feature 7](07-voat-data-enrichment.md) for the full data inventory and implementation plan. **Ruqqus: none.** No known guild metadata archive exists. |

### Remaining empirical tests

These block wiki import only, not metadata/rules:

- **Download and inspect `subreddit_wikis_2025-01.zst`** (first 100 records) to determine how wiki pages are associated with subreddits via the `path` field format
- **Test Reddit CDN URLs** from banned/quarantined subreddits to assess image persistence (informs image archival priority)

---

## Scale Estimates

| Subreddits Tracked | Metadata Records | Rules Records | Wiki Pages | DB Storage |
|---|---|---|---|---|
| 5 | 5 | ~50 | ~25 | < 1 MB |
| 50 | 50 | ~500 | ~250 | ~5 MB |
| 500 | 500 | ~5,000 | ~2,500 | ~50 MB |

The metadata itself is tiny. Wiki content can vary dramatically — r/AskHistorians may have hundreds of pages with detailed content, while most small subreddits have 0–3 wiki pages.

The import is a streaming filter over the 2.24 GB dump — same constant-memory architecture as our existing importers. For 5 tracked subreddits, >99.99% of the 22M records are skipped.

---

## Testing Strategy

### Unit tests
- Markdown rendering: Reddit-flavored markdown (r/ links, u/ links, tables) renders correctly
- HTML sanitization: XSS payloads in sidebar markdown are stripped
- Rules import: delete-and-replace correctly handles rule reordering and removal
- Auto-detection: `--enrich` correctly identifies file types from filenames
- Subreddit filtering: only tracked subreddits are imported from the 22M-record dump

### Integration tests
- Import metadata → verify `subreddit_metadata` table populated correctly
- Import rules → verify rules are ordered by priority and complete
- Import wikis → verify wiki pages associated with correct subreddits
- Dashboard generation with metadata → verify cards show description and icons
- API endpoint returns metadata fields alongside statistics
- Re-import with updated data → verify upsert/replace works correctly

### End-to-end tests
- Full pipeline: import posts → enrich metadata → export → verify about/rules/wiki pages in HTML output
- Navigation links: about/rules/wiki links appear only when data exists
- SEO: `<meta description>` uses `public_description` when available
- Dynamic mode: Flask routes serve about/rules/wiki pages from database

---

## Cross-References

- See [03-incremental-update-system.md](03-incremental-update-system.md) — same Arctic Shift data source, same streaming/filtering pattern
- See [05-unicode-foreign-language-support.md](05-unicode-foreign-language-support.md) — `lang` field enables per-subreddit FTS configuration
- See [01-static-index-improvements.md](01-static-index-improvements.md) — `link_flair_enabled` can gate flair index generation
- See [02-dynamic-serving-mode.md](02-dynamic-serving-mode.md) — metadata powers richer subreddit landing pages in dynamic mode
- See [04-visual-themes.md](04-visual-themes.md) — subreddit appearance data (`key_color`, `primary_color`) could feed per-subreddit theme overrides
- See [07-voat-data-enrichment.md](07-voat-data-enrichment.md) — shares `subreddit_metadata` table (`platform='voat'`) and about page template
