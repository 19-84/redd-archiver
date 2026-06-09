# Redd-Archiver Project Roadmap

**Status:** Draft — under active refinement
**Last updated:** 2026-06-09

---

## Overview

This roadmap outlines the major development features for redd-archiver beyond v1.0.0. The goal is to evolve from a static archive generator into a more versatile platform that supports multiple serving modes, keeps archives current with minimal manual effort, and offers flexible visual presentation.

---

## Feature Summary

| # | Feature | Spec | Status |
|---|---------|------|--------|
| 1 | [Static Index & Search Improvements](01-static-index-improvements.md) | Title index, flair index, archive map | Planned |
| 2 | [Dynamic Serving Mode](02-dynamic-serving-mode.md) | Flask serves all pages (5 phases) | Planned |
| 3 | [Incremental Update System](03-incremental-update-system.md) | Arctic Shift monthly imports (4 phases) | Planned |
| 4 | [Visual Themes](04-visual-themes.md) | CSS theme system (4 phases) | Planned |
| 5 | [Unicode & Foreign Language Support](05-unicode-foreign-language-support.md) | Multilingual FTS, CJK support, text handling | Planned |
| 6 | [Subreddit Metadata Enrichment](06-subreddit-metadata-enrichment.md) | Import descriptions, rules, wikis from Arctic Shift | Planned |
| 7 | [Voat Data Enrichment](07-voat-data-enrichment.md) | Subverse metadata, user profiles, thumbnails, flair (5 phases) | Planned |
| 8 | [Pyright Type Checking](08-pyright-type-checking.md) | Add pyright standard mode, CI integration | Planned |
| 9 | [SIM + RUF Ruff Rules](09-ruff-sim-ruf-rules.md) | Enable flake8-simplify and Ruff-specific rules | Planned |
| 10 | [Pre-Commit Hooks](10-pre-commit-hooks.md) | Activate local pre-commit hooks with ruff | Planned |
| 11 | [Docker Python Alignment](11-docker-python-version-alignment.md) | Fix 3.14 vs 3.12 version mismatch | Planned |

---

## Serving Modes

Redd-archiver supports three serving modes. The mode determines what infrastructure is needed at runtime (after data has been imported) and what features are available to end users.

### Static Mode

Pure static HTML files. No server or database needed at runtime. Deployable to GitHub Pages, Netlify, Codeberg Pages, S3, any web host, or even served from a USB stick.

**Runtime requirements:** Any HTTP server (nginx, Apache, Caddy) or static hosting platform. No PostgreSQL, no Flask.

**Build requirements:** PostgreSQL (for import + export pipeline). Database can be torn down after export completes.

**Available features (existing):**
- Subreddit index pages (score, comments, date sort orders)
- Individual post pages with full comment trees
- User profile pages
- SEO sitemaps

**Planned additions (Feature 1):**
- Post title index with browser `Ctrl+F` search
- Flair index (where flair data exists)
- Archive map page (replaces non-functional search form)

**Not available:**
- Full-text search
- Dynamic filtering (date range, flair, domain, score threshold)
- Cross-subreddit browsing
- REST API / MCP integration

**CLI:**
```bash
reddarc.py /data --output /var/www/html/ --subreddit privacy ...
# or, if data is already in PostgreSQL:
reddarc.py --export-from-database --output /var/www/html/
```

### Hybrid Mode (current default)

Static HTML files served by nginx, plus the Flask search server for full-text search and the REST API. This is how redd-archiver works today with `docker compose up`.

**Runtime requirements:** nginx + Flask + PostgreSQL.

**Available features:** Everything in static mode, plus:
- Full-text search with Google-style operators
- REST API (30+ endpoints)
- MCP server integration (29 tools)

**Not available:**
- Dynamic filtering (date range, flair, domain, score threshold)
- Cross-subreddit browsing
- Instant content availability after import (still requires export step)

**CLI:**
```bash
reddarc.py /data --output /var/www/html/ --subreddit privacy ...
search_server.py   # search + API only, nginx serves static pages
```

### Dynamic Mode

Flask + PostgreSQL serve all pages on-the-fly. No static HTML generation step. Content is available immediately after import.

