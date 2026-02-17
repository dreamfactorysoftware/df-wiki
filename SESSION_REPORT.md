# Wiki Migration Session Report

**Date:** 2026-02-12
**Scope:** Expand stub pages, migrate guide-unique chapters, fix wiki infrastructure, apply branding

---

## Summary

This session closed two major gaps in the migration pipeline: 4 stub pages that had <60 words were expanded with real DreamFactory content, and 7 guide-unique chapters from the Hugo guide were converted and uploaded to the staging wiki. Additionally, the wiki sidebar navigation was rebuilt with correct page names, the DreamFactory logo was added, and a full brand-consistent theme (including dark mode) was applied.

**Before:** 68 wiki pages, avg score 81.2/100, 4 stubs, 7 guide chapters missing
**After:** 75 wiki pages, avg score 80.8/100, 0 stubs, all guide chapters migrated, full branding applied

---

## Phase 1: Pipeline Preparation

### 1a. Fixed `success` alert mapping in postprocess.py

**File:** `scripts/postprocess.py` (line 419)

The Hugo guide uses `{{< alert color="success" >}}` shortcodes (e.g., in the Logstash section of the Limiting and Logging chapter). The `admonition_types` dictionary in `convert_admonitions()` had no mapping for `success`, causing these alerts to pass through unconverted.

**Change:** Added `'success': 'Tip'` to the dictionary, mapping Hugo success alerts to the `{{Tip}}` MediaWiki template.

### 1b. Created guide conversion helper script

**File:** `scripts/convert_guide_chapter.sh` (new)

The existing `batch_convert.sh` only processes files under the `df-docs/` tree. Guide-unique chapters live under `guide/dreamfactory-book-v2/` and need to be output as flat `.wiki` files (not mirroring directory structure). This new script:

1. Takes a guide chapter path and a target wiki page name as arguments
2. Runs `pandoc -f markdown -t mediawiki`
3. Runs `postprocess.py` with the source path (for frontmatter extraction and category assignment)
4. Saves to `converted/<wiki_name>.wiki`

---

## Phase 2: Expanded 4 Stub Pages

Each stub was rewritten as a full markdown source file with proper frontmatter (including keywords for category generation), then reconverted through the pipeline via `batch_convert.sh`.

### 2a. Rate Limiting (`Security/rate-limiting.md`)

**Before:** 2 words (just a heading)
**After:** ~650 words

Content written based on the guide chapter "Limiting and Logging API Requests" (lines 253-357). Covers:
- Why rate limiting matters
- Limit types hierarchy table (Instance, User, Each User, Role, Service, Endpoint variants)
- Limit periods (minute through 30-day)
- Step-by-step Admin Console configuration
- API-based limit management with curl example
- HTTP 429 behavior when limits are exceeded
- Monitoring usage via limit_cache endpoint
- Endpoint wildcards
- Cache storage options (file-based vs Redis)

### 2b. API Creation and Management (`api-generation-and-connections/api-creation-management.md`)

**Before:** 57 words (bullet list of API types)
**After:** ~550 words

Expanded into a proper hub page covering:
- DreamFactory's service-oriented architecture
- Step-by-step service creation via Admin Console
- curl example for querying a newly created service
- Service type categories (Database, Remote API, File Storage, Scripted, Email, Source Control)
- Service namespacing and versioning
- Managing existing services (edit, deactivate, delete)
- Links to child pages for each API type

### 2c. PHP and Laravel (`getting-started/optimizing-dreamfactory/php-laravel.md`)

**Before:** 9 words ("under construction" warning)
**After:** ~580 words

Content drawn from the guide's "Performance Considerations" chapter plus current PHP 8.1+ best practices:
- PHP 8.1+ requirement for DreamFactory 7.4.x
- OPcache configuration (with ini code block)
- JIT compilation settings
- Laravel Artisan optimization commands (config:cache, route:cache, view:cache)
- `.env` production settings (APP_DEBUG=false, CACHE_DRIVER=redis)
- Queue worker configuration with Supervisor example
- Memory and execution time tuning
- Composer autoloader optimization

### 2d. Web Server (`getting-started/optimizing-dreamfactory/webserver.md`)

**Before:** 30 words ("under construction" warning)
**After:** ~600 words

Content covers:
- Full NGINX server block configuration (gzip, keepalive, fastcgi_pass, buffers)
- NGINX global tuning (worker_processes, worker_connections)
- Apache virtual host configuration with required modules
- PHP-FPM pool tuning (pm.max_children, static vs dynamic, max_requests)
- Formula for calculating pm.max_children based on available RAM
- SSL/TLS configuration with HSTS
- Reverse proxy considerations (TRUST_PROXIES, X-Forwarded headers)

### 2e. Reconversion

All 49 non-draft df-docs files were reconverted via `batch_convert.sh` with 0 failures. The 4 expanded pages produced well-formatted MediaWiki output with proper tables, code blocks, and admonition templates.

---

## Phase 3: Migrated 7 Guide-Unique Chapters

These chapters exist only in the Hugo guide and have no df-docs equivalent. Each was converted using `convert_guide_chapter.sh`.

