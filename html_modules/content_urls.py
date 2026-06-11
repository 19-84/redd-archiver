# ABOUTME: Shared content URL enrichment and comment-tree assembly used by both
# ABOUTME: static page writers and dynamic-mode Flask routes (Feature 2 Phase 2).
"""Mode-agnostic content preparation.

Static pages live N directories below the output root and link with relative
prefixes (``../../``); dynamic mode serves the same templates from URL paths
and links from the site root (``/``). Parameterizing the root prefix lets one
implementation feed both.
"""

from __future__ import annotations

from typing import Any

from html_modules.html_url import generate_domain_display_and_hover
from html_modules.platform_utils import get_url_prefix


def build_comment_tree(comments_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assemble a flat comment list into a nested tree, returning root comments.

    Single-pass dict build + reply attachment. Mutates each comment in place,
    adding a ``replies`` list. Handles Reddit's ``t1_``/``t3_`` prefixes and
    the bare parent IDs used by Voat/Ruqqus. Root comments are sorted by score
    descending (recursive sorting happens in the render_comment macro).
    """
    comments_by_id: dict[Any, dict[str, Any]] = {}
    root_comments: list[dict[str, Any]] = []

    # First pass: build dict, initialize replies, identify root comments
    for comment in comments_list:
        comment["replies"] = []
        comments_by_id[comment["id"]] = comment

        parent_id = comment.get("parent_id", "")
        if isinstance(parent_id, str):
            if parent_id.startswith("t3_"):
                root_comments.append(comment)
            elif not parent_id.startswith("t1_"):
                root_comments.append(comment)
            # 't1_' replies are attached in the second pass
        elif not parent_id:
            root_comments.append(comment)
        else:
            root_comments.append(comment)

    # Second pass: attach replies to parents
    for comment in comments_list:
        parent_id = comment.get("parent_id", "")
        if isinstance(parent_id, str):
            if parent_id.startswith("t1_"):
                parent = comments_by_id.get(parent_id[3:])
                if parent:
                    parent["replies"].append(comment)
                elif comment not in root_comments:
                    root_comments.append(comment)
            elif parent_id in comments_by_id:
                comments_by_id[parent_id]["replies"].append(comment)
                if comment in root_comments:
                    root_comments.remove(comment)

    root_comments.sort(key=lambda c: c.get("score", 0), reverse=True)
    return root_comments


def enrich_user_content(all_content: list[dict[str, Any]], root_prefix: str = "../../") -> None:
    """Add URL/display fields to a user's mixed post+comment content, in place.

    ``root_prefix`` is the path from the rendered page to the archive root:
    ``../../`` for static user pages (at ``user/{name}/``), ``/`` for dynamic
    mode.
    """
    for item in all_content:
        subreddit = item.get("subreddit", "")

        if item["type"] == "post":
            permalink = item.get("permalink", "")
            if permalink:
                # Preserve exact case from source permalinks
                post_path = permalink.strip("/")
                item["url_comments"] = f"{root_prefix}{post_path}/"
                item["url"] = item["url_comments"]
            else:
                item["url_comments"] = ""
                item["url"] = ""

            item["domain_html"] = generate_domain_display_and_hover(
                item.get("url", ""), item.get("is_self", False), subreddit
            )

        elif item["type"] == "comment":
            permalink = item.get("permalink", "")
            if permalink:
                # Reddit: /r/example/comments/id/Post_Title_Slug/comment_id/
                # Voat:   /v/example/comments/id#comment_id (anchor already included)
                # Ruqqus: /g/example/post/id/slug/comment_id
                parts = permalink.strip("/").split("/")
                comment_id = item.get("id", "")

                if len(parts) >= 5 and parts[0] == "r" and parts[2] == "comments":
                    post_path = "/".join(parts[:5])
                    item["url_comments"] = f"{root_prefix}{post_path}/#comment-{comment_id}"
                elif len(parts) >= 4 and parts[0] == "v" and parts[2] == "comments":
                    # Voat permalinks carry a raw comment ID anchor; HTML anchors
                    # use the prefixed format (#comment-voat_NNN)
                    if "#" in permalink:
                        post_part, _raw = permalink.split("#", 1)
                        post_path = post_part.strip("/")
                        item["url_comments"] = f"{root_prefix}{post_path}#comment-{comment_id}"
                    else:
                        post_path = "/".join(parts[:4])
                        item["url_comments"] = f"{root_prefix}{post_path}#comment-{comment_id}"
                elif len(parts) >= 5 and parts[0] == "g" and parts[2] == "post":
                    # Ruqqus: comment ID is the last path segment; convert to anchor
                    post_path = "/".join(parts[:5])
                    item["url_comments"] = f"{root_prefix}{post_path}#comment-{comment_id}"
                else:
                    item["url_comments"] = ""
            else:
                item["url_comments"] = ""

            item["parent_post_title"] = item.get("link_title", "Post Title")

        # Subreddit URL and platform prefix for all items
        if subreddit:
            platform = item.get("platform", "reddit")
            prefix = get_url_prefix(platform)
            item["sub_url"] = f"{root_prefix}{prefix}/{subreddit}/"
            item["url_prefix"] = prefix
        else:
            item["sub_url"] = ""
            item["url_prefix"] = "r"