**Runtime requirements:** Flask + PostgreSQL (nginx recommended as reverse proxy).

**Available features:** Everything in hybrid mode, plus:
- Dynamic filtering: date range, flair, domain, score threshold
- Cross-subreddit browsing (`/all/`)
- Arbitrary sort orders and combinations
- Instant content availability (no export step)
- Zero disk usage for HTML files

**Not available:**
- Offline browsing / USB stick distribution
- GitHub Pages / Netlify / static CDN hosting
- Operation without a running server + database

**CLI:**
```bash
reddarc.py --import-only /data --subreddit privacy ...
REDDARCHIVER_SERVE_MODE=dynamic search_server.py   # Flask serves all page types
```

### Mode comparison

| | Static | Hybrid (current) | Dynamic |
|---|---|---|---|
| Runtime PostgreSQL | No | Yes | Yes |
| Runtime Flask | No | Yes (search only) | Yes (all pages) |
| Export step required | Yes | Yes | No |
| Full-text search | No | Yes | Yes |
| REST API | No | Yes | Yes |
| Dynamic filtering | No | No | Yes |
| Cross-subreddit view | No | No | Yes |
| GitHub Pages compatible | Yes | No | No |
| Offline browsing | Yes | Pages only (search requires server) | No |
| Disk usage for HTML | High | High | Zero |
| Content available after import | After export | After export | Immediately |

### Mode selection

```bash
# Static mode: import + export, no server needed afterward
reddarc.py /data --output /var/www/html/ --subreddit privacy ...

# Hybrid mode (current default): same as above, then start search server
search_server.py

# Dynamic mode: import only, then start full server
reddarc.py --import-only /data --subreddit privacy ...
REDDARCHIVER_SERVE_MODE=dynamic search_server.py
```

**Mode selection implementation note:** The current `search_server.py` has no argparse or CLI flags — it is entirely configured via environment variables and invoked via Gunicorn in Docker. To maintain this pattern, dynamic mode is activated via an environment variable rather than a CLI flag:

```bash
# Hybrid mode (current default — search + API only)
REDDARCHIVER_SERVE_MODE=hybrid   # or unset (default)

# Dynamic mode (all page types served by Flask)
REDDARCHIVER_SERVE_MODE=dynamic
```

In Docker, the `--profile dynamic` compose profile sets this variable automatically. For local development, set the env var before starting the server:

```bash
# Local hybrid mode
uv run python search_server.py

# Local dynamic mode
REDDARCHIVER_SERVE_MODE=dynamic uv run python search_server.py
```

When `REDDARCHIVER_SERVE_MODE=dynamic`, Flask registers additional route handlers for dashboard, subreddit indexes, post pages, and user pages. When unset or set to `hybrid`, Flask only handles `/search`, `/health`, `/api/v1/*`, and error pages (current behavior).

---

## Release Ordering & Execution Strategy

**Recommendation: Foundation fixes first, then phase-granular delivery. Features are interleaved by phase rather than completed sequentially.**

The ordering below prioritizes small, high-value wins early (fixing existing bugs and gaps) before larger architectural work. Each step builds on the previous one, and phases within features are split across steps where it makes sense.

### Step 1: Foundation Fixes (~1 day)

**F5 Phase 1 (simple regconfig) + F5 truncation fix + F2 Phase 1 (Jinja filter import)**

Three small, independent changes that fix existing FTS and rendering gaps:

- **F5 Phase 1:** Replace `'english'` with `'simple'` regconfig across its ~20 occurrences in `core/postgres_search.py`, `api/routes.py`, and `sql/indexes.sql`. Fixes FTS for all non-English content (Cyrillic, Arabic, Latin-script languages). Immediate value.
- **F5 truncation fix (cosmetic):** `truncate_smart()` in `html_modules/jinja_filters.py` does `text[:length].rsplit(" ", 1)[0]`. This is code-point-safe — it never corrupts multi-byte characters — but for space-less scripts (CJK) the word-boundary step is a no-op, so the truncation has no graceful break point. Add script-aware truncation. Lower priority than the regconfig fix (no correctness impact).
- **F2 Phase 1:** Import the cached filters from `html_modules/jinja_filters.py` into `search_server.py` and register them — it currently registers only `highlight` and `number_format` and never imports the shared filter module. Prerequisite that unblocks dynamic-mode template rendering.

