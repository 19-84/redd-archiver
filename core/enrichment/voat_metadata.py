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

# The subverse metadata file inside voat-sql-tables.tar
SUBVERSE_FILENAME = "subverse.sql.gz"


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
    """Run Voat enrichment (Phase 1: subverse metadata).

    ``path`` may be the extracted voat-sql-tables directory (auto-detects
    ``subverse.sql.gz``) or the file itself. ``tracked`` is the
    {lower: exact} name map of archived Voat communities.
    """
    if not tracked:
        print_warning("No tracked Voat subverses in the database — nothing to enrich. Import Voat posts first.")
        return {"subverses": 0}

    subverse_file = None
    if os.path.isdir(path):
        candidate = os.path.join(path, SUBVERSE_FILENAME)
        if os.path.isfile(candidate):
            subverse_file = candidate
    elif os.path.isfile(path):
        subverse_file = path

    counts = {"subverses": 0}
    if subverse_file:
        counts["subverses"] = import_subverses(db, subverse_file, tracked)
    else:
        print_warning(f"No {SUBVERSE_FILENAME} found in {path} (extract voat-sql-tables.tar first)")
    return counts
