# ABOUTME: Static discoverability pages (Feature 1): per-subreddit title index,
# ABOUTME: flair index, and the global archive map page for static-only hosting.

import math
import re
from typing import Any

from html_modules.html_url import generate_domain_display_and_hover
from html_modules.jinja_env import render_template_to_file
from html_modules.platform_utils import get_url_prefix
from utils.console_output import print_info, print_warning

TITLES_PER_PAGE = 500
FLAIR_POSTS_PER_PAGE = 100
ARCHIVE_MAP_MAX_FLAIRS = 20

LETTERS = [*"abcdefghijklmnopqrstuvwxyz", "0-9"]

# Default score ranges for badge coloring when a real sample isn't available
_DEFAULT_SCORE_RANGES = {"very_high": 100, "high": 50, "medium": 10}


def letter_bucket(title: str | None) -> str:
    """Bucket a title by its first character: 'a'..'z', or '0-9' for everything else."""
    stripped = (title or "").strip()
    if not stripped:
        return "0-9"
    # .lower() can expand one char to several (e.g. 'İ' → 'i' + combining dot),
    # and such strings compare inside 'a'..'z' lexicographically — require len 1.
    first = stripped[0].lower()
    return first if len(first) == 1 and "a" <= first <= "z" else "0-9"


def flair_slugs(flairs: list[str]) -> dict[str, str]:
    """Map each flair text to a unique, filesystem-safe slug.

    Lowercased, non-alphanumeric runs collapsed to '-', capped at 60 chars.
    Collisions get '-2', '-3', ... suffixes in input order.
    """
    slugs: dict[str, str] = {}
    used: set[str] = set()
    for flair in flairs:
        base = re.sub(r"[^a-z0-9]+", "-", flair.lower()).strip("-")[:60].rstrip("-") or "flair"
        slug = base
        n = 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        slugs[flair] = slug
    return slugs


def _post_href(permalink: str | None, root_prefix: str) -> str:
    """Relative link to a post page from a page `root_prefix` below the output root."""
    return root_prefix + str(permalink or "").strip("/") + "/"


def _detect_platform(reddit_db: Any, subreddit: str) -> str:
    try:
        sample = next(reddit_db.get_posts_paginated(subreddit, limit=1), None)
        return sample.get("platform", "reddit") if sample else "reddit"
    except Exception:
        return "reddit"


def _build_context(
    subreddit: str,
    platform: str,
    seo_config: dict[str, Any] | None,
    depth: int,
    page_url: str,
    seo_title: str,
    meta_description: str,
    keywords: str,
) -> dict[str, Any]:
    """Shared template context; `depth` is directory levels below {prefix}/{sub}/."""
    from html_modules.html_constants import sort_indexes
    from html_modules.html_seo import generate_canonical_and_og_url, generate_seo_assets

    url_prefix = get_url_prefix(platform)
    site_nav_base = "../" * (2 + depth)
    subreddit_nav_base = "../" * depth
    seo_data = seo_config.get(subreddit, {}) if seo_config else {}
    base_url = seo_data.get("base_url", seo_config.get("base_url", "") if seo_config else "")
    favicon_tags, og_image_tag = generate_seo_assets(seo_config, subreddit, site_nav_base)
    canonical_tag, og_url_tag = generate_canonical_and_og_url(base_url, page_url)
    return {
        "subreddit": subreddit,
        "platform": platform,
        "url_prefix": url_prefix,
        "include_path": site_nav_base,
        "site_nav_base": site_nav_base,
        "url_subs": site_nav_base + "index.html",
        "url_idx_score": subreddit_nav_base + "index.html",
        "url_idx_cmnt": subreddit_nav_base + "index-" + sort_indexes["num_comments"]["slug"] + "/index.html",
        "url_idx_date": subreddit_nav_base + "index-" + sort_indexes["created_utc"]["slug"] + "/index.html",
        "url_search": site_nav_base + "search",
        "url_project": (seo_config or {}).get("project_url", "https://github.com/19-84/redd-archiver"),
        "seo_title": seo_title,
        "meta_description": meta_description,
        "keywords": keywords,
        "og_title": seo_title,
        "canonical_tag": canonical_tag,
        "og_url_tag": og_url_tag,
        "site_name": seo_data.get("site_name", f"{url_prefix}/{subreddit} Archive"),
        "favicon_tags": favicon_tags,
        "og_image_tag": og_image_tag,
    }