### Step 2: Static Index & Search Improvements (F1, all phases)

The full Feature 1 — title index, flair index, and archive map page. Medium scope, no dependencies, immediate value for static and hybrid mode users. The archive map page also replaces the non-functional search form in static-only deployments.

### Step 3: CSS Token Extraction (F4 Phase 1)

Replace 478 hardcoded color overrides in `redd-archiver-universal.css` with CSS custom properties. Zero visual change. This is a prerequisite for Steps 4+ — new component styles (about pages, rules lists, dashboard enrichment) must use `var(--token)` from the start to avoid double-work when adding metadata UI.

### Step 4: Metadata Enrichment Phase 1 (F6 Phase 1 + F7 Phase 1)

Import subreddit descriptions and rules from Arctic Shift dumps (F6), and subverse metadata from Voat SQL dumps (F7). Enriches archives with contextual information that was previously missing. F6 requires `markdown` + `bleach` dependencies for safe rendering; F7 only needs `bleach` (Voat sidebar HTML is pre-rendered). F7 Phase 1 can ship alongside F6 Phase 1 — they share a new `subreddit_metadata` table and a new about-page template (`templates_jinja2/pages/subreddit_about.html`), both introduced by this work (neither exists today). Phase 2 (wiki import) is deferred until the wiki dump path format is verified empirically.

### Step 5: Dynamic Serving Mode Phases 2–4 (F2 core)

The biggest value-add — template adaptation, page routes, dynamic filtering, and cross-subreddit browsing. Most infrastructure (Flask, Jinja2, PostgreSQL queries) already exists in hybrid mode. This step extends hybrid into a full application server with clean URLs and query-parameter-driven filtering.

### Step 6: Incremental Update System (F3, all phases)

Benefits from dynamic mode being available: in dynamic mode, importing new data makes it immediately browsable with no re-export step. In static/hybrid modes, incremental updates must also trigger selective re-export, which adds complexity. Shipping dynamic mode first makes the update system simpler for at least one serving mode.

### Later Phases (demand-driven)

These phases are valuable but not urgent. Ship when demand justifies the effort:

| Phase | What | Why deferred |
|---|---|---|
| F5 Phase 2 | pg_trgm CJK fallback | Only needed if significant CJK archive demand emerges |
| F4 Phases 2–4 | System preference, theme-agnostic CSS, custom branding | Phase 1 (tokens) is the prerequisite; further phases add polish |
| F6 Phases 2–3 | Wiki import, image archival | Wiki blocked on path format verification; images blocked on CDN persistence research |
| F7 Phases 2–5 | User profiles, moderators, flair, thumbnails, historical data | Phase 1 (subverse metadata) is the prerequisite; thumbnails need storage decisions |
| F2 Phase 5 | Performance optimization | Only needed after dynamic mode is live and under real load |

### Dependencies

- **F5 Phase 1:** No dependencies. Fixes existing FTS behavior.
- **F2 Phase 1:** No dependencies. Trivial prerequisite for F2 Phases 2+.
- **F1:** No dependencies. Fully independent of all other features.
- **F4 Phase 1:** No dependencies. Must land before F6/F7 frontend work (Step 4) so new component styles use design tokens from the start. Template changes (Phases 2+) should be coordinated with F2 Phase 2.
- **F6 Phase 1:** Depends on F4 Phase 1 (Step 3) for CSS tokens. Needs `markdown` + `bleach` packages.
- **F7 Phase 1:** Depends on F4 Phase 1 (Step 3) for CSS tokens. Shares `subreddit_metadata` table with F6. Ships alongside F6 Phase 1 in Step 4. Simpler than F6P1 (no markdown rendering — Voat sidebar HTML is pre-rendered). Only needs `bleach` for XSS sanitization.
- **F2 Phases 2–4:** Depends on F2 Phase 1 (Step 1). Template changes should be coordinated with F4 Phase 1 (Step 3).
- **F3:** Works in all three modes. Simplest in dynamic mode (no re-export step) — not a hard dependency, but benefits from F2 shipping first.

