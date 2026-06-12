# ABOUTME: Voat post thumbnail integration — selectively copies archived thumbnail
# ABOUTME: images into the output and records their paths on posts (Feature 7 Phase 4).
"""Voat thumbnail enrichment.

The searchvoat.co archive ships 14GB of post thumbnails as UUID-named files in
a fan-out directory tree (``thumbnails/{XX}/{YY}/{uuid}.{ext}`` where XX/YY are
the UUID's first four hex chars). Voat submissions carry the UUID filename in
their ``thumbnail`` column (nested in the stored row at
``json_data->'json_data'->>'thumbnail'``).

Selective copy (the spec's recommended strategy): only thumbnails for posts
actually archived in this database are copied, into
``{output}/assets/thumbnails/{XX}/{YY}/{uuid}.{ext}``. Each post that got a
file gains a top-level ``thumbnail_local`` key in ``json_data`` with the
output-root-relative path, which post cards render conditionally.
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Any

from utils.console_output import print_info, print_success, print_warning

# UUID-with-extension filenames only — the thumbnail value is used to build
# filesystem paths, so anything else (traversal, weirdness) is rejected.
_THUMB_RE = re.compile(r"^([0-9a-f]{2})([0-9a-f]{2})[0-9a-f-]{32,40}\.(jpg|jpeg|png|gif|webp)$", re.IGNORECASE)


def thumbnail_relpath(thumbnail: str) -> str | None:
    """Fan-out relative path for a thumbnail filename, or None if malformed.

    ``b028b7f0-....png`` -> ``b0/28/b028b7f0-....png``
    """
    if not isinstance(thumbnail, str):
        return None
    m = _THUMB_RE.match(thumbnail.strip())
    if not m:
        return None
    return f"{m.group(1).lower()}/{m.group(2).lower()}/{thumbnail.strip()}"


def enrich_thumbnails(db: Any, thumbnails_dir: str, output_dir: str) -> dict[str, int]:
    """Copy archived posts' thumbnails into the output and record their paths.

    ``thumbnails_dir`` is the extracted archive (the directory containing the
    XX/ fan-out). Idempotent: existing copies are kept, paths re-recorded.
    """
    if not os.path.isdir(thumbnails_dir):
        print_warning(f"Thumbnails directory not found: {thumbnails_dir}")
        return {"copied": 0, "missing": 0, "posts": 0}

    rows = db.get_voat_thumbnail_posts()
    if not rows:
        print_warning("No archived Voat posts with thumbnails — nothing to do")
        return {"copied": 0, "missing": 0, "posts": 0}

    print_info(f"Resolving thumbnails for {len(rows):,} post(s) from {thumbnails_dir} ...")
    dest_root = os.path.join(output_dir, "assets", "thumbnails")
    copied = 0
    missing = 0
    path_updates: dict[str, str] = {}

    for post_id, thumbnail in rows:
        rel = thumbnail_relpath(thumbnail)
        if rel is None:
            missing += 1
            continue
        src = os.path.join(thumbnails_dir, rel)
        if not os.path.isfile(src):
            missing += 1
            continue
        dest = os.path.join(dest_root, rel)
        if not os.path.isfile(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1
        path_updates[post_id] = f"assets/thumbnails/{rel}"

    updated = db.update_post_thumbnail_batch(path_updates)
    print_success(f"Thumbnails: {copied} file(s) copied, {updated} post(s) linked, {missing} without an archived image")
    return {"copied": copied, "missing": missing, "posts": updated}
