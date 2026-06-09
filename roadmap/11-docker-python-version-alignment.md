# Feature 11: Align Docker Python Versions

**Status:** Planned
**Last updated:** 2026-06-09

**Goal:** Align all Dockerfiles to use the same Python version, eliminating a known version mismatch.

**Problem:** The search-server Dockerfile uses `python:3.14-alpine` while the builder Dockerfile and CI both use Python 3.12. Python 3.14 (released October 2025) is stable, but the mismatch is an inconsistency: the search-server does not require any 3.14-specific features, and running a different minor version than the builder/CI risks subtle behavior differences and complicates maintenance. Aligning on 3.12 removes the outlier.

| Component | Python Version |
|-----------|---------------|
| `Dockerfile` (builder) | 3.12-alpine |
| `docker/search-server/Dockerfile` | **3.14-alpine** (mismatch — the only outlier) |
| `docker/leaderboard/Dockerfile` | 3.12-alpine |
| `mcp_server/Dockerfile` | 3.12-slim-bookworm (Debian, intentional — not alpine) |
| CI (`test.yml`, `lint.yml`) | 3.12 |
| `pyproject.toml` requires-python | >=3.10 |

---

## Tasks

- Change `docker/search-server/Dockerfile` base image from `python:3.14-alpine` to `python:3.12-alpine`
- Verify search-server builds successfully with `docker compose build search-server`
- Verify `docker compose up -d` works end-to-end (health endpoints respond)
- Run the Docker CI workflow integration test pattern locally:
  - Start postgres + search-server
  - Verify `/health` and `/api/v1/stats` respond
- Update Deviations table in `CLAUDE.md` to reflect completion

---

## Acceptance Criteria

- All Dockerfiles target Python **3.12** (the search-server drops from 3.14 to 3.12). The base-image *flavor* need not be uniform: `mcp_server` intentionally stays on `3.12-slim-bookworm` (Debian) and is out of scope — the goal is eliminating the 3.14 version outlier, not forcing alpine everywhere.
- `docker compose up -d --build` succeeds
- Search-server health endpoint responds correctly
- CI Docker workflow passes