def _letter_tabs(letter_counts: dict[str, int], up_levels: int, active: str | None = None) -> list[dict[str, Any]]:
    """Letter tab data for templates; `up_levels` is how many dirs up titles/ is."""
    prefix = "../" * up_levels
    return [
        {
            "letter": letter,
            "label": letter.upper() if letter != "0-9" else "0-9",
            "href": f"{prefix}{letter}/index.html",
            "count": letter_counts.get(letter, 0),
            "active": letter == active,
        }
        for letter in LETTERS
        if letter_counts.get(letter, 0) > 0
    ]


def write_title_index_jinja2(
    subreddit: str,
    seo_config: dict[str, Any] | None,
    reddit_db: Any,
    min_score: int = 0,
    min_comments: int = 0,
) -> int:
    """Generate the alphabetical title index for one subreddit (Feature 1, Phase 1).

    Writes ``{prefix}/{sub}/titles/index.html`` (letter directory) plus one page
    per letter at ``titles/{letter}/index.html`` with overflow pagination at
    ``titles/{letter}/{n}/index.html`` (500 titles per page). Returns the number
    of pages written; 0 when the subreddit has no posts.
    """
    platform = _detect_platform(reddit_db, subreddit)
    url_prefix = get_url_prefix(platform)

    # Pass 1: per-bucket counts so pagination totals are known before streaming
    letter_counts: dict[str, int] = dict.fromkeys(LETTERS, 0)
    total_titles = 0
    for row in reddit_db.stream_post_titles(subreddit, min_score=min_score, min_comments=min_comments):
        letter_counts[letter_bucket(row["title"])] += 1
        total_titles += 1
    if total_titles == 0:
        return 0

    def render_letter_page(letter: str, page_num: int, rows: list[dict[str, Any]]) -> None:
        total_pages = math.ceil(letter_counts[letter] / TITLES_PER_PAGE)
        depth = 2 if page_num == 1 else 3  # titles/{letter}/ vs titles/{letter}/{n}/
        root_prefix = "../" * (2 + depth)
        page_dir = f"{url_prefix}/{subreddit}/titles/{letter}/" + (f"{page_num}/" if page_num > 1 else "")
        label = letter.upper() if letter != "0-9" else "0-9"
        context = _build_context(
            subreddit,
            platform,
            seo_config,
            depth=depth,
            page_url=page_dir,
            seo_title=f"{url_prefix}/{subreddit} - Titles: {label}" + (f" (page {page_num})" if page_num > 1 else ""),
            meta_description=f"Alphabetical index of {url_prefix}/{subreddit} post titles starting with {label}",
            keywords=f"{subreddit}, titles, index, {platform}, archive",
        )
        context.update(
            {
                "letter_label": label,
                "letters": _letter_tabs(letter_counts, up_levels=depth - 1, active=letter),
                "url_titles_dir": "../" * (depth - 1) + "index.html",
                "titles": [
                    {
                        "title": r["title"] or "[untitled]",
                        "href": _post_href(r["permalink"], root_prefix),
                        "score": r["score"],
                        "num_comments": r["num_comments"],
                        "created_utc": r["created_utc"],
                    }
                    for r in rows
                ],
                "page_num": page_num,
                "total_pages": total_pages,
                # From page 1 siblings live at {n}/; from page n at ../{n}/
                "prev_href": None
                if page_num == 1
                else ("../index.html" if page_num == 2 else f"../{page_num - 1}/index.html"),
                "next_href": None
                if page_num >= total_pages
                else (f"{page_num + 1}/index.html" if page_num == 1 else f"../{page_num + 1}/index.html"),
            }
        )
        render_template_to_file("pages/title_index.html", page_dir + "index.html", **context)

    # Pass 2: stream again (alphabetical) and flush each bucket every 500 rows.
    # Buckets need not be contiguous in the stream ('0-9' collects both ends of
    # the collation order), so buffers and page counters are tracked per bucket.
    buffers: dict[str, list[dict[str, Any]]] = {letter: [] for letter in LETTERS}
    pages_done: dict[str, int] = dict.fromkeys(LETTERS, 0)
    pages_written = 0
    for row in reddit_db.stream_post_titles(subreddit, min_score=min_score, min_comments=min_comments):
        bucket = letter_bucket(row["title"])
        buffers[bucket].append(row)
        if len(buffers[bucket]) >= TITLES_PER_PAGE:
            pages_done[bucket] += 1
            render_letter_page(bucket, pages_done[bucket], buffers[bucket])
            pages_written += 1
            buffers[bucket] = []
    for letter in LETTERS:
        if buffers[letter]:
            pages_done[letter] += 1
            render_letter_page(letter, pages_done[letter], buffers[letter])
            pages_written += 1

    # Letter directory page at titles/index.html (depth 1)
    context = _build_context(
        subreddit,
        platform,
        seo_config,
        depth=1,
        page_url=f"{url_prefix}/{subreddit}/titles/",
        seo_title=f"{url_prefix}/{subreddit} - Title index",
        meta_description=f"Browse all {total_titles:,} archived post titles from {url_prefix}/{subreddit} alphabetically",
        keywords=f"{subreddit}, titles, index, {platform}, archive",
    )
    context.update(
        {
            "letters": _letter_tabs(letter_counts, up_levels=0),
            "total_titles": total_titles,
        }
    )
    render_template_to_file("pages/title_directory.html", f"{url_prefix}/{subreddit}/titles/index.html", **context)
    pages_written += 1

    print_info(f"Generated title index for {url_prefix}/{subreddit} ({pages_written} pages)")
    return pages_written


