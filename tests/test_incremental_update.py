#!/usr/bin/env python
"""
ABOUTME: Tests for Feature 3 Phases 1+2 (incremental Arctic Shift updates)
ABOUTME: Covers filename parsing, mandatory filtering, upsert merging, dedup, and history tracking
"""

import json

import pytest
import zstandard

from core.importers.arctic_shift_importer import ArcticShiftImporter, parse_dump_filename
from core.incremental_update import discover_dump_pairs, run_update, sha256_file
from core.selective_export import _delete_subreddit_listings, _delete_user_pages

TEST_SUB = "test_incrupd"
OTHER_SUB = "test_incrupd_untracked"


def _write_zst(path, objs):
    cctx = zstandard.ZstdCompressor()
    with open(path, "wb") as f:
        f.write(cctx.compress(("\n".join(json.dumps(o) for o in objs) + "\n").encode()))
    return str(path)


def _submission(i, subreddit=TEST_SUB, score=10, author="upd_author"):
    return {
        "id": f"incrupd{i}",
        "subreddit": subreddit,
        "author": author,
        "title": f"Update post {i}",
        "selftext": "original body",
        "created_utc": 1700000000 + i,
        "score": score,
        "num_comments": 0,
        "url": "",
        "permalink": f"/r/{subreddit}/comments/incrupd{i}/slug/",
        "is_self": True,
    }


def _comment(i, post_i, subreddit=TEST_SUB, score=3, author="upd_commenter"):
    return {
        "id": f"incrcmt{i}",
        "link_id": f"t3_incrupd{post_i}",
        "parent_id": f"t3_incrupd{post_i}",
        "subreddit": subreddit,
        "author": author,
        "body": f"update comment {i}",
        "created_utc": 1700000100 + i,
        "score": score,
        "permalink": f"/r/{subreddit}/comments/incrupd{post_i}/slug/incrcmt{i}/",
    }


@pytest.mark.unit
class TestDumpFilenames:
    def test_valid(self):
        assert parse_dump_filename("/data/RS_2026-01.zst") == ("RS", "2026-01")
        assert parse_dump_filename("RC_2025-12.zst") == ("RC", "2025-12")
        assert parse_dump_filename("rs_2026-01.zst") == ("RS", "2026-01")

    def test_invalid(self):
        assert parse_dump_filename("degoogle_submissions.zst") is None
        assert parse_dump_filename("RS_2026.zst") is None
        assert parse_dump_filename("RS_2026-01.txt") is None


@pytest.mark.unit
class TestImporter:
    def test_prefix_id_is_raw(self):
        assert ArcticShiftImporter().prefix_id("abc123") == "abc123"

    def test_filter_is_mandatory(self, tmp_path):
        imp = ArcticShiftImporter()
        path = _write_zst(tmp_path / "RS_2026-01.zst", [_submission(1)])
        with pytest.raises(ValueError, match="filter_communities"):
            next(imp.stream_posts(path))
        with pytest.raises(ValueError, match="filter_communities"):
            next(imp.stream_comments(path, filter_communities=set()))

    def test_streams_raw_objects_filtered(self, tmp_path):
        imp = ArcticShiftImporter()
        path = _write_zst(
            tmp_path / "RS_2026-01.zst",
            [_submission(1), _submission(2, subreddit=OTHER_SUB), _submission(3)],
        )
        rows = list(imp.stream_posts(path, filter_communities={TEST_SUB}))
        assert [r["id"] for r in rows] == ["incrupd1", "incrupd3"]
        # raw passthrough: no platform field injected, json identical to source
        assert "platform" not in rows[0]

    def test_comment_parent_ids_stay_raw(self, tmp_path):
        imp = ArcticShiftImporter()
        path = _write_zst(tmp_path / "RC_2026-01.zst", [_comment(1, 1)])
        row = next(imp.stream_comments(path, filter_communities={TEST_SUB}))
        assert row["parent_id"] == "t3_incrupd1"
        assert row["link_id"] == "t3_incrupd1"

    def test_detect_files(self, tmp_path):
        _write_zst(tmp_path / "RS_2026-01.zst", [_submission(1)])
        _write_zst(tmp_path / "RC_2026-01.zst", [_comment(1, 1)])
        _write_zst(tmp_path / "unrelated_submissions.zst", [_submission(2)])
        files = ArcticShiftImporter().detect_files(str(tmp_path))
        assert [f.endswith("RS_2026-01.zst") for f in files["posts"]] == [True]
        assert [f.endswith("RC_2026-01.zst") for f in files["comments"]] == [True]


@pytest.mark.unit
class TestDiscoverDumpPairs:
    def test_pairs_chronological(self, tmp_path):
        for name in ["RC_2026-02.zst", "RS_2026-01.zst", "RC_2026-01.zst", "RS_2026-02.zst", "other.zst"]:
            _write_zst(tmp_path / name, [_submission(1)])
        pairs = discover_dump_pairs(str(tmp_path))
        assert len(pairs) == 2
        assert pairs[0][0].endswith("RS_2026-01.zst") and pairs[0][1].endswith("RC_2026-01.zst")
        assert pairs[1][0].endswith("RS_2026-02.zst")

    def test_unpaired_month_still_processed(self, tmp_path):
        _write_zst(tmp_path / "RS_2026-03.zst", [_submission(1)])
        pairs = discover_dump_pairs(str(tmp_path))
        assert pairs == [(str(tmp_path / "RS_2026-03.zst"), None)]

    def test_empty_dir(self, tmp_path):
        assert discover_dump_pairs(str(tmp_path)) == []


