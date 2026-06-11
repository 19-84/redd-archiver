#!/usr/bin/env python
"""
ABOUTME: Tests for Feature 7 Phase 1 (Voat subverse metadata enrichment)
ABOUTME: Covers SQL parsing, normalization, sanitization, DB roundtrip, and about pages
"""

import gzip

import pytest

from core.enrichment.voat_metadata import (
    _to_unix,
    enrich_voat,
    import_subverses,
    map_subverse,
    parse_moderators,
)
from core.importers.voat_sql_parser import VoatSQLParser

TEST_SUB = "test_voatenrich"


_SQL_TEMPLATE = """-- MariaDB dump 10.19
/*!40101 SET NAMES utf8mb4 */;
DROP TABLE IF EXISTS `subverse`;
CREATE TABLE `subverse` (
  `id` int(11) NOT NULL AUTO_INCREMENT
);
INSERT INTO `subverse` VALUES __ROWS__;
"""


def _subverse_sql(rows: str) -> str:
    """Build subverse.sql.gz fixture text (dump file content, not an executed query)."""
    return _SQL_TEMPLATE.replace("__ROWS__", rows)


def _row(name=TEST_SUB, sidebar_html="<p>hello</p>", moderators="alice;bob", is_deleted=0):
    return (
        f"(7,'{name}','founder_user','2015-12-03 16:22:32','A tagline','{sidebar_html}',"
        f"0,0,0,{is_deleted},'{moderators}','raw *markdown* sidebar',1234,'/v/{name}','link',"
        f"'2021-01-01 00:00:00',5,0,'2020-12-25 10:00:00',0)"
    )


@pytest.fixture
def subverse_file(tmp_path):
    def make(rows):
        path = tmp_path / "subverse.sql.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(_subverse_sql(rows))
        return str(path)

    return make


@pytest.mark.unit
class TestParseModerators:
    def test_multiple(self):
        assert parse_moderators("DerpyPigSauce;T4C0M4ST3R") == [
            {"username": "DerpyPigSauce"},
            {"username": "T4C0M4ST3R"},
        ]

    def test_single_and_empty(self):
        assert parse_moderators("DaMan123456") == [{"username": "DaMan123456"}]
        assert parse_moderators("") == []
        assert parse_moderators(None) == []

    def test_whitespace_and_empty_segments(self):
        assert parse_moderators("alice; ;bob;") == [{"username": "alice"}, {"username": "bob"}]


@pytest.mark.unit
class TestToUnix:
    def test_valid(self):
        assert _to_unix("2015-12-03 16:22:32") == 1449159752

    def test_invalid(self):
        assert _to_unix(None) is None
        assert _to_unix("") is None
        assert _to_unix("not a date") is None
        assert _to_unix(12345) is None


@pytest.mark.unit
class TestMapSubverse:
    ROW = {
        "id": 7,
        "name": TEST_SUB,
        "createdBy": "founder_user",
        "creationDate": "2015-12-03 16:22:32",
        "description": "A tagline",
        "formattedSidebar": '<p>hi</p><script>alert("xss")</script>',
        "isAdult": 1,
        "isAnonymized": 0,
        "isDefault": 0,
        "isDeleted": 1,
        "moderators": "alice;bob",
        "sidebar": "raw *markdown* sidebar",
        "subscriberCount": 1234,
        "title": f"/v/{TEST_SUB}",
        "type": "link",
        "lastFetched": "2021-01-01 00:00:00",
        "fetchCount": 5,
        "hideTop50": 0,
        "lastPosted": "2020-12-25 10:00:00",
        "isUnauthorised": 0,
    }

    def test_field_mapping(self):
        m = map_subverse(self.ROW)
        assert m["display_name"] == TEST_SUB
        assert m["title"] == f"/v/{TEST_SUB}"
        assert m["public_description"] == "A tagline"
        assert m["description"] == "raw *markdown* sidebar"
        assert m["subscribers"] == 1234
        assert m["created_utc"] == 1449159752
        assert m["created_by"] == "founder_user"
        assert m["over_18"] is True
        assert m["is_deleted"] is True
        assert m["moderators_json"] == [{"username": "alice"}, {"username": "bob"}]

    def test_sidebar_html_sanitized(self):
        m = map_subverse(self.ROW)
        assert "<p>hi</p>" in m["description_html"]
        assert "<script>" not in m["description_html"]

    def test_voat_type_not_mapped_to_subreddit_type(self):
        m = map_subverse(self.ROW)
        assert "subreddit_type" not in m
        assert m["raw_json"]["type"] == "link"


class TestSubverseParsing:
    def test_column_map_has_20_columns(self):
        assert len(VoatSQLParser.COLUMN_MAPS["subverse"]) == 20

    def test_stream_rows(self, subverse_file):
        path = subverse_file(_row() + "," + _row(name="other_sub", moderators=""))
        rows = list(VoatSQLParser().stream_rows(path, "subverse"))
        assert len(rows) == 2
        assert rows[0]["name"] == TEST_SUB
        assert rows[0]["createdBy"] == "founder_user"
        assert rows[0]["subscriberCount"] == 1234
        assert rows[1]["moderators"] == ""


