#!/usr/bin/env python
"""
ABOUTME: Tests for Feature 1 static index pages (title index, flair index, archive map)
ABOUTME: Covers letter bucketing, flair slugs, pagination, and HTML generation
"""

import pytest

from html_modules.html_static_indexes import (
    TITLES_PER_PAGE,
    flair_slugs,
    letter_bucket,
    write_archive_map_jinja2,
    write_flair_index_jinja2,
    write_title_index_jinja2,
)

TEST_SUB = "test_staticidx"


@pytest.mark.unit
class TestLetterBucket:
    def test_ascii_letters(self):
        assert letter_bucket("Apple pie") == "a"
        assert letter_bucket("zebra") == "z"
        assert letter_bucket("  Mid spaces") == "m"

    def test_numeric_and_special(self):
        assert letter_bucket("9 things") == "0-9"
        assert letter_bucket('"Quoted title"') == "0-9"
        assert letter_bucket("[deleted]") == "0-9"

    def test_empty_and_none(self):
        assert letter_bucket("") == "0-9"
        assert letter_bucket("   ") == "0-9"
        assert letter_bucket(None) == "0-9"

    def test_accented_latin_folds_to_base_letter(self):
        assert letter_bucket("Émile Zola") == "e"
        assert letter_bucket("über alles") == "u"
        assert letter_bucket("Ñandú") == "n"
        assert letter_bucket("Çava") == "c"
        assert letter_bucket("İstanbul news") == "i"  # 'İ' → 'I' + combining dot

    def test_compatibility_forms_fold(self):
        assert letter_bucket("\uff21pple fullwidth") == "a"  # FULLWIDTH LATIN CAPITAL A
        assert letter_bucket("ﬁnal ligature") == "f"

    def test_non_latin_goes_to_catchall(self):
        assert letter_bucket("日本語タイトル") == "0-9"
        assert letter_bucket("Привет мир") == "0-9"
        assert letter_bucket("مرحبا") == "0-9"

    def test_latin_letters_without_decomposition_go_to_catchall(self):
        # No NFKD decomposition to a-z: stay in the catch-all
        assert letter_bucket("ßtraße") == "0-9"
        assert letter_bucket("Æsir") == "0-9"
        assert letter_bucket("Øresund") == "0-9"


_BUCKET_PARITY_TITLES = [
    "Apple pie",
    "zebra",
    "  Mid spaces",
    "9 things",
    '"Quoted title"',
    "[deleted]",
    "",
    "Émile Zola",
    "über alles",
    "Ñandú",
    "İstanbul news",
    "\uff21pple fullwidth",  # FULLWIDTH LATIN CAPITAL A
    "ﬁnal ligature",
    "日本語タイトル",
    "Привет мир",
    "مرحبا",
    "ßtraße",
    "Æsir",
    "Øresund",
]


class TestTitleBucketSqlParity:
    """Dynamic mode buckets in SQL; static mode in Python. They must agree."""

    def test_sql_bucket_matches_letter_bucket(self, postgres_db):
        with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
            for title in _BUCKET_PARITY_TITLES:
                cur.execute(
                    # Interpolates a class constant, not input; the title is a bound parameter
                    f"SELECT {postgres_db._TITLE_BUCKET_SQL} AS bucket FROM (VALUES (%s::text)) AS t(title)",  # noqa: S608
                    (title,),
                )
                assert cur.fetchone()["bucket"] == letter_bucket(title), title


@pytest.mark.unit
class TestFlairSlugs:
    def test_basic_and_special_chars(self):
        slugs = flair_slugs(["Discussion", "News & Politics", "Q&A / Help!"])
        assert slugs["Discussion"] == "discussion"
        assert slugs["News & Politics"] == "news-politics"
        assert slugs["Q&A / Help!"] == "q-a-help"

    def test_collisions_deduped(self):
        slugs = flair_slugs(["Help!", "help", "(help)"])
        assert slugs["Help!"] == "help"
        assert slugs["help"] == "help-2"
        assert slugs["(help)"] == "help-3"

    def test_degenerate_flair(self):
        slugs = flair_slugs(["???", "!!!"])
        assert slugs["???"] == "flair"
        assert slugs["!!!"] == "flair-2"

    def test_long_flair_capped(self):
        slugs = flair_slugs(["x" * 200])
        assert len(slugs["x" * 200]) <= 60


def _post(i, title, flair=None, score=10):
    return {
        "id": f"staticidx_{i}",
        "subreddit": TEST_SUB,
        "author": "test_user",
        "title": title,
        "selftext": "body",
        "created_utc": 1640000000 + i,
        "score": score,
        "num_comments": 2,
        "url": f"https://example.com/{i}",
        "permalink": f"/r/{TEST_SUB}/comments/staticidx_{i}/slug/",
        "is_self": True,
        "link_flair_text": flair,
        "platform": "reddit",
    }


