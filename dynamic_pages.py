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
from typing import Any

from flask import Blueprint, abort, redirect, render_template, request

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


def _check_platform(prefix: str, subreddit: str) -> str:
    """404 unless `prefix` exists and matches the archived posts' platform."""
    platform = _PREFIX_PLATFORMS.get(prefix)
    if platform is None:
        abort(404)
    sample = next(get_db().get_posts_paginated(subreddit, limit=1), None)
    if sample is None or sample.get("platform", "reddit") != platform:
        abort(404)
    return platform


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
                "url_idx_titles": None,  # dynamic title browsing arrives with F2 Phase 4
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


@pages.route("/<prefix>/<subreddit>/")
def subreddit_index(prefix: str, subreddit: str):
    platform = _check_platform(prefix, subreddit)
    db = get_db()
    sort = _sort_arg()
    page_num = _page_arg()
    sort_key, order_by = _SORTS[sort]

    stats = db.get_subreddit_statistics_from_db(subreddit) or {}
    total_posts = stats.get("total_posts") or 0
    total_pages = max(1, (total_posts + links_per_page - 1) // links_per_page)

    posts = list(
        db.get_posts_paginated(
            subreddit, limit=links_per_page, offset=(page_num - 1) * links_per_page, order_by=order_by
        )
    )
    if not posts and page_num > 1:
        abort(404)

    try:
        sample = list(db.get_posts_paginated(subreddit, limit=100, order_by="score DESC"))
        score_ranges = calculate_subreddit_score_ranges(sample)
    except Exception:
        score_ranges = {"very_high": 100, "high": 50, "medium": 10}

    url_prefix = get_url_prefix(platform)
    has_about = db.get_subreddit_metadata(subreddit, platform) is not None

    context = {
        **_nav_context(subreddit, prefix),
        "subreddit": subreddit,
        "platform": platform,
        "url_prefix": url_prefix,
        "posts": _prepare_posts(posts, platform),
        "page_num": page_num,
        "total_pages": total_pages,
        "score_ranges": score_ranges,
        "base_path": "/",
        "has_about": has_about,
        "url_idx_score_css": "active" if sort == "score" else "",
        "url_idx_cmnt_css": "active" if sort == "comments" else "",
        "url_idx_date_css": "active" if sort == "date" else "",
        "arch_num_posts": total_posts,
        "arch_num_comments": stats.get("total_comments") or 0,
        "pagination_url_pattern": f"/{prefix}/{subreddit}/?sort={sort}&page=__PAGE__",
        "seo_title": f"{url_prefix}/{subreddit} - sorted by {sort_indexes[sort_key]['slug']} - page {page_num}",
        "meta_description": f"Archived posts from {url_prefix}/{subreddit}",
        "keywords": f"{subreddit}, {platform}, archive, posts",
        "og_title": f"{url_prefix}/{subreddit} archive",
    }
    return render_template("pages/subreddit.html", **context)


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
    platform = _check_platform(prefix, subreddit)
    db = get_db()
    metadata = db.get_subreddit_metadata(subreddit, platform)
    if not metadata:
        abort(404)
    rules = db.get_subreddit_rules(subreddit, platform)
    wiki_count = len(db.get_wiki_pages(subreddit, platform))

    public_desc = (metadata.get("public_description") or "").strip()
    context = {
        **_nav_context(subreddit, prefix),
        "subreddit": subreddit,
        "platform": platform,
        "url_prefix": get_url_prefix(platform),
        "metadata": metadata,
        "rules": rules,
        "wiki_count": wiki_count,
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
# 301 redirects from static-style file paths
# ---------------------------------------------------------------------------


@pages.route("/index.html")
def redirect_root_index():
    return redirect("/", code=301)


@pages.route("/<prefix>/<subreddit>/index.html")
def redirect_sub_index(prefix: str, subreddit: str):
    return redirect(f"/{prefix}/{subreddit}/", code=301)


@pages.route("/<prefix>/<subreddit>/index-<int:n>.html")
def redirect_sub_page(prefix: str, subreddit: str, n: int):
    return redirect(f"/{prefix}/{subreddit}/?page={n}", code=301)


@pages.route("/<prefix>/<subreddit>/index-<slug>/index.html")
@pages.route("/<prefix>/<subreddit>/index-<slug>/")
def redirect_sub_sorted(prefix: str, subreddit: str, slug: str):
    sort = slug if slug in _SORTS else "score"
    return redirect(f"/{prefix}/{subreddit}/?sort={sort}", code=301)


@pages.route("/<prefix>/<subreddit>/index-<slug>/index-<int:n>.html")
def redirect_sub_sorted_page(prefix: str, subreddit: str, slug: str, n: int):
    sort = slug if slug in _SORTS else "score"
    return redirect(f"/{prefix}/{subreddit}/?sort={sort}&page={n}", code=301)


@pages.route("/user/<username>/index.html")
def redirect_user_index(username: str):
    return redirect(f"/user/{username}/", code=301)


@pages.route("/user/<username>/page-<int:n>.html")
def redirect_user_page(username: str, n: int):
    return redirect(f"/user/{username}/?page={n}", code=301)


@pages.route("/<path:subpath>/index.html")
def redirect_any_index(subpath: str):
    """Catch-all: any remaining {dir}/index.html maps to its directory URL."""
    return redirect(f"/{subpath}/", code=301)