---

## URL Compatibility Across Modes

Static and hybrid modes use file-based paths (matching the generated HTML file structure). Dynamic mode uses proper web application URLs:

| Page | Static/Hybrid Path | Dynamic URL |
|---|---|---|
| Subreddit index | `/r/privacy/index.html` | `/r/privacy/` |
| Page 2, by score | `/r/privacy/index-2.html` | `/r/privacy/?page=2` |
| By comments | `/r/privacy/index-comments/index.html` | `/r/privacy/?sort=comments` |
| Post page | `/r/privacy/comments/abc123/slug/index.html` | `/r/privacy/comments/abc123/slug/` |
| User page | `/user/johndoe/index.html` | `/user/johndoe/` |
| Title index | `/r/privacy/titles/a/` | `/r/privacy/titles/a/` (same) |

The dynamic server handles incoming requests for static-style paths by issuing 301 redirects to the clean equivalents. This means:

- Dynamic mode gets clean, conventional URLs
- Bookmarks and links from a previous static/hybrid deployment continue to work
- Search engine rankings transfer gracefully via 301 permanent redirects
- Switching from static/hybrid to dynamic hosting is seamless for end users
- A `url_for_page()` Jinja2 helper (to be added as part of this feature — it does not exist yet) will generate the correct URL format based on which mode the templates are being rendered in (file paths for static/hybrid export, clean URLs for dynamic serving)

---

## Infrastructure Considerations

### Docker configuration per mode

The current `docker-compose.yml` defines these base services: `postgres`, `reddarchiver-builder` (one-shot CLI), `search-server` (Flask), `nginx` (reverse proxy + static files), and `mcp-server` (AI integration). The `certbot` and `tor` services are gated behind the `production` and `tor` profiles.

**Services needed per mode:**

| Service | Static | Hybrid (current) | Dynamic |
|---|---|---|---|
| `postgres` | Build-time only | Yes | Yes |
| `reddarchiver-builder` | Yes (import + export) | Yes (import + export) | Yes (import only) |
| `search-server` | Not needed | Yes (search + API) | Yes (`SERVE_MODE=dynamic`) |
| `nginx` | Yes (static files) | Yes (static files + proxy) | Yes (reverse proxy only) |

**Docker compose profiles:**

The project already uses profiles for `production` (HTTPS/certbot) and `tor` (hidden service). Serving mode adds a `dynamic` profile:

```bash
# Static mode: start only what's needed for import + export
docker compose up -d postgres reddarchiver-builder
# Run the archive build:
docker compose exec reddarchiver-builder python reddarc.py /data \
  --output /output/ --subreddit privacy ...
# Then start nginx alone to serve the static files:
docker compose up -d nginx
docker compose stop postgres reddarchiver-builder

# Hybrid mode (current default): all base services running
docker compose up -d

# Dynamic mode: Flask serves everything
docker compose --profile dynamic up -d
```

The `--profile dynamic` profile:
- Sets `REDDARCHIVER_SERVE_MODE=dynamic` on the `search-server` service (see mode selection note below)
- Swaps the nginx config to proxy all requests to Flask (instead of serving static files)
- The `reddarchiver-builder` service still runs for `--import-only` operations

Existing profiles (`production`, `tor`) compose with any serving mode:
```bash
# Dynamic + HTTPS + Tor
docker compose --profile dynamic --profile production --profile tor up -d
```

**Nginx config per mode:**

```
# Static mode
location / {
    root /var/www/html;                        # serve pre-generated files
    try_files $uri $uri/ =404;
}

# Hybrid mode (current default)
location / {
    root /var/www/html;                        # serve pre-generated files
    try_files $uri $uri/ =404;
}
location /search { proxy_pass http://search-server:5000; }
location /api/   { proxy_pass http://search-server:5000; }
location /health { proxy_pass http://search-server:5000; }

# Dynamic mode (--profile dynamic)
location / {
    proxy_pass http://search-server:5000;      # Flask serves everything
    proxy_set_header Host $host;
}
location /static/ {
    root /app/;                                # CSS/images from Flask static dir
    expires 30d;
}
```

