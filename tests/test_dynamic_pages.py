#!/usr/bin/env python
"""
ABOUTME: Tests for Feature 2 Phases 2+3 (dynamic serving mode)
ABOUTME: Covers content URL helpers, mode gating, page routes, and static-path redirects
"""

import importlib
from typing import ClassVar

import pytest

from html_modules.content_urls import MAX_NESTING_DEPTH, build_comment_tree, enrich_user_content

TEST_SUB = "test_dynpages"


# ---------------------------------------------------------------------------
# Unit: shared content helpers (Phase 2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildCommentTree:
    def test_reddit_prefixes_and_nesting(self):
        comments = [
            {"id": "c1", "parent_id": "t3_post1", "score": 5},
            {"id": "c2", "parent_id": "t1_c1", "score": 3},
            {"id": "c3", "parent_id": "t3_post1", "score": 9},
        ]
        roots = build_comment_tree(comments)
        assert [c["id"] for c in roots] == ["c3", "c1"]  # sorted by score desc
        assert [r["id"] for r in roots[1]["replies"]] == ["c2"]

    def test_bare_parent_ids(self):
        comments = [
            {"id": "v1", "parent_id": "", "score": 1},
            {"id": "v2", "parent_id": "v1", "score": 1},
        ]
        roots = build_comment_tree(comments)
        assert [c["id"] for c in roots] == ["v1"]
        assert roots[0]["replies"][0]["id"] == "v2"

    def test_orphaned_reply_becomes_root(self):
        roots = build_comment_tree([{"id": "c9", "parent_id": "t1_missing", "score": 0}])
        assert [c["id"] for c in roots] == ["c9"]

    @staticmethod
    def _chain(length):
        """A single reply chain c0 → c1 → ... nested one level per comment."""
        comments = [{"id": "c0", "parent_id": "t3_post1", "score": 0, "author": "u0", "body": "b", "created_utc": 1}]
        comments += [
            {"id": f"c{i}", "parent_id": f"t1_c{i - 1}", "score": 0, "author": f"u{i}", "body": "b", "created_utc": 1}
            for i in range(1, length)
        ]
        return comments

    def test_deep_chain_flattened_at_cap(self):
        roots = build_comment_tree(self._chain(300))
        assert len(roots) == 1

        seen, max_depth = [], 0
        stack = [(roots[0], 0)]
        while stack:
            comment, depth = stack.pop()
            seen.append(comment["id"])
            max_depth = max(max_depth, depth)
            stack.extend((reply, depth + 1) for reply in reversed(comment["replies"]))

        assert max_depth == MAX_NESTING_DEPTH + 1
        # All comments preserved, pre-order matches the original chain order
        assert seen == [f"c{i}" for i in range(300)]

    def test_chain_at_cap_not_flattened(self):
        roots = build_comment_tree(self._chain(MAX_NESTING_DEPTH + 1))
        depth, comment = 0, roots[0]
        while comment["replies"]:
            assert len(comment["replies"]) == 1
            comment = comment["replies"][0]
            depth += 1
        assert depth == MAX_NESTING_DEPTH

    def test_deep_chain_renders_without_recursion_error(self):
        """Regression: depth-274 threads overflowed the recursion limit in render_comment."""
        from html_modules.jinja_env import jinja_env

        roots = build_comment_tree(self._chain(600))
        template = jinja_env.from_string(
            "{% from 'macros/comment_macros.html' import render_comment %}"
            "{% for c in comments %}{{ render_comment(c, 0, 'op', '../../', score_ranges) }}{% endfor %}"
        )
        html = template.render(comments=roots, score_ranges={"very_high": 100, "high": 50, "medium": 10})
        assert html.count("data-depth=") == 600
        assert f'data-depth="{MAX_NESTING_DEPTH + 1}"' in html
        assert f'data-depth="{MAX_NESTING_DEPTH + 2}"' not in html


