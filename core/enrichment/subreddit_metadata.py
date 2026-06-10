# ABOUTME: Import subreddit descriptions/rules/wikis from Arctic Shift dumps into
# ABOUTME: an existing archive, filtered to tracked subreddits (Feature 6).
"""Subreddit metadata enrichment importer.

Streams the Arctic Shift subreddit dumps (`subreddits_*.zst`,
`subreddit_rules_*.zst`, `subreddit_wikis_*.zst`) with constant memory, keeps
only records for subreddits already in the archive, renders moderator markdown
to sanitized HTML once, and upserts into the `subreddit_metadata` /
`subreddit_rules` / `subreddit_wiki_pages` tables.

This is intentionally NOT a `BaseImporter` subclass — that interface models
posts/comments, while this imports subreddit-level metadata.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from core.watchful import read_lines_zst
from utils.console_output import print_info, print_success, print_warning
from utils.markdown_render import render_reddit_markdown, sanitize_html

# Wiki dump records carry no `subreddit` field — it is encoded in the path as
# `/r/{subreddit}/wiki/{page}`. Page paths become output directories, so every
# segment is restricted to a safe character set (no dots → no traversal, no
# hidden files). Verified against the 2025-01 dump: all paths match.
_WIKI_PATH_RE = re.compile(r"^/r/([A-Za-z0-9_-]+)/wiki/((?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+)$")


def _to_dt(ts: Any) -> datetime | None:
    """Convert a Unix timestamp (int/float) to a tz-aware UTC datetime, or None."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _iso_to_dt(value: Any) -> datetime | None:
    """Convert an ISO-8601 string (wiki `revision_date`) to a datetime, or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_wiki_path(path: Any) -> tuple[str, str] | None:
    """Split a wiki dump path `/r/{sub}/wiki/{page}` into (subreddit, page_path).

    Returns None for malformed or unsafe paths (anything outside
    ``[A-Za-z0-9_-]`` segments), which the importer skips.
    """
    if not isinstance(path, str):
        return None
    m = _WIKI_PATH_RE.match(path)
    if not m:
        return None
    return m.group(1), m.group(2)


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
    """Stream a subreddits_*.zst dump, importing metadata for tracked subreddits.

    The dump is a snapshot with one record per subreddit, so the scan stops as
    soon as every tracked subreddit has been seen. Only tracked subreddits
    absent from the dump force a full scan (absence can't be proven earlier).
    """
    print_info(f"Enriching subreddit metadata from {os.path.basename(metadata_file)} ...")
    imported = 0
    scanned = 0
    found: set[str] = set()
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
        found.add(name)
        if len(found) == len(tracked):
            print_info(f"All {len(tracked)} tracked subreddit(s) found — stopping scan early", indent=1)
            break
    print_success(f"Imported metadata for {imported} subreddit(s) (scanned {scanned:,} records)")
    return imported


def import_rules(db: Any, rules_file: str, tracked: set[str], platform: str = "reddit") -> int:
    """Stream a subreddit_rules_*.zst dump, importing rules for tracked subreddits.

    One record per subreddit (the full rules array), so like ``import_metadata``
    the scan stops once every tracked subreddit has been seen.
    """
    print_info(f"Enriching subreddit rules from {os.path.basename(rules_file)} ...")
    imported = 0
    found: set[str] = set()
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
        found.add(subreddit.lower())
        if len(found) == len(tracked):
            print_info(f"All {len(tracked)} tracked subreddit(s) found — stopping scan early", indent=1)
            break
    print_success(f"Imported rules for {imported} subreddit(s)")
    return imported


def import_wikis(db: Any, wikis_file: str, tracked: set[str], platform: str = "reddit") -> int:
    """Stream a subreddit_wikis_*.zst dump, importing wiki pages for tracked subreddits."""
    print_info(f"Enriching wiki pages from {os.path.basename(wikis_file)} ...")
    imported = 0
    subs: set[str] = set()
    for line, _ in read_lines_zst(wikis_file):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed = parse_wiki_path(obj.get("path"))
        if not parsed:
            continue
        subreddit, page_path = parsed
        if subreddit.lower() not in tracked:
            continue
        page = {
            "path": page_path,
            "content": obj.get("content") or "",
            "content_html": render_reddit_markdown(obj.get("content")),
            "revision_author": obj.get("revision_author"),
            "revision_date": _iso_to_dt(obj.get("revision_date")),
            "revision_reason": obj.get("revision_reason"),
            "retrieved_on": _to_dt(obj.get("retrieved_on")),
        }
        if db.save_wiki_page(subreddit, platform, page):
            imported += 1
            subs.add(subreddit.lower())
    print_success(f"Imported {imported} wiki page(s) for {len(subs)} subreddit(s)")
    return imported


def _detect_files(directory: str) -> dict[str, str | None]:
    """Locate metadata + rules + wiki dumps in a directory by filename convention."""
    full_meta = None
    meta_only = None
    rules = None
    wikis = None
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".zst"):
            continue
        path = os.path.join(directory, fname)
        if fname.startswith("subreddit_rules_"):
            rules = path
        elif fname.startswith("subreddit_wikis_"):
            wikis = path
        elif fname.startswith("subreddits_meta_only_"):
            meta_only = path
        elif fname.startswith("subreddits_"):
            full_meta = path
    # Prefer the full metadata dump; fall back to the lightweight one.
    return {"metadata": full_meta or meta_only, "rules": rules, "wikis": wikis}


# Per-subreddit split dumps produced by tools/split_subreddit_dumps.py, named
# like the per-subreddit post dumps ({Sub}_comments.zst): one small file per
# subreddit instead of a monolithic 22M-record scan.
_SPLIT_SUFFIXES = {"_metadata.zst": "metadata", "_rules.zst": "rules", "_wiki.zst": "wikis"}


def _detect_split_files(directory: str, tracked: set[str]) -> dict[str, list[str]]:
    """Locate per-subreddit split dump files for tracked subreddits."""
    found: dict[str, list[str]] = {"metadata": [], "rules": [], "wikis": []}
    for fname in sorted(os.listdir(directory)):
        for suffix, kind in _SPLIT_SUFFIXES.items():
            if fname.endswith(suffix):
                if fname[: -len(suffix)].lower() in tracked:
                    found[kind].append(os.path.join(directory, fname))
                break
    return found


def enrich(
    db: Any,
    path: str | None,
    tracked: set[str],
    platform: str = "reddit",
    metadata_file: str | None = None,
    rules_file: str | None = None,
    wikis_file: str | None = None,
) -> dict[str, int]:
    """Run enrichment.

    `path` may be a directory or None when explicit `metadata_file` /
    `rules_file` / `wikis_file` overrides are given. A directory may hold the
    monolithic dumps and/or per-subreddit split files
    (tools/split_subreddit_dumps.py); split files matching tracked subreddits
    take precedence per dump kind, skipping the monolith scan entirely.
    """
    if not tracked:
        print_warning("No tracked subreddits in the database — nothing to enrich. Import posts first.")
        return {"metadata": 0, "rules": 0, "wikis": 0}

    metadata_files = [metadata_file] if metadata_file else []
    rules_files = [rules_file] if rules_file else []
    wikis_files = [wikis_file] if wikis_file else []

    if path and os.path.isdir(path):
        split = _detect_split_files(path, tracked)
        detected = _detect_files(path)
        metadata_files = metadata_files or split["metadata"] or ([detected["metadata"]] if detected["metadata"] else [])
        rules_files = rules_files or split["rules"] or ([detected["rules"]] if detected["rules"] else [])
        wikis_files = wikis_files or split["wikis"] or ([detected["wikis"]] if detected["wikis"] else [])
    elif path and os.path.isfile(path):
        # A single file passed positionally: dispatch by name.
        base = os.path.basename(path)
        if base.startswith("subreddit_rules_") or base.endswith("_rules.zst"):
            rules_files = rules_files or [path]
        elif base.startswith("subreddit_wikis_") or base.endswith("_wiki.zst"):
            wikis_files = wikis_files or [path]
        else:
            metadata_files = metadata_files or [path]

    counts = {"metadata": 0, "rules": 0, "wikis": 0}
    if metadata_files:
        for f in metadata_files:
            counts["metadata"] += import_metadata(db, f, tracked, platform)
    else:
        print_warning("No subreddit metadata dump found (subreddits_*.zst or {sub}_metadata.zst)")
    if rules_files:
        for f in rules_files:
            counts["rules"] += import_rules(db, f, tracked, platform)
    else:
        print_warning("No subreddit rules dump found (subreddit_rules_*.zst or {sub}_rules.zst)")
    if wikis_files:
        for f in wikis_files:
            counts["wikis"] += import_wikis(db, f, tracked, platform)
    else:
        print_warning("No subreddit wikis dump found (subreddit_wikis_*.zst or {sub}_wiki.zst)")
    return counts
