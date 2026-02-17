# DreamFactory Documentation Consolidation - Executive Brief

## Objective
Consolidate 3 documentation sources into a single MediaWiki at wiki.dreamfactory.com.

### Guiding Principles (per team directive)
- **LLM discoverability is a first-class goal.** More focused pages, semantic URLs, and clean MediaWiki markup maximize surface area for both search engines and LLMs.
- **Every page earns its existence.** Minimum 500 words of substantive content, code examples, and cross-links. Stubs get expanded or merged.
- **All content targets v7.4.x.** No legacy platform references (Ubuntu 16.04, macOS 10.11, v2.x APIs) in the main namespace.
- **No AI-resistance signals.** Remove EU Directive 2019/790 robots.txt policy from docs site before redirect cutover.

---

## Sources Overview

| Source | Content | Status |
|--------|---------|--------|
| **df-docs** (Docusaurus) | 65 markdown files | Most current - PRIMARY |
| **Guide** (Hugo) | 28 chapters | Outdated, guide-oriented |
| **MediaWiki** (Existing) | 489 pages (103MB dump) | Legacy 2015-2025 |

**Total inventory**: 582 documentation items

**Note**: Legacy wiki content is NOT directly imported. Instead:
1. Run old wiki in isolated Docker container
2. Review content manually
3. Export selected pages as markdown
4. Commit to Git repository

---

## Key Decisions

### Version Preservation Strategy
- **Main namespace**: Current documentation (7.x+)
- **V2: - V6: namespaces**: Version-specific legacy docs
- **Legacy: namespace**: Pre-v2 or unversioned content

### Content Quality Standards
- **Minimum 500 words** of substantive content per page (code examples count)
- ~30% of existing wiki pages are hub stubs with <100 words — each must be expanded or merged into its parent
- Every page must include code examples where applicable and links to 3-5 related pages
- All main-namespace content must reference **v7.4.x**, current platforms (Ubuntu 24.04, Docker, K8s), and current API endpoints

### URL Structure & Mapping
- Preserve the wiki's semantic URL structure (`/DreamFactory/Features/Database/MySQL`, etc.) — these have backlink equity and match LLM training data
- Guide database chapter (8,000-10,000 words, 35+ code examples) must be **split** into per-database pages:
  - Database overview → `/DreamFactory/Features/Database`
  - MySQL specifics → `/DreamFactory/Features/Database/MySQL`
  - PostgreSQL → `/DreamFactory/Features/Database/PostgreSQL`
  - (and so on for each supported database)
- MCP/AI docs (3 pages from df-docs) map to `/DreamFactory/Features/MCP` and subpages
- All other df-docs content follows the existing wiki hierarchy conventions

### URL Redirect Strategy
- Both `docs.dreamfactory.com` and `guide.dreamfactory.com` redirect to wiki
- 93 specific path redirects generated (nginx + Apache configs ready)
- Catch-all redirects to Main_Page for unmapped URLs
- **Pre-cutover**: Remove `robots.txt` AI training signals (EU Directive 2019/790) from docs site before 301s go live

---

## Timeline (16-18 weeks, part-time)