def write_flair_index_jinja2(
    subreddit: str,
    seo_config: dict[str, Any] | None,
    reddit_db: Any,
    min_score: int = 0,
    min_comments: int = 0,
) -> int:
    """Generate the flair index for one subreddit (Feature 1, Phase 2).

    Writes ``{prefix}/{sub}/flair/index.html`` (flair directory) plus paginated
    post listings at ``flair/{slug}/index.html`` and ``flair/{slug}/{n}/index.html``
    (100 posts per page). Returns the number of pages written; 0 (a no-op) when
    the subreddit has no flair data.
    """
    reddit_db.ensure_flair_index()
    flair_counts = reddit_db.get_flair_counts(subreddit, min_score=min_score, min_comments=min_comments)
    if not flair_counts:
        return 0

    platform = _detect_platform(reddit_db, subreddit)
    url_prefix = get_url_prefix(platform)
    slugs = flair_slugs([f["flair"] for f in flair_counts])
    pages_written = 0

    for entry in flair_counts:
        flair, count = entry["flair"], entry["count"]
        slug = slugs[flair]
        total_pages = math.ceil(count / FLAIR_POSTS_PER_PAGE)
        for page_num in range(1, total_pages + 1):
            posts = reddit_db.get_posts_by_flair(
                subreddit,
                flair,
                limit=FLAIR_POSTS_PER_PAGE,
                offset=(page_num - 1) * FLAIR_POSTS_PER_PAGE,
                min_score=min_score,
                min_comments=min_comments,
            )
            if not posts:
                break
            depth = 2 if page_num == 1 else 3  # flair/{slug}/ vs flair/{slug}/{n}/
            root_prefix = "../" * (2 + depth)
            for post in posts:
                post.setdefault("platform", platform)
                post["url_comments"] = _post_href(post.get("permalink"), root_prefix)
                post["domain_html"] = generate_domain_display_and_hover(
                    post.get("url", ""), post.get("is_self", False), subreddit
                )
            page_dir = f"{url_prefix}/{subreddit}/flair/{slug}/" + (f"{page_num}/" if page_num > 1 else "")
            context = _build_context(
                subreddit,
                platform,
                seo_config,
                depth=depth,
                page_url=page_dir,
                seo_title=f"{url_prefix}/{subreddit} - Flair: {flair}"
                + (f" (page {page_num})" if page_num > 1 else ""),
                meta_description=f"{count:,} archived posts tagged {flair} in {url_prefix}/{subreddit}",
                keywords=f"{subreddit}, {flair}, flair, {platform}, archive",
            )
            context.update(
                {
                    "flair": flair,
                    "flair_count": count,
                    "posts": posts,
                    "score_ranges": _DEFAULT_SCORE_RANGES,
                    "base_path": root_prefix,
                    "url_flair_dir": "../" * (depth - 1) + "index.html",
                    "page_num": page_num,
                    "total_pages": total_pages,
                    "prev_href": None
                    if page_num == 1
                    else ("../index.html" if page_num == 2 else f"../{page_num - 1}/index.html"),
                    "next_href": None
                    if page_num >= total_pages
                    else (f"{page_num + 1}/index.html" if page_num == 1 else f"../{page_num + 1}/index.html"),
                }
            )
            render_template_to_file("pages/flair_index.html", page_dir + "index.html", **context)
            pages_written += 1

    # Flair directory page at flair/index.html (depth 1)
    context = _build_context(
        subreddit,
        platform,
        seo_config,
        depth=1,
        page_url=f"{url_prefix}/{subreddit}/flair/",
        seo_title=f"{url_prefix}/{subreddit} - Browse by flair",
        meta_description=f"Browse {url_prefix}/{subreddit} posts grouped by flair ({len(flair_counts)} flairs)",
        keywords=f"{subreddit}, flair, categories, {platform}, archive",
    )
    context["flairs"] = [
        {"flair": f["flair"], "count": f["count"], "href": f"{slugs[f['flair']]}/index.html"} for f in flair_counts
    ]
    render_template_to_file("pages/flair_directory.html", f"{url_prefix}/{subreddit}/flair/index.html", **context)
    pages_written += 1

    print_info(
        f"Generated flair index for {url_prefix}/{subreddit} ({len(flair_counts)} flairs, {pages_written} pages)"
    )
    return pages_written