@pytest.mark.unit
class TestSelectiveDeletion:
    def test_listing_artifacts_deleted_post_pages_kept(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sub = tmp_path / "r" / TEST_SUB
        for f in ["index.html", "index-2.html"]:
            (sub / "comments" / "abc").mkdir(parents=True, exist_ok=True)
            sub.joinpath(f).write_text("stale")
        for d in ["index-comments", "titles", "about"]:
            (sub / d).mkdir(parents=True, exist_ok=True)
            (sub / d / "index.html").write_text("stale")
        (sub / "comments" / "abc" / "index.html").write_text("post page")

        _delete_subreddit_listings("r", TEST_SUB)

        assert not (sub / "index.html").exists()
        assert not (sub / "index-2.html").exists()
        assert not (sub / "index-comments").exists()
        assert not (sub / "titles").exists()
        # post pages and about pages survive
        assert (sub / "comments" / "abc" / "index.html").exists()
        assert (sub / "about" / "index.html").exists()

    def test_user_pages_deleted(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "user" / "alice").mkdir(parents=True)
        (tmp_path / "user" / "alice" / "index.html").write_text("x")
        (tmp_path / "user" / "bob").mkdir(parents=True)
        assert _delete_user_pages(["alice", "missing"]) == 1
        assert not (tmp_path / "user" / "alice").exists()
        assert (tmp_path / "user" / "bob").exists()


@pytest.fixture
def update_db(postgres_db):
    """DB seeded with one existing post in the tracked subreddit, cleaned around each test."""

    def cleanup():
        with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM comments WHERE LOWER(subreddit) IN (LOWER(%s), LOWER(%s))", (TEST_SUB, OTHER_SUB))
            cur.execute("DELETE FROM posts WHERE subreddit IN (%s, %s)", (TEST_SUB, OTHER_SUB))
            cur.execute("DELETE FROM subreddit_statistics WHERE subreddit IN (%s, %s)", (TEST_SUB, OTHER_SUB))
            cur.execute("DROP TABLE IF EXISTS update_history")
            conn.commit()

    cleanup()
    existing = {**_submission(1, score=5), "platform": "reddit"}
    postgres_db.insert_posts_batch([existing])
    yield postgres_db
    cleanup()


def _post_row(db, post_id):
    with db.pool.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, title, score, selftext FROM posts WHERE id = %s", (post_id,))
        row = cur.fetchone()
        return dict(row) if row else None


class TestRunUpdate:
    def test_filtered_import_and_merge(self, update_db, tmp_path):
        rs = _write_zst(
            tmp_path / "RS_2026-01.zst",
            [
                {**_submission(1, score=99), "title": "EDITED TITLE SHOULD NOT WIN"},  # existing -> score refresh
                _submission(2),  # new tracked post
                _submission(3, subreddit=OTHER_SUB),  # untracked -> filtered
            ],
        )
        rc = _write_zst(tmp_path / "RC_2026-01.zst", [_comment(1, 1), _comment(2, 1, subreddit=OTHER_SUB)])

        summary = run_update(update_db, submissions_file=rs, comments_file=rc)
        assert summary["posts"] == 2
        assert summary["comments"] == 1
        assert summary["affected_subreddits"] == [TEST_SUB]
        assert "upd_author" in summary["affected_users"] and "upd_commenter" in summary["affected_users"]

        # upsert semantics: score refreshed, original title preserved
        row = _post_row(update_db, "incrupd1")
        assert row["score"] == 99
        assert row["title"] == "Update post 1"
        # new post inserted; untracked subreddit absent
        assert _post_row(update_db, "incrupd2") is not None
        assert _post_row(update_db, "incrupd3") is None

    def test_rerun_skipped_by_hash(self, update_db, tmp_path):
        rs = _write_zst(tmp_path / "RS_2026-01.zst", [_submission(2)])
        first = run_update(update_db, submissions_file=rs)
        assert first["posts"] == 1 and first["skipped_files"] == 0

        second = run_update(update_db, submissions_file=rs)
        assert second["posts"] == 0
        assert second["skipped_files"] == 1

    def test_history_recorded(self, update_db, tmp_path):
        rs = _write_zst(tmp_path / "RS_2026-01.zst", [_submission(2)])
        run_update(update_db, submissions_file=rs)
        rows = update_db.get_update_history()
        assert len(rows) == 1
        assert rows[0]["source_file"] == "RS_2026-01.zst"
        assert rows[0]["month_period"] == "2026-01"
        assert rows[0]["status"] == "completed"
        assert rows[0]["posts_matched"] == 1
        assert rows[0]["affected_subreddits"] == [TEST_SUB]
        assert rows[0]["file_hash"] == sha256_file(rs)

    def test_statistics_refreshed(self, update_db, tmp_path):
        rs = _write_zst(tmp_path / "RS_2026-01.zst", [_submission(2), _submission(3)])
        run_update(update_db, submissions_file=rs)
        stats = update_db.get_subreddit_statistics_from_db(TEST_SUB)
        assert stats and stats["total_posts"] == 3  # 1 existing + 2 new

    def test_no_tracked_subreddits_is_noop(self, postgres_db, tmp_path):
        with postgres_db.pool.get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM posts WHERE subreddit IN (%s, %s)", (TEST_SUB, OTHER_SUB))
            conn.commit()
        rs = _write_zst(tmp_path / "RS_2026-01.zst", [_submission(9, subreddit="never_archived_xyz")])
        # tracked set is whatever reddit subs exist; the dump's sub is untracked either way
        run_update(postgres_db, submissions_file=rs)
        assert _post_row(postgres_db, "incrupd9") is None
