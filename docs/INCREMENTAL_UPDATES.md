# Incremental Updates (Monthly Arctic Shift Dumps)

Keep an existing archive current by applying monthly Reddit data dumps. The
update pipeline imports **only the subreddits already tracked in your
database**, deduplicates on re-runs, refreshes scores/comment counts, and
never overwrites preserved content with deletions.

## How It Works

1. Each month, [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift)
   publishes a dump pair on Academic Torrents:
   `RS_YYYY-MM.zst` (submissions) and `RC_YYYY-MM.zst` (comments).
   The full list of torrents lives in
   [download_links.md](https://github.com/ArthurHeitmann/arctic_shift/blob/master/download_links.md).
2. `reddarc.py --update` streams the dump, keeping only records whose
   subreddit is already in your archive (everything else is skipped without
   being stored).
3. Records are **upserted**: new posts/comments are added; existing ones get
   refreshed scores and counts, while original text is preserved (a later
   `[deleted]` never replaces archived content).
4. Every processed file is recorded in the `update_history` table with its
   SHA256 hash — re-running the same file is detected and skipped, so the
   whole flow is idempotent and safe to automate.
5. Affected subreddits and users are tracked per run, so static/hybrid
   deployments can selectively re-export just the changed listings.

## Commands

```bash
# Apply a single month
python reddarc.py \
  --update /data/monthly/reddit/submissions/RS_2026-01.zst \
  --comments-file /data/monthly/reddit/comments/RC_2026-01.zst

# Apply every unprocessed month in a directory, oldest first.
# Both flat directories and the Academic Torrents layout
# (reddit/comments/ + reddit/submissions/) are auto-discovered.
python reddarc.py --update-all /data/monthly/reddit/

# Audit what has been applied
python reddarc.py --update-status
```

Docker equivalents run inside the builder container:

```bash
docker compose exec reddarchiver-builder python reddarc.py --update-all /data/monthly/reddit/
```

## After the Update

| Serving mode | What to do after `--update` |
|---|---|
| **Dynamic** | Nothing — new content is served immediately. |
| **Hybrid / Static** | Re-export: the update tracks affected subreddits, and `--export-from-database` regenerates listings (post pages for new posts are added; existing pages are refreshed where needed). |

## Automating Monthly Updates

The flow is cron-able because every step is idempotent:

```bash
#!/bin/sh
# monthly-update.sh — download the latest dump pair and apply it.
# Torrent download is the operator's choice of client; aria2c shown here.
# Infohashes are published in arctic_shift's download_links.md.

set -eu
MONTHLY_DIR=/data/monthly

# 1. Download (skips if already complete — aria2 resumes via control files)
aria2c --dir="$MONTHLY_DIR" --seed-time=0 "magnet:?xt=urn:btih:<INFOHASH>"

# 2. Apply everything not yet processed (SHA256-checked, oldest first)
python reddarc.py --update-all "$MONTHLY_DIR/reddit/"

# 3. (hybrid/static only) refresh exported HTML
# python reddarc.py --export-from-database --output /var/www/html/
```

Run it monthly via cron or a systemd timer. A run that is interrupted or
repeated does no harm: completed files are skipped by hash, and upserts are
idempotent.

## Operational Notes

- **Time and I/O**: a monthly pair is ~60GB compressed (RC ~40GB + RS ~20GB).
  The updater hashes each file (one sequential read) and then streams it once
  more for the filtered import. Plan for the corresponding disk-read time;
  CPU cost scales with total dump lines, not with your archive size.
- **Disk**: dumps can be deleted after `--update-status` confirms the month
  is recorded — the hash lives in the database, not the file.
- **User statistics** are refreshed for affected users only, and counts stay
  global (activity across all archived communities).
- **Submissions-only or comments-only months** are supported: a missing side
  of the pair logs a warning and processes the available file.
- **Schema**: the `update_history` table is created automatically on first
  use; no migration steps are needed.

## Verifying an Update

```bash
python reddarc.py --update-status            # months applied, when, row counts
psql "$DATABASE_URL" -c "SELECT to_timestamp(max(created_utc))::date FROM posts;"
```

The newest post date should match the most recent month applied.
