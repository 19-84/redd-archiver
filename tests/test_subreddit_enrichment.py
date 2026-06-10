#!/usr/bin/env python
"""
ABOUTME: Integration tests for subreddit metadata enrichment (Feature 6)
ABOUTME: Covers DB methods, dump importing with filtering, and about-page render
"""

import json

import pytest
import zstandard

from core.enrichment import subreddit_metadata as em
from html_modules.html_pages_jinja import write_subreddit_about_jinja2, write_subreddit_wiki_jinja2

TEST_SUB = "test_enrich_sub"
OTHER_SUB = "test_enrich_other"


def _write_zst(path, records):
    """Write JSON-Lines records to a .zst file the importer can stream."""
    payload = "".join(json.dumps(r) + "\n" for r in records).encode("utf-8")
    with open(path, "wb") as f:
        f.write(zstandard.ZstdCompressor().compress(payload))


def _cleanup(db):
    with db.pool.get_connection() as conn:
        with conn.cursor() as cur:
            for sub in (TEST_SUB, OTHER_SUB):
                cur.execute("DELETE FROM subreddit_metadata WHERE LOWER(subreddit) = LOWER(%s)", (sub,))
                cur.execute("DELETE FROM subreddit_rules WHERE LOWER(subreddit) = LOWER(%s)", (sub,))
                cur.execute("DELETE FROM subreddit_wiki_pages WHERE LOWER(subreddit) = LOWER(%s)", (sub,))
                cur.execute("DELETE FROM posts WHERE subreddit = %s", (sub,))
            conn.commit()


@pytest.fixture
def enriched_db(postgres_db):
    """postgres_db with enrichment tables ensured and test rows cleaned."""
    postgres_db.create_enrichment_tables()
    _cleanup(postgres_db)
    yield postgres_db
    _cleanup(postgres_db)


def _track(db, sub):
    """Insert a minimal posts row so `sub` counts as tracked."""
    with db.pool.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO posts (id, subreddit, platform, author, title, permalink, created_utc, json_data) "
                "VALUES (%s, %s, 'reddit', 'test_user', 'title', '/p', %s, '{}') "
                "ON CONFLICT (id) DO NOTHING",
                (f"test_enrich_{sub}_p1", sub, 1700000000),
            )
            conn.commit()


class TestMetadataDbMethods:
    def test_metadata_upsert_roundtrip(self, enriched_db):
        ok = enriched_db.save_subreddit_metadata(
            TEST_SUB, "reddit", {"display_name": TEST_SUB, "subscribers": 42, "raw_json": {"k": "v"}}
        )
        assert ok
        got = enriched_db.get_subreddit_metadata(TEST_SUB.upper())  # case-insensitive
        assert got["subscribers"] == 42
        assert got["raw_json"] == {"k": "v"}

        # Upsert updates in place (no duplicate row)
        enriched_db.save_subreddit_metadata(TEST_SUB, "reddit", {"display_name": TEST_SUB, "subscribers": 99})
        assert enriched_db.get_subreddit_metadata(TEST_SUB)["subscribers"] == 99

    def test_rules_delete_and_replace(self, enriched_db):
        two = [
            {"priority": 0, "short_name": "A", "kind": "all"},
            {"priority": 1, "short_name": "B", "kind": "link"},
        ]
        enriched_db.save_subreddit_rules(TEST_SUB, "reddit", two)
        rules = enriched_db.get_subreddit_rules(TEST_SUB)
        assert [r["short_name"] for r in rules] == ["A", "B"]  # ordered by priority

        # Re-import with a single (reordered/removed) rule fully replaces the set
        enriched_db.save_subreddit_rules(TEST_SUB, "reddit", [{"priority": 0, "short_name": "Only", "kind": "all"}])
        rules = enriched_db.get_subreddit_rules(TEST_SUB)
        assert len(rules) == 1 and rules[0]["short_name"] == "Only"

    def test_get_tracked_subreddits(self, enriched_db):
        _track(enriched_db, TEST_SUB)
        assert TEST_SUB.lower() in enriched_db.get_tracked_subreddits()


