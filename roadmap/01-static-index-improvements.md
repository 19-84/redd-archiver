# Feature 1: Static Index & Search Improvements

**Status:** Planned
**Last updated:** 2026-06-09

**Goal:** Improve content discoverability in pure static hosting environments (GitHub Pages, Netlify, etc.) where no server or JavaScript is available.

**Problem:** The current static output provides subreddit index pages (sorted by score/comments/date) and individual post pages, but there's no way to search or browse by category. The search form is non-functional without the Flask server.

---

## Phase 1: Post Title Index

Pre-computed alphabetical listing of all post titles with direct links to post pages. One page per letter (A, B, C, ..., Z, 0-9) with overflow pagination for letters exceeding 500 titles. Users use browser `Ctrl+F` to search within each page.

**URL structure:**
```
r/{subreddit}/titles/              # Directory: all letters with counts
r/{subreddit}/titles/a/            # All titles starting with A
r/{subreddit}/titles/a/2/          # Page 2 of A titles (if >500)
r/{subreddit}/titles/b/
...
r/{subreddit}/titles/z/
r/{subreddit}/titles/0-9/          # Numeric/special character titles
```

**Page layout:**
- Navigation bar with letter tabs (A | B | C | ... | Z | 0-9)
- Alphabetically sorted post titles, each a direct link to the post page
- Score shown alongside each title for context
- Paginated within each letter if >500 titles per page
- Tip/reminder to use `Ctrl+F` for searching

**Scale estimates:**

| Archive Size | Directory Page | Letter Pages | Overflow Pages | Total |
|---|---|---|---|---|
| 10,000 posts | 1 | ~27 | ~0 | **~28** |
| 500,000 posts | 1 | 27 | ~230 | **~258** |
| 5,000,000 posts | 1 | 27 | ~2,570 | **~2,600** |
| 50,000,000 posts | 1 | 27 | ~26,000 | **~26,000** |

---

## Phase 2: Flair Index

Group posts by their existing flair/tag metadata. Only generated for subreddits that have flair data.

**URL structure:**
```
r/{subreddit}/flair/
r/{subreddit}/flair/{flair-slug}/
```

**Page layout:**
- Directory page listing all flairs with post counts
- Per-flair pages showing posts tagged with that flair, paginated at 100/page
- Standard post card format (same as subreddit index pages)

**Scale estimates:**

| Archive Size | Flairs | Approx. Pages |
|---|---|---|
| 10,000 posts | ~8 | ~40 |
| 500,000 posts | ~15 | ~750 |
| 5,000,000 posts | ~20 | ~6,000 |
| 50,000,000 posts | ~25 | ~62,500 |

**Notes:**
- Only generated when flair data exists in the source data
- Voat and Ruqqus flair support TBD (depends on available metadata)
- Subreddits without flairs skip this entirely

---

## Phase 3: Archive Map Page

A human-readable structured overview page that replaces the non-functional static search form. Serves as the central navigation hub for static archives.

**URL:** `archive-map/index.html` (linked from main navigation)

**Page layout:**
- Per-subreddit section showing:
  - Browse links (by score | by comments | by date)
  - Title index links (A | B | C | ... | Z | 0-9)
  - Flair links (if flairs exist)
  - Basic stats (post count, comment count, author count, date range)
- Overall archive statistics
- Usage tip about `Ctrl+F` on title index pages

**Replaces:** The static search form page, which currently renders a form that submits to the Flask server (non-functional in static-only deployments).

---

## Implementation Details

### Where in the pipeline

Per-subreddit indexes (title index, flair index) slot into the export pipeline after subreddit index pages and individual post pages, inside `process_subreddit_database_backed()` (`core/write_html.py:897`):

```
process_subreddit_database_backed()
  ├─ write_link_pages_jinja2()           # Individual post pages (existing)
  ├─ write_subreddit_pages_from_database() # Subreddit indexes (existing)
  ├─ write_title_index_jinja2()          # NEW: Title index per subreddit
  ├─ write_flair_index_jinja2()          # NEW: Flair index per subreddit
  └─ (statistics calculation)
```

The archive map page slots into `finalize_archive_with_stats()` (`reddarc.py:2622`):

```
finalize_archive_with_stats()
  ├─ write_index()                       # Dashboard homepage (existing)
  ├─ update_global_search_incremental()  # Subreddit list (existing)
  └─ write_archive_map_jinja2()          # NEW: Archive map page
```

### New templates needed

- `templates_jinja2/pages/title_index.html` — alphabetical title listing
- `templates_jinja2/pages/title_directory.html` — letter directory
- `templates_jinja2/pages/flair_index.html` — posts by flair
- `templates_jinja2/pages/flair_directory.html` — flair listing
- `templates_jinja2/pages/archive_map.html` — structured overview

### Database queries

