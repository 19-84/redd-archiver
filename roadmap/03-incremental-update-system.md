# Feature 3: Incremental Update System

**Status:** Planned
**Last updated:** 2026-02-11

**Goal:** Keep archives current by importing new data from monthly Arctic Shift torrent releases without requiring full re-imports.

**Problem:** Archives become stale. Currently, updating an archive means re-importing the entire dataset. There's no mechanism to pull in just the new posts and comments that appeared since the last import.

---

## Data Source

[Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) publishes monthly Reddit data dumps as torrents:
- Format: `.zst` compressed files (same format redd-archiver already handles)
- Content: `RC` (Reddit Comments) and `RS` (Reddit Submissions) per month
- Scope: **All of Reddit** for that time period — not separated by subreddit
- Distribution: Academic Torrents
- Frequency: Monthly releases

---

## Approach

A new importer that:

1. **Accepts a monthly Arctic Shift .zst dump** (containing all of Reddit for that month)
2. **Streams through the entire file** using the existing `read_lines_zst()` architecture (constant memory)
3. **Filters by tracked subreddits** — only processes posts/comments belonging to subreddits already in the archive's database
4. **Merges new data** into the existing PostgreSQL database — existing records get scores refreshed, new records are inserted (see implementation details)
5. **Tracks processing state** — records which monthly dumps have been processed to avoid re-importing
6. **Triggers selective re-export** — regenerates only the pages affected by the new data:
   - Updated subreddit index pages (new posts change pagination/ordering)
   - New individual post pages
   - Updated user pages for authors with new activity
   - Updated statistics/dashboard
   - Updated sitemaps

---

## Processing flow

```
Monthly .zst dump (all Reddit)
        │
        ▼
Stream line-by-line (constant memory)
        │
        ▼
Filter: is this subreddit tracked? ──── No → skip
        │
        Yes
        ▼
Upsert into PostgreSQL
        │
        ▼
Track affected subreddits + users
        │
        ▼
 ┌──────┴──────────────────────┐
 │ Static/Hybrid:              │ Dynamic:
 │ Re-export affected pages    │ Done (content is live)
 └─────────────────────────────┘
```

---

## Phase 1: Importer + Schema

### New importer: `core/importers/arctic_shift_importer.py`

```python
class ArcticShiftImporter(BaseImporter):
    """Importer for monthly Arctic Shift Reddit data dumps."""
    PLATFORM_ID = "reddit"

    def prefix_id(self, raw_id):
        # OVERRIDE: Return raw ID without platform prefix.
        # Existing Reddit data uses unprefixed IDs via the legacy
        # stream_to_database() path. Must match for upserts to merge.
        return str(raw_id)

    def stream_posts(self, file_path, filter_communities=None):
        # Reuse read_lines_zst() from core/watchful.py
        # Each line is a JSON Reddit submission (same format as pushshift)
        # filter_communities is REQUIRED (not optional) — enforced at runtime
        # Filter by subreddit field against filter_communities set
        # Yield normalized post dicts (same format as legacy stream_to_database)

    def stream_comments(self, file_path, filter_communities=None):
        # Same pattern as stream_posts
        # filter_communities is REQUIRED — enforced at runtime
        # Filter by subreddit field
        # Yield normalized comment dicts
```

**Critical design decision: IDs must be raw, unprefixed.**

The `BaseImporter` pattern normally prefixes IDs with the platform name (`voat_12345`, `ruqqus_67890`). However, existing Reddit data does NOT use the importer path — it uses the legacy `stream_to_database()` function in `core/watchful.py`, which passes raw Reddit JSON directly to `insert_posts_batch()`. This means existing Reddit records in the database have **raw, unprefixed IDs** (e.g., `abc123`, not `reddit_abc123`).

The `RedditImporter` class exists and has `prefix_id()`, but it's never actually used for imports — `reddarc.py:1082` explicitly routes Reddit through the legacy path: `if importer_obj and platform != "reddit":`.

For Arctic Shift data to merge with existing Reddit data, the importer must:
1. Use raw Reddit IDs without any prefix (matching the legacy import format)
2. Set `platform = "reddit"` on all records
3. Either: (a) bypass `prefix_id()` in its normalize methods, or (b) not extend `BaseImporter` and instead follow the `stream_to_database()` pattern more closely

Option (a) is cleaner — extend `BaseImporter` but override ID handling to pass through raw IDs.

The key difference from `RedditImporter`: Arctic Shift files contain ALL subreddits, so the `filter_communities` parameter is mandatory (not optional). The importer streams the entire file but only yields records matching tracked subreddits.

### Existing upsert support