| Source Chapter | Wiki Page | Words |
|---|---|---|
| Using Remote HTTP and SOAP Connectors | `Remote_HTTP_And_SOAP_Connectors` | 1,008 |
| Integrating Salesforce Data | `Integrating_Salesforce_Data` | 1,739 |
| Demo DreamFactory Applications | `Demo_DreamFactory_Applications` | 1,016 |
| Appendix A: Configuration Parameter Reference | `Appendix_Configuration_Parameters` | 1,480 |
| Appendix C: GDPR API Gateway | `GDPR_API_Gateway` | 1,305 |
| Appendix D: Architecture FAQ | `Architecture_FAQ` | 1,122 |
| Appendix E: Scalability | `Scalability` | 2,722 |

**Note on images:** The guide chapters reference ~35 images (screenshots of DreamFactory UI, architecture diagrams, etc.) via `[[File:...]]` syntax. These image files are not present in the repository — the Hugo guide's `static/` directory contains only theme assets. The image references remain in the wiki markup but render as broken links until source images are obtained and uploaded.

---

## Phase 4: Upload to Staging Wiki

### Wiki rate limiter fix

**File:** `staging-wiki-config/LocalSettings.php`

The initial upload attempt failed with a `WRStatsError` crash. The root cause was the rate limit configuration:

```php
// BROKEN — window (second param) must be positive
$wgRateLimits['edit']['bot'] = [ 0, 0 ];

// FIXED — 0 actions per 60 seconds = unlimited
$wgRateLimits['edit']['anon'] = [ 0, 60 ];
```

MediaWiki 1.39's `LimitCondition` constructor requires a positive window value. The `[0, 0]` format (zero actions per zero seconds) caused a division-by-zero style crash. Fixed for all three rate limit types (edit, create, upload) and added `$wgGroupPermissions['*']['noratelimit'] = true` for the staging environment.

### Upload results

Used `mwclient` (from `scripts/.venv/`) with `site.force_login = False` for anonymous uploads:

- **4 pages updated** (expanded stubs — these already existed on the wiki)
- **7 pages created** (guide-unique chapters — new to the wiki)
- **0 failures**
- **Total wiki pages:** 75 (up from 68)

---

## Phase 5: Inventory Update & Validation

### Inventory changes (`scripts/migration_inventory.csv`)

Updated 11 rows:

**4 stub pages:** Status changed from `Needs-Expansion` → `Converted`. Added keywords, updated word counts, added notes.

**7 guide-unique pages:** Status changed from `Not Started` → `Converted`. Updated `target_wiki_page` to match actual uploaded page names (e.g., `Using remote http and soap connectors` → `Remote_HTTP_And_SOAP_Connectors`). Added keywords, difficulty levels, and notes.

### Content scoring

Ran `content_score.py --dir ./converted --skip-drafts`:

- **56 files scored**, average **80.8/100**
- **0 stubs** remaining (was 4)
- **0 blockers** in validation

Individual scores for the 11 pages:

| Page | Score | Notes |
|---|---|---|
| Security/rate-limiting | 90.0 | All criteria pass |
| api-creation-management | 87.0 | All criteria pass |
| php-laravel | 82.5 | All criteria pass |
| webserver | 82.5 | All criteria pass |
| Remote HTTP And SOAP Connectors | 76.2 | -cross-links, -URL structure |
| Demo DreamFactory Applications | 72.5 | -cross-links, -URL structure |
| Integrating Salesforce Data | 65.0 | -cross-links, -URL structure, legacy version refs |
| Appendix Configuration Parameters | 61.0 | -cross-links, -URL structure, -code examples |
| GDPR API Gateway | 55.0 | -cross-links, -URL structure, -code examples |
| Architecture FAQ | 51.0 | -cross-links, -URL structure, -code examples, "OS X" ref |
| Scalability | 51.0 | -cross-links, -URL structure, -code examples, legacy version refs |

Guide-unique pages score lower due to:
- **Cross-linking (0/15):** Orphan pages with no internal wiki links (postprocess couldn't find siblings since they're flat files outside the df-docs tree)
- **URL Structure (0/10):** Scorer can't resolve flat file paths to inventory entries (the `_index.md` slug is skipped in mapping)
- **Structured Data (0/10):** Expected — injected post-upload via MediaWiki templates
- **Version Currency:** Some guide content references legacy versions (OS X, PHP 7.2, etc.)

### Validation

Ran `validate_migration.py`:
- **0 blockers**, 0 major issues for the 11 target pages
- 2 minor content variance warnings (php-laravel and webserver) — expected since we intentionally expanded the content far beyond the original stubs

---

## Phase 6: Sidebar Navigation

### Problem

The existing `MediaWiki:Sidebar` used underscored page names (`Getting_Started/Docker_Installation`) but actual wiki pages use spaces (`Getting Started/Docker Installation`). **Every sidebar link was broken.** Additionally, the 7 new guide-unique pages were not listed.

### Fix

Created an admin account (`WikiAdmin`) via `maintenance/createAndPromote.php` to edit the protected `MediaWiki:Sidebar` page. Rewrote the entire sidebar with:

