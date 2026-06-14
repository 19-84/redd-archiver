# Changelog

All notable changes to Redd-Archiver will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-06-12 — "Living Archive"

The archive is no longer a snapshot: serve it three ways, keep it current
monthly, and skin it to taste.

### Added

**Serving modes**
- **Dynamic serving mode** (`REDDARCHIVER_SERVE_MODE=dynamic`): Flask renders
  every page straight from PostgreSQL — no export step, content live the
  moment it imports. Adds listing filters (`?flair=&domain=&min_score=&from=&to=`),
  the `/all/` cross-subreddit view, on-the-fly title browsing, case-insensitive
  URLs, and 301 redirects from static-style paths.
- Static-mode navigation: per-letter **title indexes**, **flair indexes**, and
  an **archive map** page — Ctrl+F-friendly browsing with zero server.

**Incremental updates**
- `--update RS_YYYY-MM.zst --comments-file RC_YYYY-MM.zst` applies a monthly
  Arctic Shift dump to an existing archive: only tracked subreddits import,
  scores refresh, original content is never overwritten by deletions.
- `--update-all DIR` discovers and applies every unprocessed month oldest-first
  (the Academic Torrents `comments/` + `submissions/` layout is understood).
- `--update-status` audit view; SHA256 dedup via the `update_history` table
  makes every step idempotent and cron-safe. Affected subreddits re-export
  selectively in static/hybrid deployments.
- Validated end-to-end against real 2026-01/2026-02 monthly dumps (60GB pairs).
- See `docs/INCREMENTAL_UPDATES.md`.

**Themes**
- 11 palettes: `default`, `sepia`, `nord`, `solarized`, `dracula`, `gruvbox`,
  `cyberpunk`, `midnight` (true-black OLED), `old-reddit`, `phosphor`,
  `high-contrast` — via `--theme` at export or `REDDARCHIVER_THEME` in dynamic
  mode. `--accent-color` re-tints any palette; `--custom-css` appends operator
  styles. Dark/light follows the system preference with a CSS-only toggle.

**Community metadata**
- Subreddit descriptions, rules, and wiki pages imported from Arctic Shift
  metadata dumps; about pages and wiki rendering.
- Voat enrichment: subverse metadata, user profiles, moderator lists, post
  flair, subscriber history, thumbnails.

**Search & i18n**
- Full-text search rebuilt on the `simple` regconfig — non-English content
  (Cyrillic, Arabic, and other scripts) is now searchable.

**Operations**
- `--precompress` writes .gz siblings for the whole export; bundled nginx
  configs enable `gzip_static`.
- HTTP caching on the search server: `Cache-Control` + ETag/304 revalidation
  (`REDDARCHIVER_HTTP_CACHE_MAX_AGE`).
- Tuned `postgres.conf` shipped for the Docker deployment; gunicorn workers
  scale with CPUs (`GUNICORN_WORKERS` overrides).

### Performance
- Dynamic listings **2.2s → 1–23ms** (~95×): exact-match queries with
  canonical-name resolution at the boundaries, new composite/global indexes,
  and an in-process listing cache (`REDDARCHIVER_LISTING_CACHE_TTL`).
- Export thread reconstruction no longer spills hundreds of MB to disk per
  chunk (SQL sorts moved to Python; keyset index added).
- Import line parsing switched to orjson; listing queries strip `selftext`
  server-side.

### Fixed
- Deep comment threads (270+ levels) crashed page generation with
  `RecursionError`; trees now flatten past depth 50 (visually identical).
- Post-bulk-load index recreation silently failed forever (wrong
  `indexes.sql` path) — imports left databases unindexed.
- Manual light-mode toggle produced unreadable white-on-white text.
- Subreddit-filtered user-statistics refresh clobbered global user counts
  with per-community values (would have corrupted stats during incremental
  updates).
- Orphaned comments in monthly dumps (parents never archived) poisoned COPY
  batches with FK retry churn; they are now pre-filtered and reported.
- Re-exports left subreddit listing pages stale: the listing renderer skipped
  any index page already on disk, so `--export-from-database` after metadata
  enrichment never surfaced the About/wiki nav link (and post-update listings
  kept old pagination). Existing pages are now rewritten on re-export; only an
  interrupted-run resume skips them.
- Post-page `canonical`/`og:url` pointed at a flat `{permalink}.html` that does
  not exist in the directory-based layout (pages live at `{permalink}/`), so
  every post canonicalized to a 404. Canonicals now use the served directory URL.
- Heading-order accessibility failure on user pages (Lighthouse 97 → 100).
- Playwright moved from required dependencies to the optional `screenshots`
  extra (`uv sync --extra screenshots`); archive generation no longer pulls
  browser binaries.

### Changed
- Python 3.10+ required; PostgreSQL 14+ recommended (CI tests against 18).
- Docker images aligned on Python 3.12.
- Documentation fully refreshed: serving modes, incremental updates guide,
  measured performance numbers, theme reference.

## [1.0.0] — 2025-11-30 — "Production Release"

Initial public release: multi-platform archiving (Reddit `.zst`, Voat SQL,
Ruqqus `.7z`), PostgreSQL streaming backend with COPY-protocol imports and
resume capability, static HTML export with full-text search server, REST API
v1 (30+ endpoints), MCP server (29 tools), Docker deployment with HTTPS and
Tor profiles, instance registry.