Both `insert_posts_batch()` and `insert_comments_batch()` in `core/postgres_database.py` use PostgreSQL's `ON CONFLICT (id) DO UPDATE` with selective field updates:

- **Posts**: On conflict, updates `score`, `num_comments`, and `json_data` — preserves `title`, `author`, `selftext`, `created_utc`
- **Comments**: On conflict, updates `score` and `json_data` — preserves `body`, `author`, `created_utc`

This means:
- An Arctic Shift importer can stream matching records and batch-insert them directly
- New records are inserted normally
- Existing records get their scores refreshed to the latest values (useful — scores change over time)
- Original content (titles, body text, authors) is never overwritten
- No complex merge logic needed — the database handles everything

### Existing importer patterns to leverage

The `BaseImporter` abstract class (`core/importers/base_importer.py`) defines the interface:
- `stream_posts(file_path, filter_communities=None)` → generator of post dicts
- `stream_comments(file_path, filter_communities=None)` → generator of comment dicts

The `filter_communities` parameter already supports filtering by subreddit during streaming — exactly what the Arctic Shift importer needs.

The factory pattern in `core/importers/__init__.py` provides:
- `get_importer(platform)` → returns platform-specific importer
- `detect_platform(input_dir)` → auto-detects from file patterns

### Update tracking (new schema addition)

```sql
CREATE TABLE IF NOT EXISTS update_history (
    id SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,          -- e.g., "RS_2026-01.zst"
    file_hash TEXT,                     -- SHA256 for deduplication
    month_period TEXT,                  -- e.g., "2026-01"
    posts_matched INTEGER DEFAULT 0,    -- posts matching tracked subreddits
    posts_failed INTEGER DEFAULT 0,     -- posts that failed insertion
    comments_matched INTEGER DEFAULT 0, -- comments matching tracked subreddits
    comments_failed INTEGER DEFAULT 0,  -- comments that failed insertion
    affected_subreddits JSONB,          -- ["privacy", "security", ...]
    affected_users JSONB,               -- ["johndoe", "janedoe", ...] — authors with new/updated records
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'in_progress'
);
```

**Note on insert vs update counts:** The current `insert_posts_batch()` and `insert_comments_batch()` methods return `(successful, failed)` counts but do not distinguish between newly inserted records and existing records updated via `ON CONFLICT DO UPDATE`. The `*_matched` columns above reflect total records that passed the subreddit filter and were sent to the database — the upsert handles deduplication transparently. If distinguishing new-vs-updated becomes important, the batch methods would need a `RETURNING (xmax = 0) AS was_insert` clause added to the upsert SQL.

---

## Phase 2: CLI Integration

### CLI interface

```bash
# Import a monthly dump + selective re-export (static/hybrid modes)
python reddarc.py --update /path/to/RS_2026-01.zst \
  --comments-file /path/to/RC_2026-01.zst \
  --output /var/www/html/

# Import a monthly dump only, no re-export (dynamic mode)
python reddarc.py --update /path/to/RS_2026-01.zst \
  --comments-file /path/to/RC_2026-01.zst \
  --import-only

# Import all unprocessed dumps from a directory
python reddarc.py --update-all /path/to/arctic-shift-dumps/ --output /var/www/html/

# Check update status
python reddarc.py --update-status
```

### Integration with existing CLI

The main import loop in `reddarc.py:1080-1160` already handles batch insertion:
```
for post in importer.stream_posts(file, filter_communities):
    batch.append(post)
    if len(batch) >= 10000:
        db.insert_posts_batch(batch)  # ON CONFLICT DO UPDATE refreshes scores
        batch.clear()
```

This exact pattern works for Arctic Shift imports — just with a different importer instance and a larger filter_communities set (all tracked subreddits instead of one).

---

## Phase 3: Selective Re-Export

<a id="selective-re-export-logic"></a>

After an incremental import, the system knows which subreddits and users received new data (from `affected_subreddits` and `affected_users` in `update_history`). Re-export targets:
- Subreddit index pages for affected subreddits only (new posts change page ordering)
- New individual post pages (posts with IDs not in previous export)
- User pages for affected users (authors with new posts/comments)
- Dashboard (updated statistics)
- Title index pages for affected subreddits (new titles to add)
- Sitemaps (new URLs to include)

**How affected users are identified:** During batch insertion, the importer collects the `author` field from every record that passes the subreddit filter. This set is accumulated in memory (low overhead — usernames are small strings, and only unique values are stored). After import completes, the set is persisted to `update_history.affected_users` as a JSON array. The selective re-export step reads this list and regenerates only those user pages.

