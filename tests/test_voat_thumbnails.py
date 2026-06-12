#!/usr/bin/env python
"""
ABOUTME: Tests for Feature 7 Phase 4 (Voat post thumbnail integration)
ABOUTME: Covers path validation, selective copy, post linking, and idempotency
"""

import pytest

from core.enrichment.voat_thumbnails import enrich_thumbnails, thumbnail_relpath

TEST_SUB = "test_voatthumb"
# synthetic UUID — must not collide with real archive data in the shared test DB
UUID_PNG = "fee1dead-0000-4abc-8def-123456789abc.png"


@pytest.mark.unit
class TestThumbnailRelpath:
    def test_valid(self):
        assert thumbnail_relpath(UUID_PNG) == f"fe/e1/{UUID_PNG}"
        assert thumbnail_relpath("ABCDEF01-a99c-4af2-b923-13b669927ae1.JPG") is not None

    def test_rejects_unsafe_and_malformed(self):
        assert thumbnail_relpath("../../etc/passwd") is None
        assert thumbnail_relpath("nota-uuid.png") is None
        assert thumbnail_relpath("b028b7f0.exe") is None
        assert thumbnail_relpath("") is None
        assert thumbnail_relpath(None) is None
        assert thumbnail_relpath("b0/28/../escape.png") is None


def _voat_post(i, thumbnail=None):
    inner = {"submissionid": 900000 + i, "subverse": TEST_SUB}
    if thumbnail:
        inner["thumbnail"] = thumbnail
    return {
        "id": f"voat_90000{i}",
        "subreddit": TEST_SUB,
        "author": "thumb_author",
        "title": f"thumb post {i}",
        "selftext": "",
        "created_utc": 1500000000 + i,
        "score": 1,
        "num_comments": 0,
        "url": "",
        "permalink": f"/v/{TEST_SUB}/comments/voat_90000{i}/",
        "is_self": False,
        "platform": "voat",
        "json_data": inner,
    }


@pytest.fixture
def thumb_db(postgres_db, tmp_path):
    def cleanup():
        with postgres_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM posts WHERE subreddit = %s", (TEST_SUB,))
                conn.commit()

    cleanup()
    postgres_db.insert_posts_batch(
        [
            _voat_post(1, thumbnail=UUID_PNG),
            _voat_post(2, thumbnail="00000000-dead-beef-0000-000000000000.png"),  # no file
            _voat_post(3),  # no thumbnail at all
        ]
    )
    yield postgres_db
    cleanup()


class TestEnrichThumbnails:
    def _make_source(self, tmp_path):
        src_dir = tmp_path / "thumbnails"
        (src_dir / "fe" / "e1").mkdir(parents=True)
        (src_dir / "fe" / "e1" / UUID_PNG).write_bytes(b"\x89PNG fake")
        return str(src_dir)

    def test_selective_copy_and_link(self, thumb_db, tmp_path):
        out = tmp_path / "out"
        counts = enrich_thumbnails(thumb_db, self._make_source(tmp_path), str(out))
        assert counts["copied"] == 1
        assert counts["posts"] == 1
        # at least the dead-beef uuid is missing (shared test DB may add more)
        assert counts["missing"] >= 1
        assert (out / "assets" / "thumbnails" / "fe" / "e1" / UUID_PNG).is_file()

        with thumb_db.pool.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT json_data->>'thumbnail_local' AS t FROM posts WHERE id = 'voat_900001'")
                assert cur.fetchone()["t"] == f"assets/thumbnails/fe/e1/{UUID_PNG}"
                cur.execute("SELECT json_data->>'thumbnail_local' AS t FROM posts WHERE id = 'voat_900002'")
                assert cur.fetchone()["t"] is None

    def test_idempotent_rerun(self, thumb_db, tmp_path):
        out = tmp_path / "out"
        src = self._make_source(tmp_path)
        enrich_thumbnails(thumb_db, src, str(out))
        counts = enrich_thumbnails(thumb_db, src, str(out))
        assert counts["copied"] == 0  # file already present
        assert counts["posts"] == 1  # path re-recorded

    def test_missing_source_dir(self, thumb_db, tmp_path):
        counts = enrich_thumbnails(thumb_db, str(tmp_path / "nope"), str(tmp_path / "out"))
        assert counts == {"copied": 0, "missing": 0, "posts": 0}
