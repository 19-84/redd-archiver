#!/usr/bin/env python3
"""
ABOUTME: Split Arctic Shift subreddit metadata/rules/wiki dumps into per-subreddit
ABOUTME: files, mirroring the {Sub}_comments.zst / {Sub}_submissions.zst layout.

One-time operation: stream the monolithic dumps (22M-record metadata, rules,
wikis) once and write one small file per subreddit of interest:

    {Sub}_metadata.zst   one JSON record (subreddit metadata snapshot)
    {Sub}_rules.zst      one JSON record (full rules array)
    {Sub}_wiki.zst       one JSON record per wiki page

After splitting, `reddarc.py --enrich SPLIT_DIR` picks the per-subreddit files
for tracked subreddits directly — no monolith scan per archive run.

A subreddit filter is required (the full metadata dump covers 22M subreddits —
splitting all of them would create 22M files). Point --filter-dir at a
directory of per-subreddit data dumps (e.g. the one holding
{Sub}_submissions.zst) to split exactly the subreddits you can archive.

Usage:
    python tools/split_subreddit_dumps.py /data/subreddit-dumps/ \
        --output /data/subreddits_split/ \
        --filter-dir /data/subreddits25/

    python tools/split_subreddit_dumps.py /data/subreddit-dumps/ \
        --output /data/subreddits_split/ \
        --subreddits degoogle,PrivacyGuides
"""

import argparse
import json
import os
import sys
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.enrichment.subreddit_metadata import _detect_files, parse_wiki_path
from core.watchful import read_lines_zst
from utils.console_output import print_error, print_info, print_success, print_warning

# Flush a subreddit's buffered wiki pages once they exceed this size. Each flush
# appends a complete zstd frame; read_lines_zst reads across frames, so a file
# may hold any number of frames.
WIKI_BUFFER_FLUSH_BYTES = 4 * 1024 * 1024


def _filter_subs_from_dir(directory: str) -> set[str]:
    """Lowercased subreddit names derived from {Sub}_submissions/_comments.zst files."""
    subs: set[str] = set()
    for fname in os.listdir(directory):
        for suffix in ("_submissions.zst", "_comments.zst"):
            if fname.endswith(suffix):
                subs.add(fname[: -len(suffix)].lower())
                break
    return subs


def _write_zst(path: str, lines: list[str], append: bool = False) -> None:
    """Write JSON lines to `path` as one zstd frame, truncating or appending."""
    payload = ("".join(line + "\n" for line in lines)).encode("utf-8")
    with open(path, "ab" if append else "wb") as f:
        f.write(zstandard.ZstdCompressor().compress(payload))


def split_one_record_dump(dump_file: str, output_dir: str, subs: set[str], suffix: str, name_of: callable) -> int:
    """Split a one-record-per-subreddit dump (metadata or rules).

    `name_of` extracts the subreddit display name from a parsed record. Stops
    scanning once every filter subreddit has been written (only subreddits
    absent from the dump force a full scan).
    """
    print_info(f"Splitting {os.path.basename(dump_file)} ...")
    written = 0
    scanned = 0
    found: set[str] = set()
    for line, _ in read_lines_zst(dump_file):
        scanned += 1
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = name_of(obj) or ""
        lowered = name.lower()
        if not lowered or lowered not in subs or lowered in found:
            continue
        _write_zst(os.path.join(output_dir, f"{name}{suffix}"), [line])
        written += 1
        found.add(lowered)
        if len(found) == len(subs):
            print_info(f"All {len(subs)} filter subreddit(s) found — stopping scan early", indent=1)
            break
    print_success(f"Wrote {written} {suffix} file(s) (scanned {scanned:,} records)")
    return written


