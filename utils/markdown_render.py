# ABOUTME: Render and sanitize Reddit-flavored markdown (subreddit sidebar
# ABOUTME: descriptions, rules, wiki content) to safe HTML for Feature 6 enrichment.
"""Reddit markdown -> sanitized HTML.

Subreddit sidebars, rule descriptions, and wiki pages are moderator-authored
Reddit markdown. Arctic Shift only provides pre-rendered HTML for a couple of
fields, so we render the rest ourselves *once at import time* and store the
result. Because the source is user-authored, every rendered fragment is
sanitized with an allowlist before storage to prevent stored XSS.

Perfect fidelity to Reddit's renderer is not the goal — readable, safe HTML is.
"""

from __future__ import annotations

import re

import bleach
import markdown as _markdown

# Reddit token references like `r/privacy`, `/r/privacy`, `u/spez`, `/u/spez`,
# `/user/spez`. Only matched at a word start (line start or after whitespace) so
# we don't rewrite paths inside URLs (e.g. ".../r/foo") or markdown link labels
# (e.g. "[r/foo]").
_SUBREDDIT_REF = re.compile(r"(?:^|(?<=\s))/?r/([A-Za-z0-9_]{2,21})\b")
_USER_REF = re.compile(r"(?:^|(?<=\s))/?u(?:ser)?/([A-Za-z0-9_-]{2,20})\b")

# Allowlist for sanitization. Intentionally excludes <script>, <style>, <iframe>,
# event-handler attributes, and anything that can execute. Links and images are
# constrained to safe protocols below.
ALLOWED_TAGS: list[str] = [
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "del",
    "sup",
    "sub",
    "blockquote",
    "ul",
    "ol",
    "li",
    "a",
    "code",
    "pre",
    "span",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "img",
]
ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
    "th": ["align"],
    "td": ["align"],
}
ALLOWED_PROTOCOLS: list[str] = ["http", "https", "mailto"]


def _link_reddit_refs(text: str) -> str:
    """Turn bare `r/x` and `u/x` references into markdown links to reddit.com."""
    text = _SUBREDDIT_REF.sub(r"[r/\1](https://www.reddit.com/r/\1)", text)
    text = _USER_REF.sub(r"[u/\1](https://www.reddit.com/user/\1)", text)
    return text


def sanitize_html(html: str | None) -> str:
    """Sanitize an HTML fragment against the allowlist.

    Use for fields the source already provides as HTML (e.g. Arctic Shift's
    ``submit_text_html`` / ``quarantine_message_html``). Returns "" for empty
    input. Safe to store and emit with Jinja's ``|safe``.
    """
    if not html or not html.strip():
        return ""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    ).strip()


def render_reddit_markdown(text: str | None) -> str:
    """Render Reddit markdown to sanitized HTML.

    Returns an empty string for empty/None input. The output is safe to store
    and emit with Jinja's ``|safe`` because it has been sanitized here.
    """
    if not text or not text.strip():
        return ""

    preprocessed = _link_reddit_refs(text)
    raw_html = _markdown.markdown(
        preprocessed,
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html",
    )
    return sanitize_html(raw_html)
