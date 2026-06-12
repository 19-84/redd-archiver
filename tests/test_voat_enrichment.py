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
    import_badges,
    import_flair,
    import_moderators,
    import_subscribers,
    import_subverses,
    import_users,
    map_subverse,
    map_user,
    parse_moderators,
)
from core.importers.voat_sql_parser import VoatSQLParser
from html_modules.html_charts import subscriber_sparkline

TEST_SUB = "test_voatenrich"
TEST_USER = "test_voat_user"


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
        assert counts["subverses"] == 1

    def test_enrich_voat_no_tracked(self, voat_db, tmp_path):
        assert enrich_voat(voat_db, str(tmp_path), {})["subverses"] == 0


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


_USER_SQL_TEMPLATE = """-- Adminer 4.8.1 MySQL dump
SET NAMES utf8mb4;
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
  `id` int(11) NOT NULL AUTO_INCREMENT
);
INSERT INTO `user` (`id`, `userName`, `bio`, `commentPointsSum`, `registrationDate`, `profilePicture`, `submissionPointsSum`, `isBot`, `isDeleted`, `svpassword`) VALUES
__ROWS__;
"""


def _user_row(name=TEST_USER, bio="hello voat", is_bot=0):
    return f"(5,'{name}','{bio}',321,'2014-06-01 10:00:00','',789,{is_bot},0,'')"


@pytest.fixture
def user_file(tmp_path):
    def make(rows):
        path = tmp_path / "user.sql.gz"
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(_USER_SQL_TEMPLATE.replace("__ROWS__", rows))
        return str(path)

    return make


@pytest.mark.unit
class TestMapUser:
    ROW = {
        "id": 5,
        "userName": TEST_USER,
        "bio": "hello voat",
        "commentPointsSum": 321,
        "registrationDate": "2014-06-01 10:00:00",
        "profilePicture": "",
        "submissionPointsSum": 789,
        "isBot": 1,
        "isDeleted": 0,
        "svpassword": "must-never-persist",
    }

    def test_field_mapping(self):
        m = map_user(self.ROW)
        assert m["bio"] == "hello voat"
        assert m["comment_karma"] == 321
        assert m["submission_karma"] == 789
        assert m["registration_date"] == _to_unix("2014-06-01 10:00:00")
        assert m["is_bot"] is True
        assert m["is_deleted"] is False
        assert m["profile_picture"] is None

    def test_svpassword_stripped(self):
        m = map_user(self.ROW)
        assert "svpassword" not in m["raw_json"]
        assert "must-never-persist" not in str(m)


class TestImportUsers:
    @pytest.fixture
    def user_db(self, voat_db):
        voat_db.create_user_metadata_table()

        def cleanup():
            with voat_db.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM user_metadata WHERE LOWER(username) = LOWER(%s)", (TEST_USER,))
                    conn.commit()

        cleanup()
        yield voat_db
        cleanup()

    def test_adminer_format_parsed_and_filtered(self, user_db, user_file):
        path = user_file(_user_row() + ",\n" + _user_row(name="untracked_voat_user"))
        count = import_users(user_db, path, {TEST_USER.lower(): TEST_USER})
        assert count == 1
        row = user_db.get_user_metadata(TEST_USER)
        assert row is not None
        assert row["bio"] == "hello voat"
        assert row["comment_karma"] == 321
        assert "svpassword" not in row["raw_json"]
        assert user_db.get_user_metadata("untracked_voat_user") is None

    def test_case_insensitive_lookup(self, user_db, user_file):
        import_users(user_db, user_file(_user_row()), {TEST_USER.lower(): TEST_USER})
        assert user_db.get_user_metadata(TEST_USER.upper()) is not None

    def test_enrich_voat_detects_user_file(self, user_db, user_file, subverse_file, tmp_path, monkeypatch):
        subverse_file(_row())
        user_file(_user_row())
        # the tracked author must exist as an archived voat author
        user_db.insert_posts_batch(
            [
                {
                    "id": "voatenrich_u1",
                    "subreddit": TEST_SUB,
                    "author": TEST_USER,
                    "title": "by tracked user",
                    "selftext": "",
                    "created_utc": 1500000000,
                    "score": 1,
                    "num_comments": 0,
                    "url": "",
                    "permalink": f"/v/{TEST_SUB}/comments/voatenrich_u1/",
                    "is_self": True,
                    "platform": "voat",
                }
            ]
        )
        counts = enrich_voat(user_db, str(tmp_path), {TEST_SUB: TEST_SUB})
        assert counts["subverses"] == 1
        assert counts["users"] == 1


def _table_sql(table: str, rows: str) -> str:
    return f"DROP TABLE IF EXISTS `{table}`;\nINSERT INTO `{table}` VALUES {rows};\n"


@pytest.fixture
def voat_table_file(tmp_path):
    def make(filename, table, rows):
        path = tmp_path / filename
        with gzip.open(path, "wt", encoding="utf-8") as f:
            f.write(_table_sql(table, rows))
        return str(path)

    return make


