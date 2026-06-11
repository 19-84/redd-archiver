# ABOUTME: Selective re-export after incremental updates — regenerates only the
# ABOUTME: pages affected by new data instead of the whole archive (Feature 3 Phase 3).
"""Selective re-export.

After an incremental update, only these pages can be stale:
- listing pages of affected subreddits (ordering/pagination changed)
- title/flair index pages of affected subreddits
- user pages of authors with new activity
- the dashboard, archive map, and sitemaps
- post pages for NEW posts (existing post pages are immutable here)

The static writers skip files that already exist, so refreshing means
deleting the stale artifacts first, then re-running the per-subreddit export
for affected subreddits only. Post pages reuse that skip behavior: only
pages for newly imported posts get written.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from html_modules.platform_utils import get_url_prefix
from utils.console_output import print_info, print_section, print_success, print_warning

# Per-subreddit listing artifacts to refresh (relative to {prefix}/{sub}/).
# comments/ (post pages), about/, and wiki/ are deliberately untouched.
_LISTING_DIRS = ["index-comments", "index-date", "titles", "flair"]


def _delete_subreddit_listings(prefix: str, subreddit: str) -> None:
    base = os.path.join(prefix, subreddit)
    if not os.path.isdir(base):
        return
    for name in os.listdir(base):
        if name.startswith("index") and name.endswith(".html"):
            os.unlink(os.path.join(base, name))
    for d in _LISTING_DIRS:
        path = os.path.join(base, d)
        if os.path.isdir(path):
            shutil.rmtree(path)


def _delete_user_pages(usernames: list[str]) -> int:
    deleted = 0
    for username in usernames:
        # user dirs are written from sanitized usernames; only handle the plain case
        path = os.path.join("user", username)
        if os.path.isdir(path):
            shutil.rmtree(path)
            deleted += 1
    return deleted


def selective_reexport(
    db: Any,
    output_dir: str,
    affected_subreddits: list[str],
    affected_users: list[str],
    args: Any,
) -> None:
    """Regenerate only the pages affected by an incremental update.

    Runs with cwd switched to ``output_dir`` (matching the full-export flow).
    """
    from core.write_html import process_subreddit_database_backed
    from html_modules.html_pages_jinja import write_user_page_jinja2
    from processing.incremental_statistics import IncrementalStatistics
    from reddarc import create_global_seo_config, finalize_archive_with_stats

    if not affected_subreddits:
        print_info("No affected subreddits — nothing to re-export")
        return

    print_section(f"Selective re-export: {len(affected_subreddits)} subreddit(s), {len(affected_users)} user(s)")
    os.makedirs(output_dir, exist_ok=True)
    original_cwd = os.getcwd()
    os.chdir(output_dir)
    try:
        seo_config = create_global_seo_config(args, ".")
        all_subreddits = db.get_all_imported_subreddits()

        # 1. Drop stale listing pages so the skip-if-exists writers regenerate them.
        # User dirs are only dropped when they will be regenerated below.
        regenerate_users = bool(affected_users) and not getattr(args, "no_user_pages", False)
        for sub in affected_subreddits:
            sample = next(db.get_posts_paginated(sub, limit=1), None)
            prefix = get_url_prefix((sample or {}).get("platform", "reddit"))
            _delete_subreddit_listings(prefix, sub)
        removed_users = _delete_user_pages(affected_users) if regenerate_users else 0
        print_info(f"Cleared stale listings for {len(affected_subreddits)} subreddit(s), {removed_users} user dir(s)")

        # 2. Re-export affected subreddits (new post pages + listings + titles/flair)
        for i, sub in enumerate(affected_subreddits, 1):
            print_section(f"Re-exporting r/{sub} ({i}/{len(affected_subreddits)})")
            try:
                process_subreddit_database_backed(sub, db, all_subreddits, seo_config, args)
            except Exception as e:
                print_warning(f"Re-export failed for r/{sub}: {e}")

        # 3. Regenerate affected user pages from the database
        if regenerate_users:
            stats_rows = db.get_all_subreddit_statistics_from_db()
            subs_with_stats = [{"name": row["subreddit"], "stats": dict(row)} for row in stats_rows]
            regenerated = 0
            for username in affected_users:
                try:
                    user_data = db.get_user_activity(username, min_score=args.min_score, min_comments=args.min_comments)
                    if user_data.get("all_content") and write_user_page_jinja2(
                        username, user_data, subs_with_stats, seo_config
                    ):
                        regenerated += 1
                except Exception as e:
                    print_warning(f"User page failed for u/{username}: {e}")
            print_success(f"Regenerated {regenerated} user page(s)")

        # 4. Dashboard, archive map, sitemaps, robots.txt
        stats_manager = IncrementalStatistics(output_dir, postgres_db=db)
        finalize_archive_with_stats(
            stats_manager,
            [],
            seo_config,
            postgres_db=db,
            min_score=args.min_score,
            min_comments=args.min_comments,
        )
        print_success("Selective re-export complete")
    finally:
        os.chdir(original_cwd)