def split_wiki_dump(wikis_file: str, output_dir: str, subs: set[str]) -> int:
    """Split the wiki dump (many records per subreddit; always a full scan).

    Pages are buffered per subreddit and flushed as appended zstd frames, so no
    assumption about dump ordering is needed. The first flush per subreddit
    truncates, making re-runs idempotent.
    """
    print_info(f"Splitting {os.path.basename(wikis_file)} ...")
    buffers: dict[str, list[str]] = {}
    buffer_bytes: dict[str, int] = {}
    flushed: set[str] = set()
    names: dict[str, str] = {}  # lowercased -> display case from path
    pages = 0

    def flush(lowered: str) -> None:
        lines = buffers.pop(lowered, [])
        buffer_bytes.pop(lowered, None)
        if not lines:
            return
        path = os.path.join(output_dir, f"{names[lowered]}_wiki.zst")
        _write_zst(path, lines, append=lowered in flushed)
        flushed.add(lowered)

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
        sub, _page = parsed
        lowered = sub.lower()
        if lowered not in subs:
            continue
        names.setdefault(lowered, sub)
        buffers.setdefault(lowered, []).append(line)
        buffer_bytes[lowered] = buffer_bytes.get(lowered, 0) + len(line)
        pages += 1
        if buffer_bytes[lowered] >= WIKI_BUFFER_FLUSH_BYTES:
            flush(lowered)

    for lowered in list(buffers):
        flush(lowered)
    print_success(f"Wrote {pages} wiki page(s) across {len(flushed)} subreddit(s)")
    return pages


def split_dumps(
    output_dir: str,
    subs: set[str],
    metadata_file: str | None = None,
    rules_file: str | None = None,
    wikis_file: str | None = None,
) -> dict[str, int]:
    """Split the given dumps into per-subreddit files under `output_dir`."""
    os.makedirs(output_dir, exist_ok=True)
    counts = {"metadata": 0, "rules": 0, "wikis": 0}
    if metadata_file:
        counts["metadata"] = split_one_record_dump(
            metadata_file, output_dir, subs, "_metadata.zst", lambda obj: obj.get("display_name")
        )
    else:
        print_warning("No subreddit metadata dump found (subreddits_*.zst) — skipping")
    if rules_file:
        counts["rules"] = split_one_record_dump(
            rules_file, output_dir, subs, "_rules.zst", lambda obj: obj.get("subreddit")
        )
    else:
        print_warning("No subreddit rules dump found (subreddit_rules_*.zst) — skipping")
    if wikis_file:
        counts["wikis"] = split_wiki_dump(wikis_file, output_dir, subs)
    else:
        print_warning("No subreddit wikis dump found (subreddit_wikis_*.zst) — skipping")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Split Arctic Shift subreddit dumps into per-subreddit files")
    parser.add_argument("input_dir", help="Directory containing the monolithic dumps (auto-detected by filename)")
    parser.add_argument("--output", "-o", required=True, help="Output directory for per-subreddit files")
    parser.add_argument(
        "--filter-dir",
        help="Only split subreddits that have {Sub}_submissions.zst / {Sub}_comments.zst files in this directory",
    )
    parser.add_argument("--subreddits", help="Comma-separated subreddit names to split (adds to --filter-dir)")
    parser.add_argument("--metadata", help="Explicit path to a subreddits_*.zst dump (overrides auto-detect)")
    parser.add_argument("--rules", help="Explicit path to a subreddit_rules_*.zst dump (overrides auto-detect)")
    parser.add_argument("--wikis", help="Explicit path to a subreddit_wikis_*.zst dump (overrides auto-detect)")
    args = parser.parse_args()

    subs: set[str] = set()
    if args.filter_dir:
        if not os.path.isdir(args.filter_dir):
            print_error(f"--filter-dir is not a directory: {args.filter_dir}")
            return 1
        subs |= _filter_subs_from_dir(args.filter_dir)
    if args.subreddits:
        subs |= {s.strip().lower() for s in args.subreddits.split(",") if s.strip()}
    if not subs:
        print_error("A subreddit filter is required: --filter-dir and/or --subreddits")
        print_info("Splitting all 22M subreddits in the dump would create 22M files.", indent=1)
        return 1

    if not os.path.isdir(args.input_dir):
        print_error(f"input_dir is not a directory: {args.input_dir}")
        return 1
    detected = _detect_files(args.input_dir)
    print_info(f"Splitting dumps for {len(subs)} subreddit(s) into {args.output}")
    counts = split_dumps(
        args.output,
        subs,
        metadata_file=args.metadata or detected["metadata"],
        rules_file=args.rules or detected["rules"],
        wikis_file=args.wikis or detected["wikis"],
    )
    print_success(
        f"Split complete: {counts['metadata']} metadata, {counts['rules']} rules, {counts['wikis']} wiki page(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