class TestImportModerators:
    def test_structured_moderators_replace_names(self, voat_db, voat_table_file):
        voat_db.save_subreddit_metadata(TEST_SUB, "voat", map_subverse(TestMapSubverse.ROW))
        path = voat_table_file(
            "subverseModerator.sql.gz",
            "subverseModerator",
            f"(1,'modbob','{TEST_SUB}','Moderator','2016-01-01 00:00:00','2020-12-01 00:00:00'),"
            f"(2,'owneralice','{TEST_SUB}','Owner',NULL,NULL),"
            f"(3,'other','unrelated_sub','Owner',NULL,NULL)",
        )
        updated = import_moderators(voat_db, path, {TEST_SUB: TEST_SUB})
        assert updated == 1
        row = voat_db.get_subreddit_metadata(TEST_SUB, "voat")
        mods = row["moderators_json"]
        # Owner sorts first; levels and dates preserved
        assert mods[0] == {"username": "owneralice", "level": "Owner", "first_date": None, "last_date": None}
        assert mods[1]["username"] == "modbob"
        assert mods[1]["first_date"] == "2016-01-01 00:00:00"

    def test_no_metadata_row_means_no_update(self, voat_db, voat_table_file):
        path = voat_table_file(
            "subverseModerator.sql.gz",
            "subverseModerator",
            f"(1,'modbob','{TEST_SUB}','Owner',NULL,NULL)",
        )
        assert import_moderators(voat_db, path, {TEST_SUB: TEST_SUB}) == 0


class TestImportFlair:
    @pytest.fixture
    def flair_db(self, voat_db):
        voat_db.insert_posts_batch(
            [
                {
                    "id": "voat_777001",
                    "subreddit": TEST_SUB,
                    "author": "someone",
                    "title": "flaired post",
                    "selftext": "",
                    "created_utc": 1500000000,
                    "score": 1,
                    "num_comments": 0,
                    "url": "",
                    "permalink": f"/v/{TEST_SUB}/comments/voat_777001/",
                    "is_self": True,
                    "platform": "voat",
                }
            ]
        )
        return voat_db

    def test_flair_rows_applied_data_rows_skipped(self, flair_db, voat_table_file):
        path = voat_table_file(
            "submissionAttribute.sql.gz",
            "submissionAttribute",
            "(1,777001,-1,'linkflairlabel','Data','NSFW','Not Safe For Work'),"
            "(2,777001,-1,'ORANGE','Flair','Article/News','Article/News'),"
            "(3,999999,-1,'news','Flair','news','news')",  # not archived
        )
        assert import_flair(flair_db, path) == 1
        with flair_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT json_data->>'link_flair_text' AS flair FROM posts WHERE id='voat_777001'")
                assert cur.fetchone()["flair"] == "Article/News"

    def test_first_flair_wins(self, flair_db, voat_table_file):
        path = voat_table_file(
            "submissionAttribute.sql.gz",
            "submissionAttribute",
            "(1,777001,-1,'a','Flair','First','d'),(2,777001,-1,'b','Flair','Second','d')",
        )
        assert import_flair(flair_db, path) == 1
        with flair_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT json_data->>'link_flair_text' AS flair FROM posts WHERE id='voat_777001'")
                assert cur.fetchone()["flair"] == "First"


@pytest.mark.unit
class TestSubscriberSparkline:
    def test_renders_svg(self):
        series = [{"date": f"2018-01-{d:02d}", "count": d * 10} for d in range(1, 11)]
        svg = subscriber_sparkline(series)
        assert svg.startswith("<svg")
        assert "polyline" in svg and "polygon" in svg
        assert "low 10" in svg and "high 100" in svg

    def test_too_short_series(self):
        assert subscriber_sparkline([]) == ""
        assert subscriber_sparkline([{"date": "2018-01-01", "count": 5}]) == ""

    def test_long_series_downsampled(self):
        series = [{"date": f"d{i}", "count": i} for i in range(2000)]
        svg = subscriber_sparkline(series)
        assert svg.count(",") < 600  # ~121 points x 2 coords, not 2000


class TestImportSubscribers:
    def test_points_imported_for_tracked(self, voat_db, voat_table_file):
        voat_db.create_subscriber_history_table()
        path = voat_table_file(
            "subverseSubscribers.sql.gz",
            "subverseSubscribers",
            f"(1,'{TEST_SUB}','2018-01-01',100),(2,'{TEST_SUB}','2018-01-02',110),(3,'other_sub','2018-01-01',5)",
        )
        try:
            assert import_subscribers(voat_db, path, {TEST_SUB: TEST_SUB}) == 2
            series = voat_db.get_subscriber_history(TEST_SUB)
            assert [int(r["count"]) for r in series] == [100, 110]
            # idempotent upsert
            assert import_subscribers(voat_db, path, {TEST_SUB: TEST_SUB}) == 2
            assert len(voat_db.get_subscriber_history(TEST_SUB)) == 2
        finally:
            with voat_db.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM subscriber_history WHERE subreddit = %s", (TEST_SUB,))
                    conn.commit()


class TestImportBadges:
    def test_badges_attached_to_enriched_users(self, voat_db, voat_table_file):
        voat_db.create_user_metadata_table()
        voat_db.create_subscriber_history_table()  # adds badges_json
        voat_db.save_user_metadata(TEST_USER, "voat", map_user(TestMapUser.ROW))
        try:
            path = voat_table_file(
                "userBadge.sql.gz",
                "userBadge",
                f"(1,'{TEST_USER}',1,'Badge','2015-07-05 12:56:53','x.png','Alpha tester','Joined during alpha'),"
                f"(2,'someone_else',2,'Badge','2016-01-01 00:00:00','y.png','Beta','desc')",
            )
            assert import_badges(voat_db, path, {TEST_USER.lower(): TEST_USER}) == 1
            row = voat_db.get_user_metadata(TEST_USER)
            assert row["badges_json"] == [
                {"name": "Alpha tester", "description": "Joined during alpha", "awarded": "2015-07-05 12:56:53"}
            ]
        finally:
            with voat_db.pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM user_metadata WHERE LOWER(username) = LOWER(%s)", (TEST_USER,))
                    conn.commit()


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
