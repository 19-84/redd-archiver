# Feature 5: Unicode & Foreign Language Support

**Status:** Planned
**Last updated:** 2026-02-11

**Goal:** Ensure redd-archiver correctly stores, searches, displays, and indexes content from non-English subreddits, including CJK (Chinese/Japanese/Korean), Cyrillic, Arabic, and other scripts.

**Problem:** The current codebase stores and displays Unicode text correctly (UTF-8 throughout), but full-text search is hardcoded to English, title index bucketing has no plan for non-Latin characters, and text truncation breaks on CJK scripts that don't use spaces.

---

## Reddit's Actual Character Constraints

Research into [Reddit's archived source code](https://github.com/reddit-archive/reddit/blob/master/r2/r2/lib/validator/validator.py) and the [Pyprohly API documentation](https://github.com/Pyprohly/reddit-api-doc-notes/blob/main/docs/api-reference/subreddit.rst) establishes which fields can contain Unicode:

| Field | Character Set | Max Length | Unicode? |
|---|---|---|---|
| **Subreddit name** | `[A-Za-z0-9]` first, then `[A-Za-z0-9_]` | 3–21 | **No** (ASCII only) |
| **Username** | `[a-zA-Z0-9_-]` | 3–20 | **No** (ASCII only in practice) |
| **Post title** | Full Unicode | 300 | **Yes** — CJK, Cyrillic, Arabic, emoji, etc. |
| **Post body (selftext)** | Full Unicode + Markdown | 40,000 | **Yes** |
| **Comment body** | Full Unicode + Markdown | 10,000 | **Yes** |
| **Flair text** | Full Unicode + emoji | 64 | **Yes** |
| **Post URL/domain** | Standard URL (punycode for IDN) | URL limits | Punycode |
| **User display name** | Full Unicode | 30 | **Yes** (not used in post/comment JSON) |
| **Subreddit title** | Full Unicode | 100 | **Yes** (display name, not URL name) |

**Key insight:** Subreddit names and usernames are the only truly ASCII-constrained fields. All content fields (titles, bodies, comments, flair) can contain arbitrary Unicode. Our existing validation patterns in `utils/input_validation.py` are correct — they don't need Unicode support for subreddit/username matching.

**Cross-platform consistency:** Voat subverse names and Ruqqus guild names follow the same ASCII-only pattern as Reddit. All three platforms support full Unicode in content fields (titles, bodies, comments). Confirmed by reading `voat_importer.py`, `voat_sql_parser.py` (UTF-8 with `errors="replace"`), `ruqqus_importer.py` (UTF-8 JSON Lines), and `input_validation.py` (ASCII-only patterns not applied during import). The Unicode/FTS improvements in this spec apply equally to archives from all three platforms.

**Source:** Reddit's subreddit name regex from [subreddit.py](https://github.com/reddit-archive/reddit/blob/master/r2/r2/models/subreddit.py):
```python
subreddit_rx = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_]{2,20}\Z")
```

### Subreddit `lang` metadata

Reddit subreddit objects include a `lang` field (e.g., `"en"`, `"de"`, `"ja"`) set by moderators. [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) publishes [subreddit metadata dumps](https://academictorrents.com/details/5d0bf258a025a5b802572ddc29cde89bf093185c) covering 22 million subreddits including this field. This could be used for per-subreddit language detection if needed.

**Open question:** How reliably is `lang` set? No public research on accuracy exists. However, this is a **non-blocking** question: the `lang` field is an optional optimization hint for per-subreddit FTS config selection (see Recommended Approach below), not a prerequisite. The `'simple'` regconfig works for all languages without per-subreddit `lang` data.

### Arctic Shift data format

[Arctic Shift](https://arctic-shift.photon-reddit.com/) uses the same JSON format as Reddit/Pushshift — UTF-8 encoded JSONL in `.zst` files. The [API](https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md) supports keyword search scoped to subreddit/author but cannot do site-wide full-text search, suggesting they face similar CJK tokenization challenges.

Arctic Shift API search fields relevant to us: `title`, `selftext`, `query` (both), `body`, `link_flair_text`, `author`, `subreddit`. All text fields accept Unicode input.

---

## Current State: What Works vs What's Broken

### Working correctly

| Component | Status | Evidence |
|---|---|---|
| UTF-8 storage in PostgreSQL | OK | TEXT columns, no encoding constraints in `sql/schema.sql` |
| `.zst` streaming (read/write) | OK | `core/watchful.py` — Python 3 default UTF-8 decoding |
| HTML rendering | OK | `<meta charset="utf-8">` in `base.html:4`, Jinja2 autoescape enabled |
| File I/O | OK | Explicit `encoding="utf-8"` in `jinja_env.py:113` |
| Subreddit/username validation | OK | ASCII-only patterns match Reddit's actual constraints |

### Broken or degraded

| Component | Location | Issue | Severity |
|---|---|---|---|
| FTS regconfig hardcoded to `'english'` | `core/postgres_search.py:217,266,303,352` | CJK text not tokenized (no word boundaries); English stopwords stripped from all languages | **Critical** |
| FTS indexes hardcoded to `'english'` | `sql/indexes.sql:75-88` | Indexes built for English stemming only | **Critical** |
| Search operator regex `\w+` | `utils/search_operators.py:85,95` | `\w+` only matches ASCII in default mode — `sub:русский` or `author:Müller` won't parse | **Medium** (but subreddits/usernames are ASCII-only on Reddit, so this may not matter in practice) |
| Smart text truncation | `html_modules/jinja_filters.py:116-137` | `rsplit(" ", 1)` — CJK text has no spaces, so truncation cuts mid-character-sequence | **Medium** |
| Title index bucketing (Feature 1) | Planned, not implemented | No spec for titles starting with non-Latin characters | **Low** (not built yet) |

### Investigated (resolved)

| Component | Answer |
|---|---|
| `ILIKE` case folding | **OK.** Docker PostgreSQL `LC_CTYPE` is `en_US.UTF-8` (set via `locale-gen` in the [official Dockerfile](https://github.com/docker-library/postgres/blob/master/16/bookworm/Dockerfile)). ILIKE correctly case-folds Cyrillic, Greek, and other non-ASCII characters with this locale. |
| `ORDER BY LOWER(title)` collation | **Acceptable.** The `en_US.UTF-8` libc collation provides linguistically reasonable (not perfect) ordering for non-ASCII text. ICU collation may be available via PGDG packages (verify with `SELECT * FROM pg_collation WHERE collprovider = 'i';`) but libc is sufficient for initial implementation. |
| `pg_trgm` with CJK | **Available but limited.** `pg_trgm` is included in the postgres:16 image (contrib). With `en_US.UTF-8`, it CAN extract trigrams from CJK characters. However, CJK queries shorter than 3 characters generate 0 trigrams → full index scan fallback. Poor for 1–2 character CJK words (which are common). |
| `pg_trgm` availability | **Yes.** Only `pg_trgm` is available in postgres:16 without custom Docker builds. `pg_bigm`, `pg_cjk_parser`, and PGroonga all require custom Dockerfiles. |

---

## PostgreSQL FTS Options for Multilingual Content

Research into [PostgreSQL's FTS documentation](https://www.postgresql.org/docs/current/textsearch.html) and available extensions:

### Built-in regconfigs

PostgreSQL ships 29 text search configurations. Relevant subset:

| Config | Language | Notes |
|---|---|---|
| `simple` | Language-agnostic | Lowercase only, no stemming. Safest for mixed-language content. |
| `english` | English | Snowball stemmer. Current default. |
| `russian` | Russian | Snowball stemmer. Works for Cyrillic. |
| `arabic` | Arabic | Snowball stemmer. |
| `turkish` | Turkish | Snowball stemmer. Handles dotless-i correctly. |
| (none) | CJK | **No built-in CJK support.** |

### CJK-specific extensions

| Extension | Approach | CJK Quality | Speed | Index Size | Docker-friendly? |
|---|---|---|---|---|---|
| `pg_trgm` (built-in) | 3-character n-grams | Poor for 1–2 char words; locale-dependent | Fast | Small | Yes (contrib) |
| `pg_bigm` | 2-character n-grams | Better than trgm for CJK | 40–50x slower than PGroonga | Small | Needs compilation |
| `pg_cjk_parser` | 2-gram FTS parser for CJK, default parser for rest | Good for CJK | Good | Medium | Needs compilation |
| [PGroonga](https://pgroonga.github.io/) | Groonga engine, language-agnostic | Excellent — all languages | Very fast | Large (~2x) | [Available as extension](https://pgroonga.github.io/install/) |

### Recommended approach (phased)

**Phase 1: Switch to `'simple'` regconfig (minimal change — recommended first step)**

```sql
-- Replace 'english' with 'simple' everywhere
CREATE INDEX idx_posts_search ON posts
  USING GIN(to_tsvector('simple', title || ' ' || COALESCE(selftext, '')));
```

- Zero new dependencies. 6-line change.
- Fixes: Cyrillic, Arabic, Turkish, and all Latin-script languages.
- Trade-off: No English stemming ("running" won't match "run"). CJK no worse than today.
- This is the recommended first step regardless of future CJK strategy.

**Phase 2: Add `pg_trgm` fallback for CJK (available without custom Docker)**

Use `'simple'` regconfig for FTS, add `pg_trgm` GIN index as a fallback for substring/trigram matching. Query tsvector first, fall back to trigram for CJK queries.

- `pg_trgm` is already available in the postgres:16 image (contrib module). No custom Docker build needed.
- Docker locale is `en_US.UTF-8`, which allows `pg_trgm` to extract trigrams from CJK characters.
- Handles CJK queries of 3+ characters. Queries shorter than 3 CJK chars fall back to full index scan.
- Effort: Medium — add trgm index, modify search queries to detect CJK and use appropriate strategy.

**Future (if significant CJK demand emerges): Custom Docker with `pg_cjk_parser` or PGroonga**

| Extension | CJK Quality | Docker Impact | Effort |
|---|---|---|---|
| `pg_cjk_parser` | Good (2-gram for CJK, default parser for rest) | Custom Dockerfile, compile extension | Medium |
| PGroonga | Excellent (all languages) | Custom Dockerfile, ~2x index size, not crash-safe | High |

These are only justified if a significant number of redd-archiver deployments archive CJK subreddits and Phase 2's `pg_trgm` proves insufficient. Both require custom Docker images, which goes against the project's preference for minimal dependencies.

---

## Specific Issues & Proposed Fixes

### 1. FTS regconfig (Critical)

**Current:** `to_tsvector('english', ...)` in 6 locations.

**Minimum fix:** Switch to `'simple'`. This is a 6-line change that improves Cyrillic, Arabic, and all Latin-script languages. CJK remains unsupported but no worse than today.

**Better fix:** `'simple'` + `pg_trgm` or `pg_cjk_parser` for CJK fallback.

**Files affected:**
- `core/postgres_search.py` — 4 query locations
- `sql/indexes.sql` — 2 index definitions

### 2. Search operator regex (Medium)

**Current:** `\w+` in `utils/search_operators.py:85,95` for `sub:` and `author:` operators.

**Analysis:** Since Reddit subreddit names and usernames are ASCII-only, this is not actually broken for real data. The regex correctly matches the only characters that can appear in these fields. No fix needed unless we want to future-proof for non-Reddit platforms.

**Recommendation:** Document as intentional, not a bug. Add a code comment explaining the ASCII constraint matches Reddit's rules. This applies equally to Voat subverses and Ruqqus guilds, which follow the same ASCII-only naming convention.

### 3. Smart text truncation (Medium)

**Current:** `text[:length].rsplit(" ", 1)[0]` — splits on spaces only.

**Fix:** Add script-aware truncation. For CJK text (detected by Unicode block), truncate at character boundary without looking for spaces. For Latin/Cyrillic/Arabic text, keep the current space-based approach.

```python
def truncate_smart(text, length=150, suffix="..."):
    if len(text) <= length:
        return text
    truncated = text[:length]
    # CJK characters don't use spaces — truncate at character boundary
    if not any(c == ' ' for c in truncated[-20:]):
        return truncated + suffix
    return truncated.rsplit(" ", 1)[0] + suffix
```

**File:** `html_modules/jinja_filters.py:116-137`

### 4. Title index bucketing (Feature 1, Low — not built yet)

**Proposed approach:** Add a catch-all bucket for titles starting with non-Latin characters.

```
r/{subreddit}/titles/a/          # Latin A
...
r/{subreddit}/titles/z/          # Latin Z
r/{subreddit}/titles/0-9/        # Digits and punctuation
r/{subreddit}/titles/other/      # Non-Latin first characters (CJK, Cyrillic, Arabic, etc.)
```

For subreddits that are primarily non-English (detectable via the `lang` metadata), consider script-specific bucketing (e.g., Cyrillic А–Я, Hiragana あ–ん). But this is a Feature 1 implementation detail, not a Feature 5 concern.

### 5. Database locale (Needs investigation)

**Risk:** If the Docker PostgreSQL container uses `LC_CTYPE=C`, then:
- `ILIKE` won't case-fold non-ASCII characters
- `pg_trgm` won't recognize CJK characters
- `LOWER()` may not lowercase non-ASCII characters correctly

**Action needed:** Check the current Docker PostgreSQL image locale configuration. The official `postgres:16` image defaults to `en_US.UTF-8` on Debian, but this should be verified.

---

## Resolved Research

All questions that previously blocked this spec have been answered or reframed as non-blocking:

| # | Question | Resolution |
|---|----------|------------|
| 1 | Reddit `lang` field reliability | **Non-blocking.** No public research on accuracy. `lang` is an optional optimization hint for per-subreddit FTS config, not a prerequisite. `'simple'` regconfig works without it. If Feature 6 (Metadata Enrichment) imports `lang` data, it can be used as an enhancement later. |
| 2 | Docker PostgreSQL `LC_CTYPE` | **`en_US.UTF-8`.** Set via `locale-gen` in the [official Dockerfile](https://github.com/docker-library/postgres/blob/master/16/bookworm/Dockerfile). ILIKE, LOWER(), pg_trgm all function correctly with this locale. |
| 3 | Non-English subreddit fraction | **Deployment-dependent.** Phase 1 (simple regconfig) is a 6-line change that helps ALL non-English content with zero risk. CJK-specific support (Phase 2) is an opt-in enhancement, not a prerequisite. |
| 4 | `pg_trgm` CJK behavior | **Partial.** With `en_US.UTF-8`, pg_trgm extracts trigrams from CJK characters. Queries <3 CJK chars generate 0 trigrams → full index scan. Acceptable for Phase 2; better CJK requires custom Docker extensions. |
| 5 | Extension availability in postgres:16 | **Only `pg_trgm`** (contrib) is available without custom builds. `pg_bigm`, `pg_cjk_parser`, PGroonga all need custom Dockerfiles. |
| 6 | ICU collation support | **Likely available** via PGDG package dependencies (`libicu72`), but needs verification: `SELECT * FROM pg_collation WHERE collprovider = 'i';`. Non-blocking — libc collation with UTF-8 is sufficient for Phase 1. |
| 7 | Voat/Ruqqus Unicode patterns | **Identical to Reddit.** All three platforms: ASCII-only community names, full Unicode content fields. Confirmed from codebase (`voat_importer.py`, `voat_sql_parser.py`, `ruqqus_importer.py`, `input_validation.py`). |

### Remaining empirical tests (nice-to-have, not blocking)

These can be verified when a Docker environment is available:

- `SHOW lc_ctype;` — confirm `en_US.UTF-8` in running container
- `SELECT * FROM pg_collation WHERE collprovider = 'i';` — confirm ICU availability
- `SELECT show_trgm('日本語');` — verify pg_trgm CJK trigram extraction
- Sample Arctic Shift metadata dump for `lang` field distribution (if Feature 6 lands first)

---

## Testing Strategy

### Test data needed
- Posts with CJK titles and bodies (from r/japan, r/China, r/korea, r/newsokur)
- Posts with Cyrillic text (from r/ru, r/russian, r/pikabu)
- Posts with Arabic text (from r/arabs, r/arabic)
- Posts with mixed-script content (English + CJK in same title)
- Flair text with emoji and non-Latin characters
- Edge case: empty titles, single-character titles, emoji-only titles

### Key test scenarios
- FTS returns results for non-English search queries
- CJK search queries return relevant posts (if CJK extension adopted)
- Title index correctly buckets non-Latin titles
- Smart truncation produces valid output for CJK text
- `ILIKE` case-folds Cyrillic characters correctly
- Sorting by title produces linguistically reasonable order for non-Latin text

---

## Cross-References

- See [01-static-index-improvements.md > Phase 1](01-static-index-improvements.md#phase-1-post-title-index) — title bucketing needs non-Latin character handling
- See [02-dynamic-serving-mode.md > Phase 4](02-dynamic-serving-mode.md#phase-4-dynamic-only-features) — dynamic flair/title filtering queries affected by FTS config
- See [03-incremental-update-system.md](03-incremental-update-system.md) — Arctic Shift data contains same Unicode content as original Reddit data
- See [04-visual-themes.md](04-visual-themes.md) — no direct dependency, but CJK text may need CSS adjustments for line-breaking (`word-break: break-all` vs `overflow-wrap`)