@pytest.fixture
def voat_db(postgres_db):
    """DB with enrichment tables (incl. migration 009 columns), cleaned around each test."""
    postgres_db.create_enrichment_tables()

    def cleanup():
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM subreddit_metadata WHERE LOWER(subreddit) = LOWER(%s)", (TEST_SUB,))
                cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
                conn.commit()

    cleanup()
    yield postgres_db
    cleanup()


class TestVoatMetadataRoundtrip:
    def test_save_and_get(self, voat_db):
        meta = map_subverse(TestMapSubverse.ROW)
        assert voat_db.save_subreddit_metadata(TEST_SUB, "voat", meta) is True

        row = voat_db.get_subreddit_metadata(TEST_SUB, "voat")
        assert row is not None
        assert row["created_by"] == "founder_user"
        assert row["is_deleted"] is True
        assert row["moderators_json"] == [{"username": "alice"}, {"username": "bob"}]
        assert row["subscribers"] == 1234
        assert row["raw_json"]["type"] == "link"

    def test_platform_none_finds_voat_row(self, voat_db):
        voat_db.save_subreddit_metadata(TEST_SUB, "voat", map_subverse(TestMapSubverse.ROW))
        assert voat_db.get_subreddit_metadata(TEST_SUB) is None  # default platform=reddit
        row = voat_db.get_subreddit_metadata(TEST_SUB, platform=None)
        assert row is not None
        assert row["platform"] == "voat"


class TestImportSubverses:
    def test_tracked_filter_and_early_exit(self, voat_db, subverse_file):
        path = subverse_file(_row() + "," + _row(name="untracked_sub"))
        count = import_subverses(voat_db, path, {TEST_SUB: TEST_SUB})
        assert count == 1
        assert voat_db.get_subreddit_metadata(TEST_SUB, "voat") is not None
        assert voat_db.get_subreddit_metadata("untracked_sub", "voat") is None

    def test_exact_case_match_preferred(self, voat_db, subverse_file):
        # Voat had case-distinct subverses; the archived case must win
        variant = TEST_SUB.capitalize()
        path = subverse_file(_row(name=variant, moderators="wrong_mod") + "," + _row(name=TEST_SUB))
        count = import_subverses(voat_db, path, {TEST_SUB: TEST_SUB})
        assert count == 1
        row = voat_db.get_subreddit_metadata(TEST_SUB, "voat")
        assert row["subreddit"] == TEST_SUB
        assert row["moderators_json"] == [{"username": "alice"}, {"username": "bob"}]

    def test_case_variant_fallback(self, voat_db, subverse_file):
        # Only a case-variant exists in the dump -> used as fallback
        variant = TEST_SUB.capitalize()
        path = subverse_file(_row(name=variant))
        count = import_subverses(voat_db, path, {TEST_SUB: TEST_SUB})
        assert count == 1
        assert voat_db.get_subreddit_metadata(TEST_SUB, "voat")["subreddit"] == variant

    def test_enrich_voat_directory_detection(self, voat_db, subverse_file, tmp_path):
        subverse_file(_row())
        counts = enrich_voat(voat_db, str(tmp_path), {TEST_SUB: TEST_SUB})
        assert counts == {"subverses": 1}

    def test_enrich_voat_no_tracked(self, voat_db, tmp_path):
        assert enrich_voat(voat_db, str(tmp_path), {}) == {"subverses": 0}


class TestPlatformScopedTracking:
    def test_reddit_posts_not_tracked_for_voat(self, voat_db):
        """A Reddit subreddit must not pull in a same-named Voat subverse's metadata."""
        voat_db.insert_posts_batch(
            [
                {
                    "id": "voatenrich_r1",
                    "subreddit": TEST_SUB,
                    "author": "someone",
                    "title": "Reddit post",
                    "selftext": "body",
                    "created_utc": 1500000000,
                    "score": 5,
                    "num_comments": 0,
                    "url": "",
                    "permalink": f"/r/{TEST_SUB}/comments/voatenrich_r1/slug/",
                    "is_self": True,
                    "platform": "reddit",
                }
            ]
        )
        assert TEST_SUB not in voat_db.get_archived_subreddit_names("voat")
        assert voat_db.get_archived_subreddit_names("reddit").get(TEST_SUB) == TEST_SUB


class TestVoatAboutPage:
    def test_about_page_generated(self, voat_db, tmp_path, monkeypatch):
        from html_modules.html_pages_jinja import write_subreddit_about_jinja2

        voat_db.insert_posts_batch(
            [
                {
                    "id": "voatenrich_1",
                    "subreddit": TEST_SUB,
                    "author": "someone",
                    "title": "A post",
                    "selftext": "body",
                    "created_utc": 1500000000,
                    "score": 5,
                    "num_comments": 0,
                    "url": "",
                    "permalink": f"/v/{TEST_SUB}/comments/voatenrich_1/slug/",
                    "is_self": True,
                    "platform": "voat",
                }
            ]
        )
        voat_db.save_subreddit_metadata(TEST_SUB, "voat", map_subverse(TestMapSubverse.ROW))
        monkeypatch.chdir(tmp_path)
        assert write_subreddit_about_jinja2(TEST_SUB, None, voat_db) is True

        page = (tmp_path / f"v/{TEST_SUB}/about/index.html").read_text(encoding="utf-8")
        assert f"About v/{TEST_SUB}" in page
        assert "founder_user" in page
        assert "alice, bob" in page
        assert "Deleted community" in page
        assert "<p>hi</p>" in page
        assert "<script>" not in page
