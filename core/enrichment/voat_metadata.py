# ABOUTME: Import Voat subverse metadata from the searchvoat.co SQL dump into
# ABOUTME: an existing archive, filtered to tracked subverses (Feature 7 Phase 1).
"""Voat subverse metadata enrichment importer.

Streams ``subverse.sql.gz`` from the Voat SQL archive (voat-sql-tables.tar),
keeps only records for subverses already in the archive, sanitizes the
pre-rendered sidebar HTML, and upserts into the shared ``subreddit_metadata``
table with ``platform='voat'``.

Unlike Feature 6's Reddit pipeline there is no markdown rendering step:
Voat's ``formattedSidebar`` is already HTML from Voat's own renderer and only
needs XSS sanitization.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from core.importers.voat_sql_parser import VoatSQLParser
from utils.console_output import print_info, print_success, print_warning
from utils.markdown_render import sanitize_html

# Metadata files inside voat-sql-tables.tar
SUBVERSE_FILENAME = "subverse.sql.gz"
USER_FILENAME = "user.sql.gz"
MODERATOR_FILENAME = "subverseModerator.sql.gz"
ATTRIBUTE_FILENAME = "submissionAttribute.sql.gz"
SUBSCRIBERS_FILENAME = "subverseSubscribers.sql.gz"
BADGE_FILENAME = "userBadge.sql.gz"

# Stripped from user rows before storage. svpassword is always empty in the
# dump but must never be persisted; the fetch* fields are scraper bookkeeping.
SENSITIVE_USER_FIELDS = {"svpassword"}


def _to_unix(value: Any) -> int | None:
    """Convert a MariaDB datetime string ('2015-12-03 16:22:32', UTC) to a Unix timestamp."""
    if not value or not isinstance(value, str):
        return None
    try:
        return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def parse_moderators(value: Any) -> list[dict[str, Any]]:
    """Parse the semicolon-separated ``moderators`` field into a structured list.

    ``'DerpyPigSauce;T4C0M4ST3R'`` -> ``[{"username": "DerpyPigSauce"}, ...]``.
    The richer per-moderator levels/dates live in the subverseModerator table
    (Feature 7 Phase 3); this captures the names available in Phase 1.
    """
    if not value or not isinstance(value, str):
        return []
    return [{"username": name.strip()} for name in value.split(";") if name.strip()]


def map_subverse(row: dict[str, Any]) -> dict[str, Any]:
    """Map a ``subverse`` table row to subreddit_metadata columns.

    Voat's ``type`` (link/text content type) is deliberately NOT mapped to
    ``subreddit_type`` (an access level on Reddit) — it is preserved in
    ``raw_json`` only.
    """
    moderators = parse_moderators(row.get("moderators"))
    return {
        "display_name": row.get("name"),
        "title": row.get("title"),
        "description": row.get("sidebar"),
        "description_html": sanitize_html(row.get("formattedSidebar")),
        "public_description": row.get("description"),
        "public_description_html": "",
        "subscribers": row.get("subscriberCount"),
        "created_utc": _to_unix(row.get("creationDate")),
        "over_18": bool(row.get("isAdult")),
        "created_by": row.get("createdBy"),
        "is_deleted": bool(row.get("isDeleted")),
        "moderators_json": moderators or None,
        "raw_json": row,
    }


def map_user(row: dict[str, Any]) -> dict[str, Any]:
    """Map a ``user`` table row to user_metadata columns, stripping sensitive fields."""
    raw = {k: v for k, v in row.items() if k not in SENSITIVE_USER_FIELDS}
    return {
        "bio": (row.get("bio") or "").strip() or None,
        "registration_date": _to_unix(row.get("registrationDate")),
        "profile_picture": (row.get("profilePicture") or "").strip() or None,
        "comment_karma": row.get("commentPointsSum"),
        "submission_karma": row.get("submissionPointsSum"),
        "is_bot": bool(row.get("isBot")),
        "is_deleted": bool(row.get("isDeleted")),
        "raw_json": raw,
    }


def import_users(db: Any, user_file: str, tracked_users: dict[str, str]) -> int:
    """Stream user.sql.gz, importing profiles for authors archived in this database.

    ``tracked_users`` maps lowercased author names to their exact stored case
    (:meth:`get_archived_author_names`). Rows are saved under the dump's own
    username casing; lookups are case-insensitive.
    """
    print_info(f"Enriching user profiles from {os.path.basename(user_file)} ...")
    parser = VoatSQLParser()
    imported = 0
    scanned = 0
    found: set[str] = set()
    for row in parser.stream_rows(user_file, "user"):
        scanned += 1
        name = row.get("userName") if isinstance(row.get("userName"), str) else ""
        lname = name.lower()
        if not lname or lname not in tracked_users or lname in found:
            continue
        if db.save_user_metadata(name, "voat", map_user(row)):
            imported += 1
        found.add(lname)
        if len(found) == len(tracked_users):
            print_info(f"All {len(tracked_users)} tracked user(s) found — stopping scan early", indent=1)
            break
    print_success(f"Imported profiles for {imported} user(s) (scanned {scanned:,} records)")
    return imported


def import_moderators(db: Any, moderator_file: str, tracked: dict[str, str]) -> int:
    """Stream subverseModerator.sql.gz, replacing tracked subverses' moderator lists.

    The structured table (with permission levels and date ranges) supersedes the
    semicolon-separated name list Phase 1 stored. Returns subverses updated.
    """
    print_info(f"Enriching moderators from {os.path.basename(moderator_file)} ...")
    parser = VoatSQLParser()
    by_subverse: dict[str, list[dict[str, Any]]] = {}
    scanned = 0
    # The table has a `subverse` column, so the parser's built-in filter applies
    for row in parser.stream_rows(moderator_file, "subverseModerator", filter_subverses=list(tracked.values())):
        scanned += 1
        name = row.get("username")
        sub = row.get("subverse") or ""
        if not name or sub.lower() not in tracked:
            continue
        by_subverse.setdefault(sub.lower(), []).append(
            {
                "username": name,
                "level": row.get("level"),
                "first_date": row.get("firstDate"),
                "last_date": row.get("lastDate"),
            }
        )
    updated = 0
    for lsub, mods in by_subverse.items():
        # Owners first, then moderators, then the rest; stable within level
        order = {"Owner": 0, "Moderator": 1}
        mods.sort(key=lambda m: order.get(m.get("level"), 2))
        if db.update_moderators_json(tracked[lsub], "voat", mods):
            updated += 1
    print_success(f"Updated structured moderators for {updated} subverse(s) ({scanned:,} records matched)")
    return updated


def import_flair(db: Any, attribute_file: str) -> int:
    """Stream submissionAttribute.sql.gz, setting link_flair_text on archived posts.

    Only rows with ``type='Flair'`` carry user-visible flair (``name``); the
    far more numerous ``type='Data'`` rows are system labels (Anon/NSFW/
    Archived) and are skipped. Returns posts updated. First flair wins when a
    post somehow has several.
    """
    print_info(f"Enriching post flair from {os.path.basename(attribute_file)} ...")
    archived_ids = db.get_post_ids_for_platform("voat")
    if not archived_ids:
        print_warning("No archived Voat posts — skipping flair enrichment", indent=1)
        return 0
    parser = VoatSQLParser()
    updates: dict[str, str] = {}
    scanned = 0
    total = 0
    for row in parser.stream_rows(attribute_file, "submissionAttribute"):
        scanned += 1
        if row.get("type") != "Flair":
            continue
        # name can parse as a number for purely numeric flairs — coerce to str
        raw_name = row.get("name")
        flair = str(raw_name).strip() if raw_name is not None else ""
        if not flair:
            continue
        post_id = f"voat_{row.get('submissionid')}"
        if post_id not in archived_ids or post_id in updates:
            continue
        updates[post_id] = flair
        if len(updates) >= 5000:
            total += db.update_post_flair_batch(updates)
            updates.clear()
    total += db.update_post_flair_batch(updates)
    print_success(f"Set flair on {total} post(s) (scanned {scanned:,} attribute records)")
    return total


def import_subscribers(db: Any, subscribers_file: str, tracked: dict[str, str]) -> int:
    """Stream subverseSubscribers.sql.gz, importing daily counts for tracked subverses.

    Returns data points written. The series powers the subscriber sparkline on
    about pages (server-rendered SVG — no JavaScript).
    """
    print_info(f"Enriching subscriber history from {os.path.basename(subscribers_file)} ...")
    parser = VoatSQLParser()
    by_subverse: dict[str, list[tuple[str, int]]] = {}
    for row in parser.stream_rows(subscribers_file, "subverseSubscribers", filter_subverses=list(tracked.values())):
        sub = (row.get("subverse") or "").lower() if isinstance(row.get("subverse"), str) else ""
        date = row.get("date")
        count = row.get("count")
        if sub not in tracked or not date or count is None:
            continue
        by_subverse.setdefault(sub, []).append((str(date), int(count)))
    total = 0
    for lsub, points in by_subverse.items():
        total += db.save_subscriber_history_batch(tracked[lsub], "voat", points)
    print_success(f"Imported {total:,} subscriber data point(s) for {len(by_subverse)} subverse(s)")
    return total


def import_badges(db: Any, badge_file: str, tracked_users: dict[str, str]) -> int:
    """Stream userBadge.sql.gz, attaching badge lists to enriched user profiles.

    Returns users updated. Only users already in user_metadata receive badges
    (the UPDATE is a no-op for unknown users).
    """
    print_info(f"Enriching user badges from {os.path.basename(badge_file)} ...")
    parser = VoatSQLParser()
    by_user: dict[str, list[dict[str, Any]]] = {}
    for row in parser.stream_rows(badge_file, "userBadge"):
        name = row.get("username") if isinstance(row.get("username"), str) else ""
        lname = name.lower()
        if not lname or lname not in tracked_users:
            continue
        by_user.setdefault(lname, []).append(
            {
                "name": str(row.get("name") or ""),
                "description": str(row.get("description") or ""),
                "awarded": row.get("creationdate"),
            }
        )
    updated = 0
    for lname, badges in by_user.items():
        if db.update_user_badges(tracked_users[lname], "voat", badges):
            updated += 1
    print_success(f"Attached badges to {updated} user(s)")
    return updated


def import_subverses(db: Any, subverse_file: str, tracked: dict[str, str]) -> int:
    """Stream subverse.sql.gz, importing metadata for tracked subverses.

    ``tracked`` maps lowercased archived names to their exact stored case
    (:meth:`get_archived_subreddit_names`). Voat had case-distinct subverses
    (Linux vs linux), so when several dump rows fold to the same tracked name,
    the row whose name matches the archive's exact case wins; a case-variant
    row is only used as a fallback when no exact match exists in the dump.
    """
    print_info(f"Enriching subverse metadata from {os.path.basename(subverse_file)} ...")
    parser = VoatSQLParser()
    imported = 0
    scanned = 0
    exact_done: set[str] = set()
    fallbacks: dict[str, dict[str, Any]] = {}
    for row in parser.stream_rows(subverse_file, "subverse"):
        scanned += 1
        name = row.get("name") if isinstance(row.get("name"), str) else ""
        lname = name.lower()
        if not lname or lname not in tracked or lname in exact_done:
            continue
        if name == tracked[lname]:
            if db.save_subreddit_metadata(name, "voat", map_subverse(row)):
                imported += 1
            exact_done.add(lname)
            fallbacks.pop(lname, None)
            if len(exact_done) == len(tracked):
                print_info(f"All {len(tracked)} tracked subverse(s) found — stopping scan early", indent=1)
                break
        else:
            fallbacks.setdefault(lname, row)
    for lname, row in fallbacks.items():
        if lname in exact_done:
            continue
        print_warning(f"No exact-case match for {tracked[lname]!r}; using case-variant {row['name']!r}", indent=1)
        if db.save_subreddit_metadata(row["name"], "voat", map_subverse(row)):
            imported += 1
    print_success(f"Imported metadata for {imported} subverse(s) (scanned {scanned:,} records)")
    return imported


def enrich_voat(db: Any, path: str, tracked: dict[str, str]) -> dict[str, int]:
    """Run Voat enrichment (Phase 1: subverse metadata; Phase 2: user profiles).

    ``path`` may be the extracted voat-sql-tables directory (auto-detects
    ``subverse.sql.gz`` and ``user.sql.gz``) or a single one of those files.
    ``tracked`` is the {lower: exact} name map of archived Voat communities.
    """
    if not tracked:
        print_warning("No tracked Voat subverses in the database — nothing to enrich. Import Voat posts first.")
        return {"subverses": 0, "users": 0, "moderators": 0, "flair": 0, "subscriber_points": 0, "badged_users": 0}

    files: dict[str, str | None] = {
        SUBVERSE_FILENAME: None,
        USER_FILENAME: None,
        MODERATOR_FILENAME: None,
        ATTRIBUTE_FILENAME: None,
        SUBSCRIBERS_FILENAME: None,
        BADGE_FILENAME: None,
    }
    if os.path.isdir(path):
        for fname in files:
            candidate = os.path.join(path, fname)
            if os.path.isfile(candidate):
                files[fname] = candidate
    elif os.path.isfile(path):
        base = os.path.basename(path)
        files[base if base in files else SUBVERSE_FILENAME] = path

    counts = {"subverses": 0, "users": 0, "moderators": 0, "flair": 0, "subscriber_points": 0, "badged_users": 0}
    if files[SUBVERSE_FILENAME]:
        counts["subverses"] = import_subverses(db, files[SUBVERSE_FILENAME], tracked)
    else:
        print_warning(f"No {SUBVERSE_FILENAME} found in {path} (extract voat-sql-tables.tar first)")
    if files[MODERATOR_FILENAME]:
        counts["moderators"] = import_moderators(db, files[MODERATOR_FILENAME], tracked)
    if files[ATTRIBUTE_FILENAME]:
        counts["flair"] = import_flair(db, files[ATTRIBUTE_FILENAME])
    if files[USER_FILENAME]:
        db.create_user_metadata_table()
        tracked_users = db.get_archived_author_names("voat")
        if tracked_users:
            counts["users"] = import_users(db, files[USER_FILENAME], tracked_users)
        else:
            print_warning("No archived Voat authors found — skipping user profile enrichment")
    if files[SUBSCRIBERS_FILENAME]:
        db.create_subscriber_history_table()
        counts["subscriber_points"] = import_subscribers(db, files[SUBSCRIBERS_FILENAME], tracked)
    if files[BADGE_FILENAME]:
        db.create_subscriber_history_table()  # also adds badges_json (migration 012)
        tracked_users = db.get_archived_author_names("voat")
        if tracked_users:
            counts["badged_users"] = import_badges(db, files[BADGE_FILENAME], tracked_users)
    return counts
