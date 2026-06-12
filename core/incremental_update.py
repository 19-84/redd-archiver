# ABOUTME: Incremental update runner — imports monthly Arctic Shift dumps into
# ABOUTME: an existing archive with dedup and affected-entity tracking (Feature 3).
"""Incremental update orchestration.

Streams monthly Arctic Shift dumps (``RS_``/``RC_YYYY-MM.zst``), keeps only
records for already-archived Reddit subreddits, upserts them (scores refresh,
content is preserved), and records the run in ``update_history`` with the
affected subreddits/users that Phase 3's selective re-export consumes.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from core.importers.arctic_shift_importer import ArcticShiftImporter, parse_dump_filename
from utils.console_output import print_info, print_success, print_warning

BATCH_SIZE = 10_000


def discover_dump_pairs(directory: str) -> list[tuple[str | None, str | None]]:
    """Find Arctic Shift dump pairs in a directory, oldest month first.

    Scans the directory itself plus the ``comments/`` and ``submissions/``
    subdirectories — the layout the official Academic Torrents releases use —
    so ``--update-all`` can point straight at a downloaded torrent.

    Returns [(rs_path, rc_path), ...] keyed by month. A month with only one
    of the pair is still processed (the missing side is None) with a warning —
    submissions-only or comments-only updates are valid.
    """
    scan_dirs = [directory] + [
        sub for name in ("comments", "submissions") if os.path.isdir(sub := os.path.join(directory, name))
    ]
    months: dict[str, dict[str, str]] = {}
    for scan_dir in scan_dirs:
        for name in sorted(os.listdir(scan_dir)):
            parsed = parse_dump_filename(name)
            if parsed is None:
                continue
            kind, month = parsed
            months.setdefault(month, {})[kind] = os.path.join(scan_dir, name)
    pairs: list[tuple[str | None, str | None]] = []
    for month in sorted(months):
        rs = months[month].get("RS")
        rc = months[month].get("RC")
        if not (rs and rc):
            missing = "RC" if rs else "RS"
            print_warning(f"Month {month}: no {missing}_{month}.zst — processing the available file only")
        pairs.append((rs, rc))
    return pairs


def sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    """Streaming SHA256 of a file (dumps can be tens of GB)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _import_one_file(
    db: Any,
    importer: ArcticShiftImporter,
    file_path: str,
    kind: str,
    tracked: set[str],
    affected_subs: set[str],
    affected_users: set[str],
) -> dict[str, int]:
    """Stream one dump file into the database; returns matched/failed counts."""
    basename = os.path.basename(file_path)
    parsed = parse_dump_filename(file_path)
    month = parsed[1] if parsed else None

    print_info(f"Hashing {basename} ...", indent=1)
    file_hash = sha256_file(file_path)
    if db.is_dump_already_imported(file_hash):
        print_warning(f"{basename} already imported (hash match) — skipping", indent=1)
        return {"matched": 0, "failed": 0, "skipped": 1}

    update_id = db.record_update_start(basename, file_hash, month)

    stream = importer.stream_posts if kind == "posts" else importer.stream_comments
    insert = db.insert_posts_batch if kind == "posts" else db.insert_comments_batch

    matched = 0
    failed = 0
    batch: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal matched, failed
        if not batch:
            return
        # insert_posts_batch returns (ok, bad, failed_ids); insert_comments_batch (ok, bad)
        result = insert(batch)
        matched += result[0]
        failed += result[1]
        batch.clear()

    print_info(f"Streaming {basename} (filtering {len(tracked)} tracked subreddits) ...", indent=1)
    for obj in stream(file_path, filter_communities=tracked):
        if obj.get("subreddit"):
            affected_subs.add(obj["subreddit"])
        author = obj.get("author")
        if author and author != "[deleted]":
            affected_users.add(author)
        batch.append(obj)
        if len(batch) >= BATCH_SIZE:
            flush()
    flush()

    if update_id is not None:
        db.record_update_complete(
            update_id,
            posts_matched=matched if kind == "posts" else 0,
            posts_failed=failed if kind == "posts" else 0,
            comments_matched=matched if kind == "comments" else 0,
            comments_failed=failed if kind == "comments" else 0,
            affected_subreddits=list(affected_subs),
            affected_users=list(affected_users),
        )
    print_success(f"{basename}: {matched:,} {kind} upserted ({failed} failed)", indent=1)
    return {"matched": matched, "failed": failed, "skipped": 0}


def run_update(
    db: Any,
    submissions_file: str | None = None,
    comments_file: str | None = None,
) -> dict[str, Any]:
    """Import one month's Arctic Shift dump pair into an existing archive.

    Either file may be omitted (submissions-only or comments-only run).
    Returns a summary with counts and the affected subreddits/users.
    """
    db.create_update_history_table()
    tracked = set(db.get_archived_subreddit_names("reddit"))
    if not tracked:
        print_warning("No tracked Reddit subreddits in the database — nothing to update. Import an archive first.")
        return {"posts": 0, "comments": 0, "affected_subreddits": [], "affected_users": [], "skipped_files": 0}

    importer = ArcticShiftImporter()
    affected_subs: set[str] = set()
    affected_users: set[str] = set()
    posts = comments = skipped = 0

    if submissions_file:
        r = _import_one_file(db, importer, submissions_file, "posts", tracked, affected_subs, affected_users)
        posts, skipped = r["matched"], skipped + r["skipped"]
    if comments_file:
        r = _import_one_file(db, importer, comments_file, "comments", tracked, affected_subs, affected_users)
        comments, skipped = r["matched"], skipped + r["skipped"]

    # Refresh statistics so dashboards (and dynamic mode) reflect the new data
    for sub in sorted(affected_subs):
        try:
            stats = db.calculate_subreddit_statistics(sub)
            db.save_subreddit_statistics(sub, stats)
        except Exception as e:
            print_warning(f"Failed to refresh statistics for r/{sub}: {e}", indent=1)

    return {
        "posts": posts,
        "comments": comments,
        "affected_subreddits": sorted(affected_subs),
        "affected_users": sorted(affected_users),
        "skipped_files": skipped,
    }