@pytest.mark.unit
class TestEnrichUserContent:
    POST: ClassVar[dict] = {
        "type": "post",
        "subreddit": "example",
        "permalink": "/r/example/comments/abc/slug/",
        "is_self": True,
        "url": "",
        "platform": "reddit",
    }
    COMMENT: ClassVar[dict] = {
        "type": "comment",
        "id": "ccc",
        "subreddit": "example",
        "permalink": "/r/example/comments/abc/slug/ccc/",
        "platform": "reddit",
    }

    def test_static_prefix(self):
        items = [dict(self.POST), dict(self.COMMENT)]
        enrich_user_content(items, root_prefix="../../")
        assert items[0]["url_comments"] == "../../r/example/comments/abc/slug/"
        assert items[1]["url_comments"] == "../../r/example/comments/abc/slug/#comment-ccc"
        assert items[0]["sub_url"] == "../../r/example/"

    def test_dynamic_prefix(self):
        items = [dict(self.POST), dict(self.COMMENT)]
        enrich_user_content(items, root_prefix="/")
        assert items[0]["url_comments"] == "/r/example/comments/abc/slug/"
        assert items[1]["url_comments"] == "/r/example/comments/abc/slug/#comment-ccc"
        assert items[1]["sub_url"] == "/r/example/"

    def test_voat_comment_anchor(self):
        item = {
            "type": "comment",
            "id": "voat_99",
            "subreddit": "privacy",
            "permalink": "/v/privacy/comments/123#99",
            "platform": "voat",
        }
        enrich_user_content([item], root_prefix="/")
        assert item["url_comments"] == "/v/privacy/comments/123#comment-voat_99"


# ---------------------------------------------------------------------------
# Integration: Flask routes against the test database
# ---------------------------------------------------------------------------


def _post(i, title, num_comments=0, score=10):
    return {
        "id": f"dynpages_{i}",
        "subreddit": TEST_SUB,
        "author": "dyn_author",
        "title": title,
        "selftext": "body text",
        "created_utc": 1600000000 + i,
        "score": score,
        "num_comments": num_comments,
        "url": "",
        "permalink": f"/r/{TEST_SUB}/comments/dynpages_{i}/slug/",
        "is_self": True,
        "platform": "reddit",
    }


@pytest.fixture(scope="module")
def seeded_db_module(request):
    """Module-scoped seed data for route tests (posts, comments, stats, metadata)."""
    import os

    from core.postgres_database import PostgresDatabase

    db = PostgresDatabase(os.environ["DATABASE_URL"])

    def cleanup():
        with db.pool.get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM comments WHERE LOWER(subreddit) = LOWER(%s)", (TEST_SUB,))
            cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
            cur.execute("DELETE FROM subreddit_statistics WHERE subreddit = %s", (TEST_SUB,))
            cur.execute("DELETE FROM subreddit_metadata WHERE subreddit = %s", (TEST_SUB,))
            conn.commit()

    cleanup()
    db.insert_posts_batch(
        [
            _post(1, "Dynamic alpha post", num_comments=2),
            _post(2, "Dynamic beta post"),
            # extreme score: lands on page 1 of /all/ even with other test data present
            _post(3, "Dynamic gamma post", score=999999),
        ]
    )
    db.insert_comments_batch(
        [
            {
                "id": "dyncmt_1",
                "post_id": "dynpages_1",
                "parent_id": "t3_dynpages_1",
                "subreddit": TEST_SUB,
                "author": "dyn_commenter",
                "body": "a root comment",
                "created_utc": 1600000100,
                "score": 4,
                "permalink": f"/r/{TEST_SUB}/comments/dynpages_1/slug/dyncmt_1/",
                "platform": "reddit",
            },
            {
                "id": "dyncmt_2",
                "post_id": "dynpages_1",
                "parent_id": "t1_dyncmt_1",
                "subreddit": TEST_SUB,
                "author": "dyn_replier",
                "body": "a nested reply",
                "created_utc": 1600000200,
                "score": 2,
                "permalink": f"/r/{TEST_SUB}/comments/dynpages_1/slug/dyncmt_2/",
                "platform": "reddit",
            },
        ]
    )
    stats = db.calculate_subreddit_statistics(TEST_SUB)
    db.save_subreddit_statistics(TEST_SUB, stats)
    db.create_enrichment_tables()
    db.save_subreddit_metadata(
        TEST_SUB, "reddit", {"display_name": TEST_SUB, "public_description": "A dyn test sub", "subscribers": 42}
    )
    yield db
    cleanup()
    db.cleanup()