- Title index: `SELECT id, title, score, permalink, created_utc FROM posts WHERE subreddit = %s ORDER BY LOWER(title)` — simple, uses existing table
- Flair index: `SELECT DISTINCT json_data->>'link_flair_text' FROM posts WHERE subreddit = %s AND json_data->>'link_flair_text' IS NOT NULL` — needs expression index (see [Flair column migration](#flair-column-migration) below)
- Flair posts: `SELECT * FROM posts WHERE subreddit = %s AND json_data->>'link_flair_text' = %s ORDER BY score DESC` — paginated with keyset

### Patterns to follow

- Use `render_template_to_file()` for all page generation (existing pattern)
- Use `get_posts_paginated_keyset()` for paginated queries (existing, O(1) performance)
- Use the SEO helpers in `html_seo.py` for metadata — e.g. `generate_index_meta_description()`, `generate_subreddit_meta_description()`, `generate_subreddit_seo_title()` (there is no single `generate_page_seo_content()` entry point; pick the helper matching the page type)
- Follow the parallel generation pattern from `write_subreddit_pages_parallel_jinja2()` if page count is high

---

## Answered Questions

### Post title index chunking strategy

**Recommendation: Per-letter pages (A, B, C, ..., Z, 0-9) with overflow pagination.**

- One page per letter: `r/{sub}/titles/a/`, `r/{sub}/titles/b/`, etc.
- If a letter has >500 titles, paginate: `r/{sub}/titles/a/`, `r/{sub}/titles/a/2/`, etc.
- A directory page at `r/{sub}/titles/` listing all letters with counts.
- Predictable URLs, simple to implement, handles uneven distribution through pagination rather than adaptive ranges.
- Adaptive ranges (A-D, E-H) seem clever but produce unpredictable URLs and would differ between subreddits, making the code more complex for no real user benefit.

### Flair data availability

**Confirmed: Flair data is available and already used.**

- The `posts` table stores the full Reddit JSON object in `json_data JSONB`.
- `link_flair_text` is present in Reddit's submission JSON format.
- The codebase already extracts it: `post.get("link_flair_text", "")` in `html_modules/html_field_generation.py`.
- Post cards in the HTML output already display flair badges.
- Arctic Shift dumps use the same Reddit JSON format, so flair data will be present in incremental updates too.

**Implementation note for flair index:** Querying flairs efficiently at scale requires an expression index on the JSONB field (see [Flair column migration](#flair-column-migration) below for full analysis). Current schema stores flair only in JSONB, which works but isn't optimized for `WHERE json_data->>'link_flair_text' = 'Discussion'` queries across millions of rows without the index.

### Flair column migration

**Recommendation: Expression index, not a new column.**

Three options considered:

| Approach | Schema Change | Import Pipeline Change | Query Performance |
|---|---|---|---|
| Add `link_flair_text TEXT` column | Yes (migration + backfill) | Yes (must populate on insert) | Best (native B-tree) |
| Expression index on JSONB | No | No | Good enough |
| GIN index on entire `json_data` | No | No | Overkill, bloated index |

An expression index is the right call:

```sql
CREATE INDEX idx_posts_flair ON posts ((json_data->>'link_flair_text'));
```

This gives B-tree performance on flair queries without any schema migration, data backfill, or changes to the import pipeline. PostgreSQL can use this index directly for `WHERE json_data->>'link_flair_text' = 'Discussion'` queries. At 50M rows, this is efficient enough — the index is small because it only covers one extracted text value, not the entire JSONB blob.

If performance becomes insufficient at extreme scale, promoting to a dedicated column is a straightforward future migration. No need to over-engineer upfront.

### Title index generation timing

**Recommendation: Integrate into the main export pass.**

The title index is just another set of pages to generate, no different from subreddit index pages or user pages. It reads the same data from PostgreSQL (post titles, IDs, scores) and writes HTML files to the same output directory.

Reasons not to make it a separate step:
- Adds user friction — one more command to remember
- No performance benefit — the PostgreSQL queries are cheap regardless of when they run
- Users expect `--output` to produce a complete archive, not a partial one requiring post-processing

The title index generation slots in after subreddit index pages and before SEO/sitemap generation in the export pipeline. If a user needs to regenerate just the title indexes (e.g., after an incremental update), `--export-from-database` already provides that capability — it re-exports everything from the existing database.

---

## Testing Strategy

### Unit tests
- Title index letter-bucketing logic (edge cases: non-ASCII titles, empty titles, numeric-only titles)
- Flair extraction from JSONB (null flairs, empty strings, HTML entities in flair text)
- Flair slug generation (special characters, duplicates, very long flair names)
- Overflow pagination calculation (boundary: exactly 500, 501, 0 titles per letter)

### Integration tests
- Title index generation against a test PostgreSQL database with known data
- Flair index generation for subreddits with and without flair data
- Archive map page generation with multiple subreddits
- Expression index creation and query plan verification (`EXPLAIN ANALYZE`)

### End-to-end tests
- Full pipeline: import test `.zst` → export with title/flair indexes → verify HTML output structure
- Verify all inter-page links resolve (no broken links between title index ↔ post pages)
- Verify archive map links match generated index files
- Verify `Ctrl+F` target text is present and not hidden/truncated in title index pages

---

## Migration

Existing archives gain title index, flair index, and archive map pages by re-running `--export-from-database` with the updated version. No database migration needed — the expression index for flair queries is created automatically during export. Existing pages are untouched; only new files are added to the output directory.

---

## Cross-References

- See [README.md > Serving Modes](README.md#serving-modes) for how static mode features differ from hybrid/dynamic
- See [02-dynamic-serving-mode.md > Phase 4](02-dynamic-serving-mode.md#phase-4-dynamic-only-features) — dynamic flair filtering replaces static flair pages; dynamic title browsing serves title pages on-the-fly
- See [03-incremental-update-system.md > Selective re-export](03-incremental-update-system.md#selective-re-export-logic) — title/flair pages need regeneration after incremental updates