**What stays the same across all modes:**
- `postgres` service configuration is identical
- All existing profiles (production, tor) compose with any serving mode
- Environment variables (`DATABASE_URL`, `FLASK_SECRET_KEY`, etc.) are shared
- The same Docker images are used for all serving modes — the mode is determined by environment variables and compose profiles, not separate builds

### Docker changes for incremental updates

The `reddarchiver-builder` container needs access to Arctic Shift dump files. This is handled the same way as existing `.zst` imports — via the `DATA_PATH` volume mount. No new containers needed; the update commands run in the existing builder container:

```bash
sudo docker compose exec reddarchiver-builder python reddarc.py --update /data/RS_2026-01.zst \
  --comments-file /data/RC_2026-01.zst --output /output/
```

---

## Mode Switching & Migration

### Upgrading existing v1.0 archives

Each feature is designed to be additive — no breaking changes to existing archives or database schemas.

**Feature 1 (static indexes):** Existing archives gain title index, flair index, and archive map pages by re-running `--export-from-database` with the updated version. No database migration needed — the expression index for flair queries is created automatically during export. Existing pages are untouched; only new files are added to the output directory. Benefits both static and hybrid mode users.

**Feature 2 (dynamic mode):** Existing databases work as-is with dynamic serving. The schema is unchanged. Users running hybrid mode set `REDDARCHIVER_SERVE_MODE=dynamic` (or use `--profile dynamic` in Docker) to switch to dynamic mode. No re-import needed.

**Feature 3 (incremental updates):** The `update_history` table is new and created automatically on first use (guarded by `CREATE TABLE IF NOT EXISTS`). Existing `processing_metadata` entries are unaffected. The first incremental update simply imports new data alongside existing records — the upsert logic handles deduplication transparently. No manual migration steps required. Works in all three serving modes.

**Feature 4 (visual themes):** Phase 1 is a CSS-only refactor with zero visual change. Existing archives can adopt the new CSS by re-running `--export-from-database`. No database or template migration needed. Phase 3 decouples the CSS from any specific theme — operators select a theme via `--theme` at export time (static) or `REDDARCHIVER_THEME` env var (dynamic). Each theme provides both dark and light palettes; users control only the dark/light mode.

**Schema version tracking:** Each new table or index adds a version entry to the `schema_version` table (currently at version 4, set by `sql/migrations/004_add_platform_support.sql`). Migrations live as ordered SQL files under `sql/migrations/`. Note: the current code records the schema version but does **not** yet auto-apply pending migrations at startup — `get_schema_version()` exists in `core/postgres_database.py` but has no callers, and DB setup only runs `schema.sql` + `indexes.sql`. The incremental-update work (F3) should add the missing migration runner.

### Switching between serving modes

Users can switch modes at any time without data loss or re-import:

| Transition | Steps |
|---|---|
| Static → Hybrid | Start Flask (`search_server.py`) and PostgreSQL. Update nginx config to proxy `/search` and `/api/` to Flask. Database must contain the imported data (re-import if it was torn down after initial export). |
| Hybrid → Dynamic | Set `REDDARCHIVER_SERVE_MODE=dynamic` (or `--profile dynamic` in Docker). Update nginx to proxy all requests to Flask. Static HTML files can be deleted or kept as a backup. |
| Dynamic → Hybrid | Unset `REDDARCHIVER_SERVE_MODE` (or remove `--profile dynamic`). Run `--export-from-database` to generate static HTML. Update nginx to serve static files with Flask proxied for search/API only. |
| Hybrid → Static | Stop Flask and PostgreSQL. Static HTML files continue to work. Search becomes unavailable. |
| Dynamic → Static | Run `--export-from-database` to generate static HTML. Configure nginx to serve static files. Stop Flask and PostgreSQL. |
| Any → Any | The PostgreSQL database is the canonical data store. As long as the database exists (or can be re-created from source `.zst` files), any mode can be activated. In static mode, the HTML files are a self-contained copy — the database can be torn down after export, but must be restored to switch back to hybrid or dynamic. |