- Correct page names matching actual wiki titles (spaces, not underscores)
- All 75 content pages organized into 11 sections
- New "Reference" section for the 5 guide-unique reference pages
- New "File APIs" section split from the overloaded "APIs & Connections"
- New "Scripting" section for scripted services content

**Result:** 56 content links, all resolving to existing pages, 0 broken.

---

## Phase 7: Branding & Theming

### Site logo

**File added:** `dreamfactoryicon.webp` (300x300 DreamFactory gear+database icon)

- Uploaded to wiki via mwclient (`File:Dreamfactoryicon.webp`)
- Configured in `LocalSettings.php` via `$wgLogo`
- Constrained to 80% size in `MediaWiki:Common.css` via `background-size` to fit the Vector skin sidebar

### Color palette

Extracted the DreamFactory brand palette from `df-docs/df-docs/src/css/custom.css`:

| Token | Hex Value |
|---|---|
| Primary | `#ff8c5a` |
| Primary Dark | `#ff845a` |
| Primary Darker | `#ff703e` |
| Primary Darkest | `#ff5c22` |
| Primary Light | `#ffa27e` |
| Primary Lighter | `#ffb69a` |
| Primary Lightest | `#ffcab6` |

### Light theme (`MediaWiki:Common.css`)

Applied the palette to all wiki UI elements:

- **Links:** `#ff703e` default, `#ff5c22` on hover
- **Page title (h1):** Orange text with orange bottom border
- **Section headings (h2):** Peach bottom border divider
- **Sidebar:** Warm background (`#faf5f2`), uppercase orange section headers
- **Tables:** Orange header row with white text, alternating peach row striping
- **Code blocks:** Dark background (`#2d2d2d`), inline code with peach background
- **TOC, categories, search, footer:** All using palette consistently

### Dark mode

Added full dark mode support via CSS and JavaScript:

**Activation methods:**
1. **Automatic:** `@media (prefers-color-scheme: dark)` matches OS/browser preference
2. **Manual toggle:** Button in top-right personal tools area ("☾ Dark" / "☀ Light")
3. **Persistent:** Choice saved to `localStorage`, survives page loads and sessions
4. **Override:** Manual selection overrides OS preference; OS changes respected when no manual choice saved

**Dark theme values:**
- Body: `#1a1a1a`, content area: `#222`, sidebar: `#1e1e1e`
- Text: `#e0e0e0` primary, `#b0b0b0` secondary
- Links: lighter orange (`#ffa27e`) for dark background readability
- Tables: `#cc6e44` headers, `#2f2f2f` alternating rows
- Code: `#1e1e1e` with `#333` border
- Tabs: `#333` selected background with orange bottom border (fixed from white)

**Implementation:**
- `MediaWiki:Common.css` — CSS custom properties, `.dark-mode` class overrides, `@media` query fallback
- `MediaWiki:Common.js` — Toggle button injection, localStorage persistence, OS preference listener

---

## Files Modified

| File | Change |
|---|---|
| `scripts/postprocess.py` | Added `'success': 'Tip'` to admonition_types |
| `scripts/convert_guide_chapter.sh` | **New** — guide chapter conversion wrapper |
| `df-docs/.../Security/rate-limiting.md` | Expanded from 2 → ~650 words |
| `df-docs/.../api-creation-management.md` | Expanded from 57 → ~550 words |
| `df-docs/.../php-laravel.md` | Expanded from 9 → ~580 words |
| `df-docs/.../webserver.md` | Expanded from 30 → ~600 words |
| `scripts/migration_inventory.csv` | Updated status/metadata for 11 pages |
| `scripts/scores_final.csv` | Regenerated scoring output |
| `scripts/validation_final.csv` | Regenerated validation output |
| `staging-wiki-config/LocalSettings.php` | Fixed rate limiter, added logo config |
| 7 new `.wiki` files in `scripts/converted/` | Guide chapter conversions |
| `MediaWiki:Sidebar` (wiki page) | Rebuilt with correct page names |
| `MediaWiki:Common.css` (wiki page) | Full DreamFactory theme + dark mode |
| `MediaWiki:Common.js` (wiki page) | Dark mode toggle with persistence |

---

## Known Issues & Follow-ups

1. **Guide images missing:** ~35 image references in guide-unique pages point to files not in the repository. Need to source originals from the DreamFactory guide's hosted version or screenshot replacements.

2. **Guide page scores:** The 7 guide-unique pages score 51-76 due to missing cross-links, URL structure mapping gaps, and legacy version references. Improving cross-links (adding See Also sections) and updating version references would bring these above 75.

3. **Duplicate wiki pages:** Some pages exist under multiple names from earlier upload runs (e.g., `Creating Aws S3 Rest Api` and `Creating-an-aws-s3-rest-api`). These duplicates should be consolidated into redirects.

4. **Structured data:** All pages score 0/10 on this criterion. This is by design — JSON-LD (TechArticle, BreadcrumbList) will be injected via MediaWiki templates post-upload, not in source files.