def _load_app(monkeypatch, mode):
    monkeypatch.setenv("REDDARCHIVER_SERVE_MODE", mode)
    import search_server

    importlib.reload(search_server)
    search_server.app.config["TESTING"] = True
    return search_server.app


@pytest.fixture
def dynamic_client(monkeypatch, seeded_db_module):
    return _load_app(monkeypatch, "dynamic").test_client()


@pytest.fixture
def hybrid_client(monkeypatch, seeded_db_module):
    return _load_app(monkeypatch, "hybrid").test_client()


class TestModeGating:
    def test_hybrid_serves_search_form_at_root(self, hybrid_client):
        r = hybrid_client.get("/")
        assert r.status_code == 200
        assert b"search" in r.data.lower()

    def test_hybrid_404s_page_routes(self, hybrid_client):
        assert hybrid_client.get(f"/r/{TEST_SUB}/").status_code == 404
        assert hybrid_client.get("/user/dyn_author/").status_code == 404

    def test_health_reports_mode(self, dynamic_client):
        r = dynamic_client.get("/health")
        assert r.get_json()["serve_mode"] == "dynamic"


class TestDynamicRoutes:
    def test_dashboard(self, dynamic_client):
        r = dynamic_client.get("/")
        assert r.status_code == 200
        assert TEST_SUB.encode() in r.data

    def test_subreddit_index(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/")
        assert r.status_code == 200
        assert b"Dynamic alpha post" in r.data
        assert f'href="/r/{TEST_SUB}/comments/dynpages_1/slug/"'.encode() in r.data
        # pagination links use query patterns
        assert f"/r/{TEST_SUB}/?sort=score&amp;page=".encode() in r.data
        # about and titles nav links present
        assert f'href="/r/{TEST_SUB}/about/"'.encode() in r.data
        assert f'href="/r/{TEST_SUB}/titles/"'.encode() in r.data

    def test_subreddit_sort_param(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/?sort=date")
        assert r.status_code == 200
        # date sort: newest (beta) first
        assert r.data.index(b"Dynamic beta post") < r.data.index(b"Dynamic alpha post")

    def test_wrong_platform_prefix_404s(self, dynamic_client):
        assert dynamic_client.get(f"/v/{TEST_SUB}/").status_code == 404
        assert dynamic_client.get(f"/x/{TEST_SUB}/").status_code == 404

    def test_post_page_with_comment_tree(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/comments/dynpages_1/slug/")
        assert r.status_code == 200
        assert b"a root comment" in r.data
        assert b"a nested reply" in r.data
        assert b'id="comment-dyncmt_1"' in r.data

    def test_post_page_without_slug(self, dynamic_client):
        assert dynamic_client.get(f"/r/{TEST_SUB}/comments/dynpages_1/").status_code == 200

    def test_post_wrong_subreddit_404s(self, dynamic_client):
        assert dynamic_client.get("/r/othersub/comments/dynpages_1/slug/").status_code == 404

    def test_user_page(self, dynamic_client):
        r = dynamic_client.get("/user/dyn_author/")
        assert r.status_code == 200
        assert b"Dynamic alpha post" in r.data
        assert f'href="/r/{TEST_SUB}/comments/dynpages_1/slug/"'.encode() in r.data

    def test_user_page_missing_404s(self, dynamic_client):
        assert dynamic_client.get("/user/no_such_user_xyz/").status_code == 404

    def test_about_page(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/about/")
        assert r.status_code == 200
        assert b"A dyn test sub" in r.data


class TestDynamicFilters:
    def test_min_score_filter(self, dynamic_client):
        # both posts score=10 -> min_score=11 filters everything out
        r = dynamic_client.get(f"/r/{TEST_SUB}/?min_score=11")
        assert r.status_code == 200
        assert b"Dynamic alpha post" not in r.data
        r = dynamic_client.get(f"/r/{TEST_SUB}/?min_score=5")
        assert b"Dynamic alpha post" in r.data

    def test_date_range_filter(self, dynamic_client):
        # posts are at 2020-09-13 (1600000000+) — a 2019 window excludes them
        r = dynamic_client.get(f"/r/{TEST_SUB}/?from=2019-01-01&to=2019-12-31")
        assert b"Dynamic alpha post" not in r.data
        r = dynamic_client.get(f"/r/{TEST_SUB}/?from=2020-01-01&to=2020-12-31")
        assert b"Dynamic alpha post" in r.data

    def test_pagination_preserves_filters(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/?min_score=5&sort=date")
        assert b"min_score=5" in r.data and b"sort=date" in r.data

    def test_all_route(self, dynamic_client):
        r = dynamic_client.get("/all/")
        assert r.status_code == 200
        assert b"r/all" in r.data
        # the seeded extreme-score post outranks anything else in the test DB
        assert b"Dynamic gamma post" in r.data

    def test_all_route_404_in_hybrid(self, hybrid_client):
        assert hybrid_client.get("/all/").status_code == 404


class TestDynamicTitles:
    def test_directory(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/titles/")
        assert r.status_code == 200
        assert f'href="/r/{TEST_SUB}/titles/d/"'.encode() in r.data

    def test_letter_page(self, dynamic_client):
        # both posts start with "Dynamic" -> letter d
        r = dynamic_client.get(f"/r/{TEST_SUB}/titles/d/")
        assert r.status_code == 200
        assert b"Dynamic alpha post" in r.data and b"Dynamic beta post" in r.data
        assert f'href="/r/{TEST_SUB}/comments/dynpages_1/slug/"'.encode() in r.data

    def test_empty_letter_404s(self, dynamic_client):
        assert dynamic_client.get(f"/r/{TEST_SUB}/titles/z/").status_code == 404
        assert dynamic_client.get(f"/r/{TEST_SUB}/titles/zz/").status_code == 404

    def test_titles_nav_link_present(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/")
        assert f'href="/r/{TEST_SUB}/titles/"'.encode() in r.data

    def test_overflow_redirect(self, dynamic_client):
        r = dynamic_client.get(f"/r/{TEST_SUB}/titles/d/2/")
        assert r.status_code == 301
        assert r.headers["Location"] == f"/r/{TEST_SUB}/titles/d/?page=2"


class TestStaticPathRedirects:
    @pytest.mark.parametrize(
        ("path", "target"),
        [
            ("/index.html", "/"),
            (f"/r/{TEST_SUB}/index.html", f"/r/{TEST_SUB}/"),
            (f"/r/{TEST_SUB}/index-3.html", f"/r/{TEST_SUB}/?page=3"),
            (f"/r/{TEST_SUB}/index-comments/", f"/r/{TEST_SUB}/?sort=comments"),
            (f"/r/{TEST_SUB}/index-date/index-2.html", f"/r/{TEST_SUB}/?sort=date&page=2"),
            ("/user/dyn_author/index.html", "/user/dyn_author/"),
            ("/user/dyn_author/page-2.html", "/user/dyn_author/?page=2"),
        ],
    )
    def test_redirects(self, dynamic_client, path, target):
        r = dynamic_client.get(path)
        assert r.status_code == 301
        assert r.headers["Location"] == target