@pytest.fixture
def indexed_db(postgres_db):
    """Test DB with a known set of posts for index generation, cleaned around each test."""

    def cleanup():
        with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
            cur.execute("DELETE FROM subreddit_statistics WHERE subreddit = %s", (TEST_SUB,))
            conn.commit()

    cleanup()
    posts = [
        _post(1, "Alpha guide", flair="Discussion"),
        _post(2, "another alpha", flair="Discussion"),
        _post(3, "Beta notes", flair="News & Politics"),
        _post(4, "42 is the answer"),
        _post(5, "Zulu time"),
    ]
    postgres_db.insert_posts_batch(posts)
    yield postgres_db
    cleanup()


class TestTitleIndexGeneration:
    def test_title_pages_generated(self, indexed_db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pages = write_title_index_jinja2(TEST_SUB, None, indexed_db)
        # a, b, z, 0-9 letter pages + directory
        assert pages == 5

        directory = (tmp_path / f"r/{TEST_SUB}/titles/index.html").read_text(encoding="utf-8")
        assert '<a href="a/index.html">A</a>' in directory
        assert '<a href="0-9/index.html">0-9</a>' in directory
        # Letters without titles are not listed
        assert '"c/index.html"' not in directory

        a_page = (tmp_path / f"r/{TEST_SUB}/titles/a/index.html").read_text(encoding="utf-8")
        # Alphabetical within the letter, case-insensitive
        assert a_page.index("Alpha guide") < a_page.index("another alpha")
        # Post links resolve from titles/a/ (4 dirs below root) back up to the post page
        assert f'href="../../../../r/{TEST_SUB}/comments/staticidx_1/slug/"' in a_page
        assert "Ctrl" in a_page  # the Ctrl+F tip

        digits = (tmp_path / f"r/{TEST_SUB}/titles/0-9/index.html").read_text(encoding="utf-8")
        assert "42 is the answer" in digits

    def test_no_posts_is_noop(self, postgres_db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert write_title_index_jinja2("test_staticidx_absent", None, postgres_db) == 0
        assert not (tmp_path / "r/test_staticidx_absent").exists()

    def test_overflow_pagination(self, postgres_db, tmp_path, monkeypatch):
        with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
            conn.commit()
        bulk = [_post(1000 + i, f"big title {i:04d}") for i in range(TITLES_PER_PAGE + 10)]
        postgres_db.insert_posts_batch(bulk)
        try:
            monkeypatch.chdir(tmp_path)
            pages = write_title_index_jinja2(TEST_SUB, None, postgres_db)
            assert pages == 3  # b/, b/2/, directory

            page1 = (tmp_path / f"r/{TEST_SUB}/titles/b/index.html").read_text(encoding="utf-8")
            page2 = (tmp_path / f"r/{TEST_SUB}/titles/b/2/index.html").read_text(encoding="utf-8")
            assert "page 1 of 2" in page1
            assert '<a href="2/index.html">' in page1
            assert "page 2 of 2" in page2
            assert '<a href="../index.html">' in page2
            # Overflow page is one level deeper — post links gain one more ../
            assert f'href="../../../../../r/{TEST_SUB}/comments/' in page2
        finally:
            with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
                conn.commit()


class TestFlairIndexGeneration:
    def test_flair_pages_generated(self, indexed_db, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        pages = write_flair_index_jinja2(TEST_SUB, None, indexed_db)
        assert pages == 3  # discussion/, news-politics/, directory

        directory = (tmp_path / f"r/{TEST_SUB}/flair/index.html").read_text(encoding="utf-8")
        assert '<a href="discussion/index.html">Discussion</a>' in directory
        assert '<a href="news-politics/index.html">News &amp; Politics</a>' in directory

        discussion = (tmp_path / f"r/{TEST_SUB}/flair/discussion/index.html").read_text(encoding="utf-8")
        assert "Alpha guide" in discussion and "another alpha" in discussion
        assert "Beta notes" not in discussion
        # Post card link from flair/discussion/ back up to the post page
        assert f'href="../../../../r/{TEST_SUB}/comments/staticidx_1/slug/"' in discussion

    def test_no_flair_is_noop(self, postgres_db, tmp_path, monkeypatch):
        with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
            conn.commit()
        postgres_db.insert_posts_batch([_post(1, "No flair here")])
        try:
            monkeypatch.chdir(tmp_path)
            assert write_flair_index_jinja2(TEST_SUB, None, postgres_db) == 0
            assert not (tmp_path / f"r/{TEST_SUB}/flair").exists()
        finally:
            with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
                conn.commit()


class TestArchiveMapGeneration:
    def test_archive_map_generated(self, indexed_db, tmp_path, monkeypatch):
        stats = indexed_db.calculate_subreddit_statistics(TEST_SUB)
        indexed_db.save_subreddit_statistics(TEST_SUB, stats)
        monkeypatch.chdir(tmp_path)
        assert write_archive_map_jinja2(indexed_db) is True

        page = (tmp_path / "archive-map/index.html").read_text(encoding="utf-8")
        assert f'<a href="../r/{TEST_SUB}/index.html">' in page
        assert f'href="../r/{TEST_SUB}/titles/index.html"' in page
        assert f'href="../r/{TEST_SUB}/titles/a/index.html"' in page
        assert f'href="../r/{TEST_SUB}/flair/discussion/index.html"' in page
        assert "Discussion" in page
