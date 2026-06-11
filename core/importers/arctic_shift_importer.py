"""
ABOUTME: Importer for monthly Arctic Shift Reddit dumps (RS_/RC_YYYY-MM.zst)
ABOUTME: Streams all-of-Reddit files, keeping only tracked subreddits (Feature 3)

Arctic Shift (https://github.com/ArthurHeitmann/arctic_shift) publishes
monthly all-of-Reddit dumps: ``RS_YYYY-MM.zst`` (submissions) and
``RC_YYYY-MM.zst`` (comments), JSON Lines in the Pushshift schema.

Unlike the per-subreddit importers, ``filter_communities`` is REQUIRED here —
an unfiltered monthly dump would import all of Reddit.

Records are yielded as raw Pushshift objects (no ID prefixing, no field
renames), exactly like the legacy ``stream_to_database()`` path that imported
the existing Reddit data. This is what makes incremental upserts merge:
existing rows have raw unprefixed IDs and raw ``t1_``/``t3_`` parent IDs, and
``insert_posts_batch``/``insert_comments_batch`` (ON CONFLICT DO UPDATE)
refresh scores on those same IDs while preserving original content.
"""

import glob
import json
import logging
import os
import re
from collections.abc import Iterator
from typing import Any

from ..watchful import read_lines_zst
from .base_importer import BaseImporter

logger = logging.getLogger(__name__)

# RS_2026-01.zst / RC_2026-01.zst (case-insensitive, any directory)
_FILENAME_RE = re.compile(r"^(RS|RC)_(\d{4}-\d{2})\.zst$", re.IGNORECASE)


def parse_dump_filename(path: str) -> tuple[str, str] | None:
    """Split an Arctic Shift dump filename into (kind, month_period).

    ``RS_2026-01.zst`` -> ("RS", "2026-01"); None for anything else.
    """
    m = _FILENAME_RE.match(os.path.basename(path))
    if not m:
        return None
    return m.group(1).upper(), m.group(2)


class ArcticShiftImporter(BaseImporter):
    """Importer for monthly Arctic Shift all-of-Reddit dumps."""

    PLATFORM_ID = "reddit"

    def prefix_id(self, raw_id: Any) -> str:
        """Raw, unprefixed IDs — existing Reddit rows were imported without a
        platform prefix, and upserts must hit the same primary keys."""
        return str(raw_id)

    def detect_files(self, input_dir: str) -> dict[str, list[str]]:
        """Detect RS_/RC_YYYY-MM.zst dump files in a directory."""
        posts_files = []
        comments_files = []
        for path in sorted(glob.glob(os.path.join(input_dir, "*.zst"))):
            parsed = parse_dump_filename(path)
            if parsed is None:
                continue
            (posts_files if parsed[0] == "RS" else comments_files).append(path)
        if not posts_files and not comments_files:
            raise FileNotFoundError(f"No Arctic Shift dumps (RS_/RC_YYYY-MM.zst) found in {input_dir}")
        logger.info(f"Detected Arctic Shift dumps: {len(posts_files)} RS, {len(comments_files)} RC")
        return {"posts": posts_files, "comments": comments_files}

    @staticmethod
    def _require_filter(filter_communities: list[str] | set[str] | None) -> set[str]:
        if not filter_communities:
            raise ValueError(
                "ArcticShiftImporter requires filter_communities — a monthly dump "
                "contains all of Reddit; importing it unfiltered is never intended"
            )
        return {s.lower() for s in filter_communities}

    def _stream_filtered(self, file_path: str, tracked: set[str], kind: str) -> Iterator[dict[str, Any]]:
        line_count = 0
        matched = 0
        for line, _ in read_lines_zst(file_path):
            line_count += 1
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
            if not obj.get("id"):
                continue
            matched += 1
            yield obj
        logger.info(f"Arctic Shift {kind}: {line_count:,} lines scanned, {matched:,} matched tracked subreddits")

    def stream_posts(
        self, file_path: str, filter_communities: list[str] | set[str] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Stream submissions matching tracked subreddits, as raw Pushshift objects."""
        tracked = self._require_filter(filter_communities)
        yield from self._stream_filtered(file_path, tracked, "submissions")

    def stream_comments(
        self, file_path: str, filter_communities: list[str] | set[str] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Stream comments matching tracked subreddits, as raw Pushshift objects."""
        tracked = self._require_filter(filter_communities)
        yield from self._stream_filtered(file_path, tracked, "comments")