def write_archive_map_jinja2(postgres_db: Any, seo_config: dict[str, Any] | None = None) -> bool:
    """Generate the archive map page (Feature 1, Phase 3).

    A static navigation hub at ``archive-map/index.html``: per-subreddit browse
    links, title index letters, flair links, and basic stats. Replaces the
    server-backed search form as the discovery entry point on static-only hosts.
    """
    from html_modules.html_seo import generate_canonical_and_og_url, generate_seo_assets

    stats = postgres_db.get_all_subreddit_statistics_from_db()
    if not stats:
        print_warning("Archive map: no subreddit statistics found, skipping")
        return False

    subs = []
    for stat in sorted(stats, key=lambda s: s["subreddit"].casefold()):
        subreddit = stat["subreddit"]
        platform = stat.get("platform", "reddit")
        url_prefix = get_url_prefix(platform)
        sub_base = f"../{url_prefix}/{subreddit}/"

        letter_counts: dict[str, int] = dict.fromkeys(LETTERS, 0)
        total_titles = 0
        for row in postgres_db.stream_post_titles(subreddit):
            letter_counts[letter_bucket(row["title"])] += 1
            total_titles += 1

        flair_counts = postgres_db.get_flair_counts(subreddit)
        slugs = flair_slugs([f["flair"] for f in flair_counts])
        flairs = [
            {"flair": f["flair"], "count": f["count"], "href": f"{sub_base}flair/{slugs[f['flair']]}/index.html"}
            for f in flair_counts[:ARCHIVE_MAP_MAX_FLAIRS]
        ]

        subs.append(
            {
                "name": subreddit,
                "url_prefix": url_prefix,
                "url_score": sub_base + "index.html",
                "url_comments": sub_base + "index-comments/index.html",
                "url_date": sub_base + "index-date/index.html",
                "url_titles": sub_base + "titles/index.html",
                "url_flair": sub_base + "flair/index.html",
                "letters": [
                    {
                        "label": letter.upper() if letter != "0-9" else "0-9",
                        "href": f"{sub_base}titles/{letter}/index.html",
                    }
                    for letter in LETTERS
                    if letter_counts.get(letter, 0) > 0
                ],
                "total_titles": total_titles,
                "flairs": flairs,
                "more_flairs": max(0, len(flair_counts) - ARCHIVE_MAP_MAX_FLAIRS),
                "total_posts": stat.get("archived_posts") or stat.get("total_posts") or 0,
                "total_comments": stat.get("archived_comments") or stat.get("total_comments") or 0,
                "unique_users": stat.get("unique_users") or 0,
            }
        )

    seo_data = seo_config or {}
    base_url = seo_data.get("base_url", "")
    favicon_tags, og_image_tag = generate_seo_assets(seo_config, subs[0]["name"] if subs else "", "../")
    canonical_tag, og_url_tag = generate_canonical_and_og_url(base_url, "archive-map/")
    context = {
        "subs": subs,
        "total_subreddits": len(subs),
        "include_path": "../",
        "url_subs": "../index.html",
        "url_search": "../search",
        "url_project": seo_data.get("project_url", "https://github.com/19-84/redd-archiver"),
        "seo_title": "Archive map - Browse everything",
        "meta_description": f"Structured overview of all {len(subs)} archived communities: "
        "browse by score, date, title, or flair without search",
        "keywords": "archive, map, index, browse",
        "og_title": "Archive map",
        "canonical_tag": canonical_tag,
        "og_url_tag": og_url_tag,
        "site_name": seo_data.get("site_name", "Redd Archive"),
        "favicon_tags": favicon_tags,
        "og_image_tag": og_image_tag,
    }
    render_template_to_file("pages/archive_map.html", "archive-map/index.html", **context)
    print_info(f"Generated archive map ({len(subs)} subreddits)")
    return True