class TestDumpImport:
    def test_import_metadata_filters_untracked(self, enriched_db, tmp_path):
        meta_file = str(tmp_path / "subreddits_test.zst")
        _write_zst(
            meta_file,
            [
                {
                    "display_name": TEST_SUB,
                    "description": "Visit r/privacy.",
                    "public_description": "tag",
                    "subscribers": 5,
                },
                {"display_name": OTHER_SUB, "description": "should be skipped"},
            ],
        )
        n = em.import_metadata(enriched_db, meta_file, {TEST_SUB.lower()})
        assert n == 1
        assert enriched_db.get_subreddit_metadata(OTHER_SUB) is None
        got = enriched_db.get_subreddit_metadata(TEST_SUB)
        assert got is not None
        # markdown rendered to HTML, r/ ref linked
        assert 'href="https://www.reddit.com/r/privacy"' in got["description_html"]

    def test_import_metadata_sanitizes_xss(self, enriched_db, tmp_path):
        meta_file = str(tmp_path / "subreddits_xss.zst")
        _write_zst(meta_file, [{"display_name": TEST_SUB, "description": "hi <script>alert(1)</script>"}])
        em.import_metadata(enriched_db, meta_file, {TEST_SUB.lower()})
        assert "<script" not in enriched_db.get_subreddit_metadata(TEST_SUB)["description_html"].lower()

    def test_import_rules(self, enriched_db, tmp_path):
        rules_file = str(tmp_path / "subreddit_rules_test.zst")
        _write_zst(
            rules_file,
            [
                {
                    "subreddit": TEST_SUB,
                    "retrieved_on": 1700000000,
                    "rules": [
                        {"priority": 0, "short_name": "Be nice", "description": "No **rudeness**", "kind": "all"},
                    ],
                },
                {"subreddit": OTHER_SUB, "rules": [{"priority": 0, "short_name": "skip"}]},
            ],
        )
        n = em.import_rules(enriched_db, rules_file, {TEST_SUB.lower()})
        assert n == 1
        rules = enriched_db.get_subreddit_rules(TEST_SUB)
        assert len(rules) == 1
        assert "<strong>rudeness</strong>" in rules[0]["description_html"]
        assert enriched_db.get_subreddit_rules(OTHER_SUB) == []

    def test_import_metadata_stops_after_all_tracked_found(self, enriched_db, tmp_path):
        # One record per subreddit in the real dump; a second record for the same
        # sub would only be reached if the scan continued past "all found".
        meta_file = str(tmp_path / "subreddits_early.zst")
        _write_zst(
            meta_file,
            [
                {"display_name": TEST_SUB, "subscribers": 1},
                {"display_name": TEST_SUB, "subscribers": 2},
            ],
        )
        em.import_metadata(enriched_db, meta_file, {TEST_SUB.lower()})
        assert enriched_db.get_subreddit_metadata(TEST_SUB)["subscribers"] == 1

    def test_import_rules_stops_after_all_tracked_found(self, enriched_db, tmp_path):
        rules_file = str(tmp_path / "subreddit_rules_early.zst")
        _write_zst(
            rules_file,
            [
                {"subreddit": TEST_SUB, "rules": [{"priority": 0, "short_name": "first"}]},
                {"subreddit": TEST_SUB, "rules": [{"priority": 0, "short_name": "second"}]},
            ],
        )
        em.import_rules(enriched_db, rules_file, {TEST_SUB.lower()})
        rules = enriched_db.get_subreddit_rules(TEST_SUB)
        assert [r["short_name"] for r in rules] == ["first"]

    def test_enrich_autodetect(self, enriched_db, tmp_path):
        _write_zst(str(tmp_path / "subreddits_2025-01.zst"), [{"display_name": TEST_SUB, "description": "x"}])
        _write_zst(
            str(tmp_path / "subreddit_rules_2025-01.zst"),
            [{"subreddit": TEST_SUB, "rules": [{"priority": 0, "short_name": "R"}]}],
        )
        _write_zst(
            str(tmp_path / "subreddit_wikis_2025-01.zst"),
            [{"path": f"/r/{TEST_SUB}/wiki/index", "content": "w", "revision_date": "2024-01-01T00:00:00+00:00"}],
        )
        counts = em.enrich(enriched_db, str(tmp_path), {TEST_SUB.lower()})
        assert counts == {"metadata": 1, "rules": 1, "wikis": 1}


