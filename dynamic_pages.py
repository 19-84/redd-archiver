#!/usr/bin/env python
# ABOUTME: Flask blueprint serving archive pages directly from PostgreSQL
# ABOUTME: (Feature 2 Phases 2+3 — dynamic serving mode, REDDARCHIVER_SERVE_MODE=dynamic)
"""Dynamic serving mode page routes.

Renders the same Jinja2 templates the static exporter uses, but on-the-fly
from PostgreSQL with URL-path navigation instead of relative file links.
Registered by search_server.py only when ``REDDARCHIVER_SERVE_MODE=dynamic``.

Routes call the database query layer directly (never the REST API over HTTP).
Static-style file paths (``/r/x/index-2.html``) are 301-redirected to their
dynamic equivalents (``/r/x/?page=2``) so links inside previously exported
archives and the shared templates keep working.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from flask import Blueprint, abort, redirect, render_template, request, send_from_directory

from core.postgres_database import PostgresDatabase
from html_modules.content_urls import build_comment_tree, enrich_user_content
from html_modules.html_constants import links_per_page, sort_indexes, url_project
from html_modules.html_field_generation import generate_post_display_fields
from html_modules.html_scoring import calculate_score_ranges, calculate_subreddit_score_ranges
from html_modules.html_url import generate_domain_display_and_hover
from html_modules.platform_utils import get_url_prefix

pages = Blueprint("pages", __name__)

SITE_NAME = os.environ.get("REDDARCHIVER_SITE_NAME", "Redd Archive")
PROJECT_URL = os.environ.get("REDDARCHIVER_PROJECT_URL", url_project)

# URL prefix -> platform; only these prefixes are routed
_PREFIX_PLATFORMS = {"r": "reddit", "v": "voat", "g": "ruqqus"}

# ?sort= value -> (sort_indexes key, ORDER BY clause)
_SORTS = {
    "score": ("score", "score DESC, created_utc DESC"),
    "comments": ("num_comments", "num_comments DESC, score DESC"),
    "date": ("created_utc", "created_utc DESC, score DESC"),
}

_db: PostgresDatabase | None = None


def get_db() -> PostgresDatabase:
    """Get or create the page-serving PostgresDatabase instance."""
    global _db
    if _db is None:
        connection_string = os.environ.get("DATABASE_URL")
        if not connection_string:
            raise ValueError("DATABASE_URL environment variable not set")
        _db = PostgresDatabase(connection_string=connection_string, workload_type="api")
    return _db


def serve_mode() -> str:
    """The configured serving mode: 'hybrid' (default) or 'dynamic'."""
    return os.environ.get("REDDARCHIVER_SERVE_MODE", "hybrid").strip().lower()


def _page_arg() -> int:
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    return max(1, min(page, 100_000))


def _sort_arg() -> str:
    sort = request.args.get("sort", "score").strip().lower()
    return sort if sort in _SORTS else "score"


def _date_arg(name: str) -> int | None:
    """Parse a ?from=/&to= date (YYYY-MM-DD) to a UTC Unix timestamp, or None."""
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    from datetime import datetime, timezone

    try:
        return int(datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def _filter_args() -> dict[str, Any]:
    """Dynamic-only filters from query params (F2 Phase 4)."""
    try:
        min_score = max(0, int(request.args.get("min_score", "0")))
    except ValueError:
        min_score = 0
    date_to = _date_arg("to")
    if date_to is not None:
        date_to += 86399  # inclusive end of day
    return {
        "flair": request.args.get("flair", "").strip() or None,
        "domain": request.args.get("domain", "").strip() or None,
        "date_from": _date_arg("from"),
        "date_to": date_to,
        "min_score": min_score,
    }


def _filter_query_suffix(filters: dict[str, Any], sort: str) -> str:
    """Reconstruct the current sort+filter query string with a __PAGE__ slot."""
    from urllib.parse import urlencode

    params: dict[str, str] = {"sort": sort}
    if filters["flair"]:
        params["flair"] = filters["flair"]
    if filters["domain"]:
        params["domain"] = filters["domain"]
    if filters["min_score"]:
        params["min_score"] = str(filters["min_score"])
    if request.args.get("from"):
        params["from"] = request.args["from"]
    if request.args.get("to"):
        params["to"] = request.args["to"]
    return "?" + urlencode(params) + "&page=__PAGE__"


# Per-request work that only changes on import: community platforms (immutable)
# and listing counts/score ranges (TTL-cached, REDDARCHIVER_LISTING_CACHE_TTL).
_platform_cache: dict[str, str] = {}
_listing_cache: dict[tuple, tuple[float, Any]] = {}
_LISTING_CACHE_TTL = float(os.environ.get("REDDARCHIVER_LISTING_CACHE_TTL", "300"))


def _cached(key: tuple, compute: Callable[[], Any]) -> Any:
    now = time.time()
    hit = _listing_cache.get(key)
    if hit is not None and now - hit[0] < _LISTING_CACHE_TTL:
        return hit[1]
    value = compute()
    if len(_listing_cache) > 4096:  # crude bound; entries are tiny
        _listing_cache.clear()
    _listing_cache[key] = (now, value)
    return value


def _resolve_community(prefix: str, subreddit: str) -> tuple[str, str]:
    """404 unless `prefix` exists and the community is archived under it.

    Returns (platform, canonical_subreddit): user-typed URL case is mapped to
    the stored form once here so downstream queries use exact index-friendly
    matches.
    """
    platform = _PREFIX_PLATFORMS.get(prefix)
    if platform is None:
        abort(404)
    canonical = get_db().resolve_subreddit_name(subreddit)
    if canonical is None:
        abort(404)
    actual = _platform_cache.get(canonical)
    if actual is None:
        sample = next(get_db().get_posts_paginated(canonical, limit=1), None)
        if sample is None:
            abort(404)
        actual = sample.get("platform", "reddit")
        _platform_cache[canonical] = actual
    if actual != platform:
        abort(404)
    return platform, canonical


def _nav_context(subreddit: str | None = None, prefix: str = "r") -> dict[str, Any]:
    """Shared URL-path navigation context (the dynamic-mode Phase 2 adapter)."""
    ctx = {
        "include_path": "/",
        "url_subs": "/",
        "url_search": "/search",
        "url_search_css": "",
        "url_project": PROJECT_URL,
        "site_name": SITE_NAME,
        "favicon_tags": "",
        "og_image_tag": "",
        "canonical_tag": "",
        "og_url_tag": "",
        "pagination_tags": "",
    }
    if subreddit:
        base = f"/{prefix}/{subreddit}/"
        ctx.update(
            {
                "url_sub": base,
                "url_idx_score": base,
                "url_idx_cmnt": base + "?sort=comments",
                "url_idx_date": base + "?sort=date",
                "url_sub_cmnt": base + "?sort=comments",
                "url_sub_date": base + "?sort=date",
                "url_idx_about": base + "about/",
                "url_idx_titles": base + "titles/",
            }
        )
    return ctx


def _prepare_posts(posts: list[dict[str, Any]], platform: str) -> list[dict[str, Any]]:
    for post in posts:
        post.setdefault("platform", platform)
        post["url_comments"] = "/" + str(post.get("permalink", "")).strip("/") + "/"
        post["domain_html"] = generate_domain_display_and_hover(
            post.get("url", ""), post.get("is_self", False), post.get("subreddit", "")
        )
    return posts


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def dashboard():
    """Dashboard view. Dispatched from search_server's `/` route in dynamic
    mode (registering a second `/` rule would shadow-race the search form)."""
    from html_modules.html_dashboard_jinja import build_index_context

    context = build_index_context(get_db(), None)
    if context is None:
        abort(404)
    # Card links are relative ("r/x/index.html"); from "/" they resolve to
    # /r/x/index.html which the redirect layer rewrites to /r/x/.
    context.update({"include_path": "/", "site_name": SITE_NAME, "title": SITE_NAME})
    return render_template("pages/index.html", **context)


# ---------------------------------------------------------------------------
# Subreddit index
# ---------------------------------------------------------------------------


def _render_listing(prefix: str, subreddit: str | None, platform: str):
    """Shared listing renderer for subreddit indexes and /all/ (F2 Phases 3+4)."""
    db = get_db()
    sort = _sort_arg()
    page_num = _page_arg()
    sort_key, order_by = _SORTS[sort]
    filters = _filter_args()

    filter_key = tuple(sorted((k, v) for k, v in filters.items() if v))

    total_posts = _cached(
        ("count", subreddit, filter_key), lambda: db.count_posts_filtered(subreddit=subreddit, **filters)
    )
    total_pages = max(1, (total_posts + links_per_page - 1) // links_per_page)

    posts = db.query_posts_filtered(
        subreddit=subreddit,
        order_by=order_by,
        limit=links_per_page,
        offset=(page_num - 1) * links_per_page,
        **filters,
    )
    if not posts and page_num > 1:
        abort(404)

    def _compute_ranges():
        try:
            sample = db.query_posts_filtered(subreddit=subreddit, limit=100, **filters)
            return calculate_subreddit_score_ranges(sample)
        except Exception:
            return {"very_high": 100, "high": 50, "medium": 10}

    score_ranges = _cached(("ranges", subreddit, filter_key), _compute_ranges)

    url_prefix = get_url_prefix(platform)
    display_name = subreddit or "all"
    base = f"/{prefix}/{subreddit}/" if subreddit else "/all/"
    has_about = bool(subreddit) and _cached(
        ("about", subreddit, platform), lambda: db.get_subreddit_metadata(subreddit, platform) is not None
    )

    stats = _cached(("stats", subreddit), lambda: db.get_subreddit_statistics_from_db(subreddit)) if subreddit else None

    context = {
        **_nav_context(subreddit, prefix),
        "subreddit": display_name,
        "platform": platform,
        "url_prefix": url_prefix,
        "posts": _prepare_posts(posts, platform),
        "page_num": page_num,
        "total_pages": total_pages,
        "score_ranges": score_ranges,
        "base_path": "/",
        "has_about": has_about,
        "url_idx_score": base,
        "url_idx_cmnt": base + "?sort=comments",
        "url_idx_date": base + "?sort=date",
        "url_idx_score_css": "active" if sort == "score" else "",
        "url_idx_cmnt_css": "active" if sort == "comments" else "",
        "url_idx_date_css": "active" if sort == "date" else "",
        "arch_num_posts": (stats or {}).get("total_posts") or total_posts,
        "arch_num_comments": (stats or {}).get("total_comments") or 0,
        "pagination_url_pattern": base + _filter_query_suffix(filters, sort),
        "seo_title": f"{url_prefix}/{display_name} - sorted by {sort_indexes[sort_key]['slug']} - page {page_num}",
        "meta_description": f"Archived posts from {url_prefix}/{display_name}",
        "keywords": f"{display_name}, {platform}, archive, posts",
        "og_title": f"{url_prefix}/{display_name} archive",
    }
    return render_template("pages/subreddit.html", **context)


@pages.route("/<prefix>/<subreddit>/")
def subreddit_index(prefix: str, subreddit: str):
    platform, subreddit = _resolve_community(prefix, subreddit)
    return _render_listing(prefix, subreddit, platform)


@pages.route("/all/")
def all_posts():
    """Cross-subreddit combined view — dynamic mode only (F2 Phase 4)."""
    return _render_listing("r", None, "reddit")


# ---------------------------------------------------------------------------
# Title browsing (dynamic equivalent of the Feature 1 static title index)
# ---------------------------------------------------------------------------

_LETTERS = [*"abcdefghijklmnopqrstuvwxyz", "0-9"]
TITLES_PER_PAGE = 500


def _letter_tabs(prefix: str, subreddit: str, counts: dict[str, int], active: str | None = None):
    return [
        {
            "letter": letter,
            "label": letter.upper() if letter != "0-9" else "0-9",
            "href": f"/{prefix}/{subreddit}/titles/{letter}/",
            "count": counts.get(letter, 0),
            "active": letter == active,
        }
        for letter in _LETTERS
        if counts.get(letter, 0)
    ]


@pages.route("/<prefix>/<subreddit>/titles/")
def title_directory(prefix: str, subreddit: str):
    platform, subreddit = _resolve_community(prefix, subreddit)
    counts = get_db().get_title_letter_counts(subreddit)
    if not counts:
        abort(404)
    context = {
        **_nav_context(subreddit, prefix),
        "subreddit": subreddit,
        "platform": platform,
        "url_prefix": get_url_prefix(platform),
        "letters": _letter_tabs(prefix, subreddit, counts),
        "total_titles": sum(counts.values()),
        "seo_title": f"{get_url_prefix(platform)}/{subreddit} - Title index",
        "meta_description": f"Alphabetical title index for {subreddit}",
        "keywords": f"{subreddit}, titles, index, archive",
        "og_title": f"{get_url_prefix(platform)}/{subreddit} - Title index",
    }
    return render_template("pages/title_directory.html", **context)


@pages.route("/<prefix>/<subreddit>/titles/<letter>/")
def title_letter(prefix: str, subreddit: str, letter: str):
    if letter not in _LETTERS:
        abort(404)
    platform, subreddit = _resolve_community(prefix, subreddit)
    db = get_db()
    counts = db.get_title_letter_counts(subreddit)
    total = counts.get(letter, 0)
    if not total:
        abort(404)

    page_num = _page_arg()
    total_pages = max(1, (total + TITLES_PER_PAGE - 1) // TITLES_PER_PAGE)
    if page_num > total_pages:
        abort(404)
    rows = db.get_titles_by_letter(subreddit, letter, limit=TITLES_PER_PAGE, offset=(page_num - 1) * TITLES_PER_PAGE)

    base = f"/{prefix}/{subreddit}/titles/{letter}/"
    titles = [{**row, "href": "/" + str(row.get("permalink", "")).strip("/") + "/"} for row in rows]
    context = {
        **_nav_context(subreddit, prefix),
        "subreddit": subreddit,
        "platform": platform,
        "url_prefix": get_url_prefix(platform),
        "letters": _letter_tabs(prefix, subreddit, counts, active=letter),
        "letter_label": letter.upper() if letter != "0-9" else "0-9",
        "titles": titles,
        "page_num": page_num,
        "total_pages": total_pages,
        "prev_href": f"{base}?page={page_num - 1}" if page_num > 1 else None,
        "next_href": f"{base}?page={page_num + 1}" if page_num < total_pages else None,
        "url_titles_dir": f"/{prefix}/{subreddit}/titles/",
        "seo_title": f"{get_url_prefix(platform)}/{subreddit} - Titles: {letter.upper()}",
        "meta_description": f"Post titles starting with {letter} in {subreddit}",
        "keywords": f"{subreddit}, titles, {letter}, archive",
        "og_title": f"{get_url_prefix(platform)}/{subreddit} - Titles: {letter.upper()}",
    }
    return render_template("pages/title_index.html", **context)


@pages.route("/<prefix>/<subreddit>/titles/<letter>/<int:n>/")
def redirect_title_overflow(prefix: str, subreddit: str, letter: str, n: int):
    """Static overflow pages (titles/a/2/) map to ?page=N."""
    return _local_redirect(f"/{prefix}/{subreddit}/titles/{letter}/?page={n}")


# ---------------------------------------------------------------------------
# Post pages (with comment tree)
# ---------------------------------------------------------------------------


def _render_post(prefix: str, subreddit: str, post_id: str):
    platform = _PREFIX_PLATFORMS.get(prefix)
    if platform is None:
        abort(404)
    db = get_db()
    post = db.get_post_by_id(post_id)
    if not post or post.get("subreddit", "").lower() != subreddit.lower():
        abort(404)
    if post.get("platform", "reddit") != platform:
        abort(404)
    subreddit = post.get("subreddit", subreddit)  # canonical case for context/queries

    comments_list = list(db.get_comments_for_post(post_id))
    root_comments = build_comment_tree(comments_list)
    post["comments"] = root_comments
    generate_post_display_fields(post, "post_page", subreddit)

    url_prefix = get_url_prefix(platform)
    comment_scores = [c["score"] for c in comments_list if c.get("score")]

    context = {
        **_nav_context(subreddit, prefix),
        "post": post,
        "subreddit": subreddit,
        "platform": platform,
        "url_prefix": url_prefix,
        "comments": root_comments,
        "num_comments": len(comments_list),
        "score_ranges": calculate_score_ranges(comment_scores),
        "archive_date": "",
        "meta_description": (post.get("title") or "")[:160],
        "keywords": f"{subreddit}, {platform}, archive, discussion",
        "canonical_url": "",
        "structured_data": "",
    }
    return render_template("pages/link.html", **context)


@pages.route("/<prefix>/<subreddit>/comments/<post_id>/")
@pages.route("/<prefix>/<subreddit>/comments/<post_id>/<slug>/")
def post_page(prefix: str, subreddit: str, post_id: str, slug: str | None = None):
    return _render_post(prefix, subreddit, post_id)


@pages.route("/g/<subreddit>/post/<post_id>/<slug>/")
def ruqqus_post_page(subreddit: str, post_id: str, slug: str):
    return _render_post("g", subreddit, post_id)


# ---------------------------------------------------------------------------
# User pages
# ---------------------------------------------------------------------------


@pages.route("/user/<username>/")
def user_page(username: str):
    db = get_db()
    username = db.resolve_username(username) or username
    user_data = db.get_user_activity(username)
    all_content = user_data.get("all_content", [])
    if not all_content:
        abort(404)

    enrich_user_content(all_content, root_prefix="/")

    page_num = _page_arg()
    total_pages = max(1, (len(all_content) + links_per_page - 1) // links_per_page)
    if page_num > total_pages:
        abort(404)
    content = all_content[(page_num - 1) * links_per_page : page_num * links_per_page]

    post_count = sum(1 for item in all_content if item["type"] == "post")
    comment_count = len(all_content) - post_count

    subreddit_counts: dict[str, int] = {}
    subreddit_prefixes: dict[str, str] = {}
    for item in all_content:
        sub = item.get("subreddit", "")
        if sub:
            subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1
            subreddit_prefixes.setdefault(sub, item.get("url_prefix", "r"))
    top_subs = sorted(subreddit_counts, key=lambda s: subreddit_counts[s], reverse=True)[:3]
    subreddit_summary = ", ".join(f"{subreddit_prefixes[s]}/{s} ({subreddit_counts[s]})" for s in top_subs)
    if len(subreddit_counts) > 3:
        subreddit_summary += f" and {len(subreddit_counts) - 3} more"

    scores = [item["score"] for item in all_content if item.get("score") is not None]

    context = {
        **_nav_context(),
        "username": username,
        "user_metadata": db.get_user_metadata(username),
        "content": content,
        "page_num": page_num,
        "total_pages": total_pages,
        "post_count": post_count,
        "comment_count": comment_count,
        "total_content": len(all_content),
        "subreddit_summary": subreddit_summary,
        "score_ranges": calculate_score_ranges(scores),
        "url_user": f"/user/{username}/",
        "arch_num_posts": post_count,
        "arch_num_comments": comment_count,
        "pagination_url_pattern": f"/user/{username}/?page=__PAGE__",
        "seo_title": f"u/{username} - archived activity",
        "meta_description": f"Archived posts and comments by u/{username}",
        "keywords": f"{username}, user, archive",
        "og_title": f"u/{username} archive",
    }
    return render_template("pages/user.html", **context)


# ---------------------------------------------------------------------------
# About pages (Feature 6/7 metadata)
# ---------------------------------------------------------------------------


@pages.route("/<prefix>/<subreddit>/about/")
def about_page(prefix: str, subreddit: str):
    platform, subreddit = _resolve_community(prefix, subreddit)
    db = get_db()
    metadata = db.get_subreddit_metadata(subreddit, platform)
    if not metadata:
        abort(404)
    rules = db.get_subreddit_rules(subreddit, platform)
    wiki_count = len(db.get_wiki_pages(subreddit, platform))
    from html_modules.html_charts import subscriber_sparkline

    history = db.get_subscriber_history(subreddit, platform)
    sparkline_svg = subscriber_sparkline(history)

    public_desc = (metadata.get("public_description") or "").strip()
    context = {
        **_nav_context(subreddit, prefix),
        "subreddit": subreddit,
        "platform": platform,
        "url_prefix": get_url_prefix(platform),
        "metadata": metadata,
        "rules": rules,
        "wiki_count": wiki_count,
        "subscriber_sparkline_svg": sparkline_svg,
        "subscriber_peak": max((row["count"] for row in history), default=0),
        "url_wiki": None,  # dynamic wiki routes arrive with F2 Phase 4
        "url_idx_score": f"/{prefix}/{subreddit}/",
        "url_idx_cmnt": f"/{prefix}/{subreddit}/?sort=comments",
        "url_idx_date": f"/{prefix}/{subreddit}/?sort=date",
        "seo_title": f"{get_url_prefix(platform)}/{subreddit} - About",
        "meta_description": public_desc[:160] if public_desc else f"About {subreddit}",
        "keywords": f"{subreddit}, about, rules, {platform}, archive",
        "og_title": f"{get_url_prefix(platform)}/{subreddit} - About",
    }
    return render_template("pages/subreddit_about.html", **context)


# ---------------------------------------------------------------------------
# Voat post thumbnails (Feature 7 Phase 4)
# ---------------------------------------------------------------------------


@pages.route("/assets/thumbnails/<path:relpath>")
def thumbnail_asset(relpath: str):
    """Serve archived Voat thumbnails from REDDARCHIVER_THUMBNAILS_DIR.

    In static/hybrid mode nginx serves the copied files; dynamic mode points
    this env var at the extracted thumbnails/ directory instead (no copy).
    """
    base = os.environ.get("REDDARCHIVER_THUMBNAILS_DIR")
    if not base or not os.path.isdir(base):
        abort(404)
    return send_from_directory(base, relpath, max_age=86400)


# ---------------------------------------------------------------------------
# 301 redirects from static-style file paths
# ---------------------------------------------------------------------------


def _local_redirect(target: str, code: int = 301):
    """301 to a same-origin, absolute-path target or 404.

    These routes interpolate URL path segments (and the <path:subpath>
    catch-all, which matches slashes) into the Location header. Guard against
    open-redirect payloads: require a single leading slash and reject anything
    that resolves off-site — `//host`, `/\\host` (browsers fold `/\\` to `//`),
    or a `scheme:`/`netloc`. A bad static-style path 404s instead of bouncing
    the visitor to an attacker-controlled host.
    """
    if not target.startswith("/"):
        abort(404)
    if target.startswith("//") or target.startswith("/\\"):
        abort(404)
    split = urlsplit(target)
    if split.scheme or split.netloc:
        abort(404)
    return redirect(target, code=code)


@pages.route("/index.html")
def redirect_root_index():
    return redirect("/", code=301)


@pages.route("/<prefix>/<subreddit>/index.html")
def redirect_sub_index(prefix: str, subreddit: str):
    return _local_redirect(f"/{prefix}/{subreddit}/")


@pages.route("/<prefix>/<subreddit>/index-<int:n>.html")
def redirect_sub_page(prefix: str, subreddit: str, n: int):
    return _local_redirect(f"/{prefix}/{subreddit}/?page={n}")


@pages.route("/<prefix>/<subreddit>/index-<slug>/index.html")
@pages.route("/<prefix>/<subreddit>/index-<slug>/")
def redirect_sub_sorted(prefix: str, subreddit: str, slug: str):
    sort = slug if slug in _SORTS else "score"
    return _local_redirect(f"/{prefix}/{subreddit}/?sort={sort}")


@pages.route("/<prefix>/<subreddit>/index-<slug>/index-<int:n>.html")
def redirect_sub_sorted_page(prefix: str, subreddit: str, slug: str, n: int):
    sort = slug if slug in _SORTS else "score"
    return _local_redirect(f"/{prefix}/{subreddit}/?sort={sort}&page={n}")


@pages.route("/user/<username>/index.html")
def redirect_user_index(username: str):
    return _local_redirect(f"/user/{username}/")


@pages.route("/user/<username>/page-<int:n>.html")
def redirect_user_page(username: str, n: int):
    return _local_redirect(f"/user/{username}/?page={n}")


@pages.route("/<path:subpath>/index.html")
def redirect_any_index(subpath: str):
    """Catch-all: any remaining {dir}/index.html maps to its directory URL."""
    return _local_redirect(f"/{subpath}/")