**Behavior per serving mode:**
- **Dynamic mode:** Import completes → new content is immediately browsable. No re-export needed. See [02-dynamic-serving-mode.md](02-dynamic-serving-mode.md).
- **Hybrid mode:** Import completes → selective re-export regenerates affected static pages → search index is already up to date (queries live database).
- **Static mode:** Import completes → selective re-export regenerates affected static pages → PostgreSQL can be shut down again after export.

For static and hybrid modes, selective re-export is functionally the same as `--export-from-database` but scoped to affected subreddits/users rather than the entire archive.

---

## Phase 4: File Discovery & Dedup

### `--update-all` file discovery

The `--update-all` flag scans the given directory for Arctic Shift dump files using filename pattern matching:
- Submissions: `RS_YYYY-MM.zst` (e.g., `RS_2026-01.zst`)
- Comments: `RC_YYYY-MM.zst` (e.g., `RC_2026-01.zst`)

Files are paired by month period (e.g., `RS_2026-01.zst` + `RC_2026-01.zst`). Before processing each pair, the system checks `update_history.file_hash` (SHA256) to skip files that have already been imported. Files without a matching pair are skipped with a warning (e.g., submissions file present but no matching comments file). Processing order is chronological (oldest month first).

---

## Scale considerations

- Monthly Reddit dumps are large (potentially 50-100GB+ compressed)
- Streaming architecture means memory usage stays constant regardless of dump size
- Most data will be filtered out (only tracked subreddits are kept)
- For an archive tracking 5 subreddits, >99% of each monthly dump is skipped
- Duplicate records are handled at the database level (`ON CONFLICT DO UPDATE` refreshes scores while preserving content)
- Selective re-export only regenerates changed pages, not the entire archive
- The `filter_communities` check is a set membership test (O(1)) — negligible overhead per line

---

## Answered Questions

### Update automation

**Recommendation: CLI-only.**

A cron job calling the CLI command handles scheduling. Building a daemon or scheduler into redd-archiver adds complexity for no real value — the Unix philosophy of composable tools means `cron` + CLI is the correct approach. Docker users can add a cron sidecar container or use host cron.

```bash
# Example crontab entry — run monthly after Arctic Shift publishes
# Docker:
0 6 15 * * docker compose exec reddarchiver-builder python reddarc.py --update-all /data/arctic-shift/ --output /output/
# Local:
0 6 15 * * cd /opt/redd-archiver && uv run python reddarc.py --update-all /data/arctic-shift/ --output /var/www/archive/
```

If demand emerges for built-in scheduling, it can be added later without changing the core update logic.

### Voat/Ruqqus updates

**Recommendation: Not needed. Reddit-only is correct.**

Both Voat (shut down December 2020) and Ruqqus (shut down November 2022) are defunct platforms. No new data will ever be produced for either. The incremental update system only needs to support Reddit via Arctic Shift, which is the only platform with ongoing data publication.

Existing Voat and Ruqqus import capabilities remain as-is for archiving historical data dumps.

---

## Testing Strategy

### Unit tests
- Subreddit filter set matching (case sensitivity, exact match behavior)
- `affected_users` set accumulation during batch processing
- `prefix_id()` override returns raw IDs (not prefixed)
- `update_history` record creation and status transitions
- Month period extraction from Arctic Shift filenames

### Integration tests
- Import a test monthly dump → verify only tracked-subreddit records inserted
- Re-import same dump → verify no duplicate records, scores updated
- `update_history` correctly tracks affected subreddits and users
- Selective re-export only regenerates pages for affected subreddits
- SHA256 file hash deduplication prevents re-processing same file

### End-to-end tests
- Full cycle: initial import → incremental update → verify merged data correctness
- Static/hybrid modes: incremental update triggers selective re-export of correct pages only
- Dynamic mode: incremental update makes new data immediately browsable (no export step)
- Verify user pages for affected users reflect new activity after update
- Verify incremental update works correctly in all three serving modes

---

## Migration

The `update_history` table is new and created automatically on first use (guarded by `CREATE TABLE IF NOT EXISTS`). Existing `processing_metadata` entries are unaffected. The first incremental update simply imports new data alongside existing records — the upsert logic handles deduplication transparently. No manual migration steps required. Works in all three serving modes.

---

## Cross-References

- See [README.md > Serving Modes](README.md#serving-modes) for how serving mode affects post-import behavior
- See [README.md > Infrastructure](README.md#docker-changes-for-incremental-updates) for Docker volume mount configuration
- See [01-static-index-improvements.md](01-static-index-improvements.md) — title/flair pages need regeneration after updates
- See [02-dynamic-serving-mode.md](02-dynamic-serving-mode.md) — dynamic mode skips the re-export step entirely