class TestWikiPathParsing:
    def test_parses_simple_and_nested_paths(self):
        assert em.parse_wiki_path("/r/privacy/wiki/index") == ("privacy", "index")
        assert em.parse_wiki_path("/r/privacy/wiki/config/sidebar") == ("privacy", "config/sidebar")
        assert em.parse_wiki_path("/r/foo_bar/wiki/a-b/c_d/e") == ("foo_bar", "a-b/c_d/e")

    def test_rejects_malformed_and_unsafe_paths(self):
        assert em.parse_wiki_path(None) is None
        assert em.parse_wiki_path("index") is None
        assert em.parse_wiki_path("/r/privacy/index") is None  # no /wiki/
        assert em.parse_wiki_path("/r/privacy/wiki/") is None  # empty page
        assert em.parse_wiki_path("/r/privacy/wiki/a//b") is None  # empty segment
        assert em.parse_wiki_path("/r/privacy/wiki/../etc/passwd") is None  # traversal
        assert em.parse_wiki_path("/r/privacy/wiki/.hidden") is None  # dotfile
        assert em.parse_wiki_path("/r/privacy/wiki/a b") is None  # whitespace


class TestWikiImport:
    def test_import_wikis_filters_untracked(self, enriched_db, tmp_path):
        wikis_file = str(tmp_path / "subreddit_wikis_test.zst")
        _write_zst(
            wikis_file,
            [
                {
                    "path": f"/r/{TEST_SUB}/wiki/index",
                    "content": "See r/privacy for **more**.",
                    "revision_author": "mod",
                    "revision_date": "2024-11-17T17:45:02+00:00",
                    "retrieved_on": 1737155927,
                },
                {"path": f"/r/{OTHER_SUB}/wiki/index", "content": "skipped"},
                {"path": "not-a-wiki-path", "content": "skipped"},
            ],
        )
        n = em.import_wikis(enriched_db, wikis_file, {TEST_SUB.lower()})
        assert n == 1
        assert enriched_db.get_wiki_pages(OTHER_SUB) == []
        pages = enriched_db.get_wiki_pages(TEST_SUB)
        assert len(pages) == 1
        page = pages[0]
        assert page["path"] == "index"
        assert page["revision_author"] == "mod"
        assert page["revision_date"].year == 2024
        # markdown rendered, r/ ref linked
        assert "<strong>more</strong>" in page["content_html"]
        assert 'href="https://www.reddit.com/r/privacy"' in page["content_html"]

    def test_import_wikis_sanitizes_xss(self, enriched_db, tmp_path):
        wikis_file = str(tmp_path / "subreddit_wikis_xss.zst")
        _write_zst(wikis_file, [{"path": f"/r/{TEST_SUB}/wiki/faq", "content": "hi <script>alert(1)</script>"}])
        em.import_wikis(enriched_db, wikis_file, {TEST_SUB.lower()})
        assert "<script" not in enriched_db.get_wiki_page(TEST_SUB, "faq")["content_html"].lower()

    def test_reimport_upserts_in_place(self, enriched_db, tmp_path):
        for content in ("first", "second"):
            wikis_file = str(tmp_path / f"subreddit_wikis_{content}.zst")
            _write_zst(wikis_file, [{"path": f"/r/{TEST_SUB}/wiki/index", "content": content}])
            em.import_wikis(enriched_db, wikis_file, {TEST_SUB.lower()})
        pages = enriched_db.get_wiki_pages(TEST_SUB)
        assert len(pages) == 1
        assert pages[0]["content"] == "second"