| Phase | Weeks | Key Activities |
|-------|-------|----------------|
| **1. Preparation** | 1-2 | Staging wiki setup, namespace config, tracking system, **sitemap extension install, structured data extensions** |
| **2. Audit** | 3-4 | Content mapping, identify unique guide content, **flag pages <500 words for expand/merge decision, inventory outdated version references** |
| **3. Legacy Migration** | 4-6 | Move existing wiki to version namespaces |
| **4. Primary Migration** | 6-10 | Convert df-docs (P0-P3 priority order), **split guide database chapter into per-DB pages, map MCP docs to /DreamFactory/Features/MCP/*** |
| **5. Content Quality Pass** | 10-14 | **Expand/merge all stub pages to 500-word minimum, update all main-namespace content to v7.4.x, add cross-links (parent hub + 3-5 related pages per leaf), add structured data markup (JSON-LD) to templates** |
| **6. Validation** | 14-16 | Automated + manual review, **verify word counts, validate structured data, test sitemap** |
| **7. Deployment** | 16-18 | **Remove docs robots.txt AI signals**, production cutover, redirect activation |

> **Note**: Timeline extended from 12-14 to 16-18 weeks to account for the content quality pass (stub expansion, v7.4.x rewrites, cross-linking, structured data). This is the most labor-intensive new requirement.

---

## Priority Content (P0-P1)

**P0 - Critical** (migrate first):
- Introduction / Main Page
- Docker Installation
- Introducing REST and DreamFactory

**P1 - High** (week 2):
- All installation guides (Linux, Windows, Helm, Raspberry Pi)
- Security documentation (RBAC, Auth, OAuth integrations)
- Getting started configuration
- **MCP/AI documentation** (3 pages → `/DreamFactory/Features/MCP/*`)
- **Guide database chapter split** (→ per-database pages under `/DreamFactory/Features/Database/*`)

---

## SEO & Discoverability Enhancements

### Sitemap
- Install MediaWiki sitemap extension (WikiSEO or ManualSitemap) during Phase 1
- Include `lastmod` dates for all pages
- Alternatively, generate a static `sitemap.xml` as part of the deploy workflow

### Structured Data (JSON-LD)
Add via MediaWiki extensions or templates:
- **TechArticle** schema on every content page
- **SoftwareApplication** schema on the main page
- **BreadcrumbList** on every page
- **HowTo** schema on tutorial pages
- **FAQPage** schema where appropriate

> **Implementation note**: JSON-LD structured data is **not** embedded in page content during the migration pipeline. Instead, it will be injected via MediaWiki templates (e.g., `{{TechArticle}}`, `{{BreadcrumbList}}`) after upload. This means `content_score.py` will always report 0/10 for the Structured Data criterion on pre-upload files — this is expected and correct. The templates will be created during Phase 5 (Content Quality Pass) and applied wiki-wide.

### Dense Cross-Linking
- Every leaf page links back to its parent hub page
- Every leaf page links to 3-5 related pages
- Hub pages maintain 25-35 internal links (matching existing wiki pattern)
- Builds the knowledge graph that crawlers and LLMs use for topic relationships

---

## Automation Created

```
scripts/
├── inventory.py          # Content inventory (582 items tracked)
├── batch_convert.sh      # Pandoc batch conversion
├── postprocess.py        # Fix conversion issues + cross-link injection
├── upload_to_wiki.py     # MediaWiki API bulk upload
├── validate_migration.py # Link/content validation + word count check
├── generate_redirects.py # Nginx/Apache configs
├── migration_inventory.csv
└── redirect_configs/     # Ready-to-deploy configs
    ├── docs-dreamfactory-com.nginx.conf
    ├── guide-dreamfactory-com.nginx.conf
    └── redirect_map.csv
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Data loss | Backups at each phase, 3-level rollback |
| Broken links (SEO) | 93 specific redirects + monitoring |
| Legacy inaccessible | Dedicated version namespaces with banners |
| Timeline slip | Part-time adjusted, automation heavy |
| Stub pages hurt SEO/LLM ranking | 500-word minimum enforced, word count validation in pipeline |
| Outdated content erodes trust | v7.4.x rewrite pass before go-live, version audit in Phase 2 |
| AI training opt-out carries forward | Remove docs robots.txt directive pre-cutover (Phase 7) |
| Missing sitemap/structured data | Extensions installed in Phase 1, validated in Phase 6 |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| df-docs migrated | 65/65 (100%) |
| Guide unique content | 8/8 (100%) |
| Broken links | 0 |
| Pages below 500-word minimum | 0 |
| Pages with outdated version refs (pre-7.4.x) | 0 in main namespace |
| Leaf pages with <3 cross-links | 0 |
| Sitemap.xml present and valid | Yes |
| Structured data (JSON-LD) on all content pages | Yes |
| User satisfaction (30 days) | >80% |

---

## Prerequisites Before Starting

1. [ ] Staging MediaWiki instance available
2. [ ] Admin access to wiki.dreamfactory.com
3. [ ] DNS control for docs/guide subdomains
4. [ ] Pandoc installed (`apt-get install pandoc`)
5. [ ] Python dependencies (`pip install -r requirements.txt`)
6. [ ] MediaWiki sitemap extension selected and ready (WikiSEO or ManualSitemap)
7. [ ] MediaWiki JSON-LD / structured data extension selected
8. [ ] Access to docs.dreamfactory.com robots.txt for pre-cutover cleanup

---

## Quick Start Commands

```bash
cd /root/df-bug-squasher/documentation-consolidation

# 1. Start legacy wiki in Docker (for content review)
docker-compose -f docker-compose.legacy-wiki.yml up -d
# Access at http://localhost:8081

# 2. Generate legacy page inventory
python3 scripts/extract_legacy_pages.py --wiki-url http://localhost:8081 --list-only

# 3. Review inventory, mark pages as MIGRATE/SKIP in CSV

# 4. Export selected pages as markdown
python3 scripts/extract_legacy_pages.py \
    --wiki-url http://localhost:8081 \
    --inventory legacy_page_inventory.csv \
    --filter-status MIGRATE \
    --output ./legacy-content/

# 5. Shutdown legacy wiki when done
docker-compose -f docker-compose.legacy-wiki.yml down -v
```

### df-docs Migration
```bash
cd scripts

# Test conversion (requires pandoc)
./batch_convert.sh ../df-docs/df-docs/docs ./converted

# Dry-run upload
python3 upload_to_wiki.py --wiki-url https://wiki.dreamfactory.com --dry-run
```

---

---

## Post-Migration: Versioning Control

### The Problem
Multiple editing sources (GitHub + wiki direct editing) cause sync conflicts.

### Solution: Git as Single Source of Truth

**All edits happen in Git. MediaWiki is read-only display.**

| Aspect | Approach |
|--------|----------|
| Source of truth | GitHub repository |
| Editing | Git only (PRs) |
| MediaWiki role | Read-only display |
| Wiki editing | Disabled |

### Repository Structure
```
dreamfactory-docs/
├── docs/           # Current 7.x documentation
├── legacy/
│   ├── v2/ - v6/   # Version-specific legacy docs
├── .github/workflows/deploy-to-wiki.yml
└── CONTRIBUTING.md
```

### Single Unified Workflow (Everyone)
```
Edit markdown → Submit PR → Review → Merge → Auto-deploy to wiki
```

### Quick Edits (No Git Required)
1. Find file on GitHub.com
2. Click pencil icon (Edit)
3. Make changes in browser
4. Click "Propose changes" → Creates PR automatically

### Benefits
- No sync conflicts (single source of truth)
- Full version history with Git
- Code review for all changes
- Easy rollback if needed

---

## Full Plan Reference
- Staging wiki setup plan: `/root/.claude/plans/gentle-coalescing-alpaca.md`
- Team directive (SEO/LLM/content quality): `/root/wikimigration/guidance.md`
