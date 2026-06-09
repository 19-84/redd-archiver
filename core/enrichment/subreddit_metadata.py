# ABOUTME: Import subreddit descriptions/rules from Arctic Shift dumps into an
# ABOUTME: existing archive, filtered to tracked subreddits (Feature 6, Phase 1).
"""Subreddit metadata enrichment importer.

Streams the Arctic Shift subreddit dumps (`subreddits_*.zst`,
`subreddit_rules_*.zst`) with constant memory, keeps only records for subreddits
already in the archive, renders moderator markdown to sanitized HTML once, and
upserts into the `subreddit_metadata` / `subreddit_rules` tables.

This is intentionally NOT a `BaseImporter` subclass — that interface models
posts/comments, while this imports subreddit-level metadata.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from core.watchful import read_lines_zst
from utils.console_output import print_info, print_success, print_warning
from utils.markdown_render import render_reddit_markdown, sanitize_html


def _to_dt(ts: Any) -> datetime | None:
    """Convert a Unix timestamp (int/float) to a tz-aware UTC datetime, or None."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _map_metadata(obj: dict[str, Any]) -> dict[str, Any]:
    """Map an Arctic Shift subreddit record to subreddit_metadata columns."""
    return {
        "display_name": obj.get("display_name"),
        "title": obj.get("title"),
        "description": obj.get("description"),
        "description_html": render_reddit_markdown(obj.get("description")),
        "public_description": obj.get("public_description"),
        "public_description_html": render_reddit_markdown(obj.get("public_description")),
        "subreddit_type": obj.get("subreddit_type"),
        "lang": obj.get("lang"),
        "subscribers": obj.get("subscribers"),
        "active_users": obj.get("active_user_count") or obj.get("accounts_active"),
        "created_utc": obj.get("created_utc"),
        "over_18": bool(obj.get("over18")),
        "quarantine": bool(obj.get("quarantine")),
        "quarantine_message": obj.get("quarantine_message"),
        "quarantine_message_html": sanitize_html(obj.get("quarantine_message_html")),
        "submission_type": obj.get("submission_type"),
        "suggested_comment_sort": obj.get("suggested_comment_sort"),
        "icon_img": obj.get("icon_img"),
        "community_icon": obj.get("community_icon"),
        "banner_img": obj.get("banner_img"),
        "key_color": obj.get("key_color"),
        "primary_color": obj.get("primary_color"),
        "banner_background_color": obj.get("banner_background_color"),
        "link_flair_enabled": bool(obj.get("link_flair_enabled")),
        "submit_text": obj.get("submit_text"),
        "submit_text_html": sanitize_html(obj.get("submit_text_html")),
        "retrieved_on": _to_dt(obj.get("retrieved_on")),
        "raw_json": obj,
    }


def import_metadata(db: Any, metadata_file: str, tracked: set[str], platform: str = "reddit") -> int:
    """Stream a subreddits_*.zst dump, importing metadata for tracked subreddits."""
    print_info(f"Enriching subreddit metadata from {os.path.basename(metadata_file)} ...")
    imported = 0
    scanned = 0
    for line, _ in read_lines_zst(metadata_file):
        scanned += 1
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = (obj.get("display_name") or "").lower()
        if not name or name not in tracked:
            continue
        if db.save_subreddit_metadata(obj.get("display_name"), platform, _map_metadata(obj)):
            imported += 1
    print_success(f"Imported metadata for {imported} subreddit(s) (scanned {scanned:,} records)")
    return imported


def import_rules(db: Any, rules_file: str, tracked: set[str], platform: str = "reddit") -> int:
    """Stream a subreddit_rules_*.zst dump, importing rules for tracked subreddits."""
    print_info(f"Enriching subreddit rules from {os.path.basename(rules_file)} ...")
    imported = 0
    for line, _ in read_lines_zst(rules_file):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        subreddit = obj.get("subreddit") or ""
        if subreddit.lower() not in tracked:
            continue
        retrieved_on = _to_dt(obj.get("retrieved_on"))
        rules = []
        for rule in obj.get("rules") or []:
            rules.append(
                {
                    "priority": rule.get("priority", 0),
                    "short_name": rule.get("short_name"),
                    "description": rule.get("description"),
                    "description_html": render_reddit_markdown(rule.get("description")),
                    "kind": rule.get("kind"),
                    "violation_reason": rule.get("violation_reason"),
                    "rule_created_utc": rule.get("created_utc"),
                    "retrieved_on": retrieved_on,
                }
            )
        if db.save_subreddit_rules(subreddit, platform, rules):
            imported += 1
    print_success(f"Imported rules for {imported} subreddit(s)")
    return imported


def _detect_files(directory: str) -> dict[str, str | None]:
    """Locate metadata + rules dumps in a directory by filename convention."""
    full_meta = None
    meta_only = None
    rules = None
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".zst"):
            continue
        path = os.path.join(directory, fname)
        if fname.startswith("subreddit_rules_"):
            rules = path
        elif fname.startswith("subreddits_meta_only_"):
            meta_only = path
        elif fname.startswith("subreddits_"):
            full_meta = path
    # Prefer the full metadata dump; fall back to the lightweight one.
    return {"metadata": full_meta or meta_only, "rules": rules}


def enrich(
    db: Any,
    path: str | None,
    tracked: set[str],
    platform: str = "reddit",
    metadata_file: str | None = None,
    rules_file: str | None = None,
) -> dict[str, int]:
    """Run enrichment.

    `path` may be a directory (auto-detect dumps) or None when explicit
    `metadata_file` / `rules_file` overrides are given.
    """
    if path and os.path.isdir(path):
        detected = _detect_files(path)
        metadata_file = metadata_file or detected["metadata"]
        rules_file = rules_file or detected["rules"]
    elif path and os.path.isfile(path):
        # A single file passed positionally: dispatch by name.
        base = os.path.basename(path)
        if base.startswith("subreddit_rules_"):
            rules_file = rules_file or path
        else:
            metadata_file = metadata_file or path

    if not tracked:
        print_warning("No tracked subreddits in the database — nothing to enrich. Import posts first.")
        return {"metadata": 0, "rules": 0}

    counts = {"metadata": 0, "rules": 0}
    if metadata_file:
        counts["metadata"] = import_metadata(db, metadata_file, tracked, platform)
    else:
        print_warning("No subreddit metadata dump found (subreddits_*.zst)")
    if rules_file:
        counts["rules"] = import_rules(db, rules_file, tracked, platform)
    else:
        print_warning("No subreddit rules dump found (subreddit_rules_*.zst)")
    return counts
