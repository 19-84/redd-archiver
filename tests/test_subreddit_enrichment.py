#!/usr/bin/env python
"""
ABOUTME: Integration tests for subreddit metadata enrichment (Feature 6)
ABOUTME: Covers DB methods, dump importing with filtering, and about-page render
"""

import json

import pytest
import zstandard

from core.enrichment import subreddit_metadata as em
from html_modules.html_pages_jinja import write_subreddit_about_jinja2

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

    def test_enrich_autodetect(self, enriched_db, tmp_path):
        _write_zst(str(tmp_path / "subreddits_2025-01.zst"), [{"display_name": TEST_SUB, "description": "x"}])
        _write_zst(
            str(tmp_path / "subreddit_rules_2025-01.zst"),
            [{"subreddit": TEST_SUB, "rules": [{"priority": 0, "short_name": "R"}]}],
        )
        counts = em.enrich(enriched_db, str(tmp_path), {TEST_SUB.lower()})
        assert counts == {"metadata": 1, "rules": 1}


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