def _load_splitter():
    """Load tools/split_subreddit_dumps.py (tools/ is not a package)."""
    import importlib.util
    from pathlib import Path

    tool_path = Path(__file__).parent.parent / "tools" / "split_subreddit_dumps.py"
    spec = importlib.util.spec_from_file_location("split_subreddit_dumps", tool_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDumpSplitter:
    def test_split_dumps_roundtrip_and_idempotent_rerun(self, tmp_path):
        from core.watchful import read_lines_zst

        splitter = _load_splitter()
        dumps = tmp_path / "dumps"
        dumps.mkdir()
        _write_zst(
            str(dumps / "subreddits_2025-01.zst"),
            [
                {"display_name": TEST_SUB, "subscribers": 7},
                {"display_name": "unwanted", "subscribers": 1},
                {"display_name": OTHER_SUB, "subscribers": 8},
            ],
        )
        _write_zst(
            str(dumps / "subreddit_rules_2025-01.zst"),
            [{"subreddit": TEST_SUB, "rules": [{"priority": 0, "short_name": "R"}]}],
        )
        # Interleaved subs exercise per-sub buffering across the stream.
        _write_zst(
            str(dumps / "subreddit_wikis_2025-01.zst"),
            [
                {"path": f"/r/{TEST_SUB}/wiki/index", "content": "one"},
                {"path": f"/r/{OTHER_SUB}/wiki/index", "content": "other"},
                {"path": f"/r/{TEST_SUB}/wiki/config/sidebar", "content": "two"},
                {"path": "/r/unwanted/wiki/index", "content": "skipped"},
            ],
        )
        out = tmp_path / "split"
        for _run in range(2):  # second run must not duplicate content
            counts = splitter.split_dumps(
                str(out),
                {TEST_SUB.lower(), OTHER_SUB.lower()},
                metadata_file=str(dumps / "subreddits_2025-01.zst"),
                rules_file=str(dumps / "subreddit_rules_2025-01.zst"),
                wikis_file=str(dumps / "subreddit_wikis_2025-01.zst"),
            )
            assert counts == {"metadata": 2, "rules": 1, "wikis": 3}

            assert not (out / "unwanted_metadata.zst").exists()
            meta_lines = [json.loads(line) for line, _ in read_lines_zst(str(out / f"{TEST_SUB}_metadata.zst"))]
            assert len(meta_lines) == 1 and meta_lines[0]["subscribers"] == 7
            wiki_lines = [json.loads(line) for line, _ in read_lines_zst(str(out / f"{TEST_SUB}_wiki.zst"))]
            assert sorted(rec["content"] for rec in wiki_lines) == ["one", "two"]

    def test_filter_subs_from_dir(self, tmp_path):
        splitter = _load_splitter()
        (tmp_path / "Degoogle_submissions.zst").touch()
        (tmp_path / "Degoogle_comments.zst").touch()
        (tmp_path / "Other_comments.zst").touch()
        (tmp_path / "unrelated.txt").touch()
        assert splitter._filter_subs_from_dir(str(tmp_path)) == {"degoogle", "other"}


class TestSplitFileEnrich:
    def test_enrich_prefers_split_files_over_monolith(self, enriched_db, tmp_path):
        # Split file and monolith disagree; split must win for tracked subs.
        _write_zst(str(tmp_path / f"{TEST_SUB}_metadata.zst"), [{"display_name": TEST_SUB, "subscribers": 1}])
        _write_zst(str(tmp_path / "subreddits_2025-01.zst"), [{"display_name": TEST_SUB, "subscribers": 2}])
        _write_zst(
            str(tmp_path / f"{TEST_SUB}_rules.zst"),
            [{"subreddit": TEST_SUB, "rules": [{"priority": 0, "short_name": "split rule"}]}],
        )
        _write_zst(str(tmp_path / f"{TEST_SUB}_wiki.zst"), [{"path": f"/r/{TEST_SUB}/wiki/index", "content": "w"}])
        # Split files for untracked subs are ignored.
        _write_zst(str(tmp_path / f"{OTHER_SUB}_metadata.zst"), [{"display_name": OTHER_SUB}])

        counts = em.enrich(enriched_db, str(tmp_path), {TEST_SUB.lower()})
        assert counts == {"metadata": 1, "rules": 1, "wikis": 1}
        assert enriched_db.get_subreddit_metadata(TEST_SUB)["subscribers"] == 1
        assert enriched_db.get_subreddit_metadata(OTHER_SUB) is None
        assert [r["short_name"] for r in enriched_db.get_subreddit_rules(TEST_SUB)] == ["split rule"]
        assert enriched_db.get_wiki_page(TEST_SUB, "index") is not None


class TestAboutPageRender:
    def test_about_page_renders(self, enriched_db, tmp_path, monkeypatch):
        enriched_db.save_subreddit_metadata(
            TEST_SUB,
            "reddit",
            {
                "display_name": TEST_SUB,
                "public_description": "A test community",
                "description_html": "<p>Welcome</p>",
                "subscribers": 1234,
                "created_utc": 1300000000,
                "over_18": True,
            },
        )
        enriched_db.save_subreddit_rules(
            TEST_SUB,
            "reddit",
            [{"priority": 0, "short_name": "Rule one", "description_html": "<p>desc</p>", "kind": "all"}],
        )
        monkeypatch.chdir(tmp_path)
        assert write_subreddit_about_jinja2(TEST_SUB, None, enriched_db) is True
        out = tmp_path / f"r/{TEST_SUB}/about/index.html"
        assert out.is_file()
        html = out.read_text(encoding="utf-8")
        assert "Welcome" in html
        assert "Rule one" in html
        assert "NSFW" in html  # over_18 badge
        assert "1,234" in html  # subscribers via format_number

    def test_about_page_noop_without_metadata(self, enriched_db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert write_subreddit_about_jinja2("test_enrich_absent", None, enriched_db) is False

    def test_about_page_links_wiki_when_present(self, enriched_db, tmp_path, monkeypatch):
        enriched_db.save_subreddit_metadata(TEST_SUB, "reddit", {"display_name": TEST_SUB})
        enriched_db.save_wiki_page(TEST_SUB, "reddit", {"path": "index", "content": "w"})
        monkeypatch.chdir(tmp_path)
        assert write_subreddit_about_jinja2(TEST_SUB, None, enriched_db) is True
        html = (tmp_path / f"r/{TEST_SUB}/about/index.html").read_text(encoding="utf-8")
        assert '<a href="../wiki/index.html">1 archived page</a>' in html


class TestWikiPageRender:
    def test_wiki_pages_render(self, enriched_db, tmp_path, monkeypatch):
        enriched_db.save_wiki_page(
            TEST_SUB,
            "reddit",
            {
                "path": "index",
                "content": "Welcome",
                "content_html": "<p>Welcome to the wiki</p>",
                "revision_author": "mod",
            },
        )
        enriched_db.save_wiki_page(
            TEST_SUB,
            "reddit",
            {"path": "config/sidebar", "content": "s", "content_html": "<p>sidebar md</p>"},
        )
        monkeypatch.chdir(tmp_path)
        assert write_subreddit_wiki_jinja2(TEST_SUB, None, enriched_db) == 2

        listing = (tmp_path / f"r/{TEST_SUB}/wiki/index.html").read_text(encoding="utf-8")
        assert '<a href="index/index.html">index</a>' in listing
        assert '<a href="config/sidebar/index.html">config/sidebar</a>' in listing

        index_page = (tmp_path / f"r/{TEST_SUB}/wiki/index/index.html").read_text(encoding="utf-8")
        assert "Welcome to the wiki" in index_page
        assert '<a href="../index.html">wiki</a>' in index_page  # breadcrumb back to listing

        nested = (tmp_path / f"r/{TEST_SUB}/wiki/config/sidebar/index.html").read_text(encoding="utf-8")
        assert "sidebar md" in nested
        # depth-aware links: nested page is two levels below the wiki dir
        assert '<a href="../../index.html">wiki</a>' in nested
        assert 'href="../../../about/index.html"' in nested

    def test_wiki_noop_without_pages(self, enriched_db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert write_subreddit_wiki_jinja2("test_enrich_absent", None, enriched_db) == 0
        assert not (tmp_path / "r/test_enrich_absent").exists()
