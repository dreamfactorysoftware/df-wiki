# Documentation Migration Scripts

Automation scripts for migrating DreamFactory documentation to MediaWiki.

## Prerequisites

```bash
# Install system dependencies
apt-get install pandoc python3 python3-pip

# Install Python dependencies
pip3 install -r requirements.txt
```

## Scripts Overview

### 1. inventory.py - Content Inventory Generator

Scans all documentation sources and generates a tracking spreadsheet.

```bash
python3 inventory.py --output migration_inventory.csv
```

**Output**: CSV file with columns:
- source_path, source_type, title, target_wiki_page
- priority (P0-P3), status, assigned
- word_count, images, links, links_verified
- difficulty, keywords, notes

### 2. batch_convert.sh - Batch Markdown to MediaWiki Converter

Converts all markdown files in a directory to MediaWiki format.

```bash
./batch_convert.sh [source_dir] [output_dir]

# Example: Convert df-docs
./batch_convert.sh ../df-docs/df-docs/docs ./converted
```

### 3. postprocess.py - Pandoc Output Post-Processor

Fixes common Pandoc conversion issues:
- Extracts YAML frontmatter for categories
- Fixes code block syntax highlighting
- Converts internal links to wiki format
- Fixes image references
- Converts Docusaurus admonitions to templates
- Adds categories based on path/keywords

```bash
python3 postprocess.py <wiki_file> [source_md_file]
```

### 4. upload_to_wiki.py - MediaWiki API Uploader

Bulk uploads converted pages to MediaWiki via API.

```bash
python3 upload_to_wiki.py --wiki-url https://wiki.dreamfactory.com \
                          --input-dir ./converted \
                          --dry-run
```

### 5. validate_migration.py - Migration Validator

Validates migrated content:
- Checks for broken internal links
- Verifies images are uploaded
- Compares word counts
- Validates category assignments

```bash
python3 validate_migration.py --wiki-url https://wiki.dreamfactory.com \
                               --inventory migration_inventory.csv
```

### 6. generate_redirects.py - Nginx Redirect Generator

Generates nginx configuration for URL redirects.

```bash
python3 generate_redirects.py --inventory migration_inventory.csv \
                               --output redirect_map.conf
```

## Workflow

1. **Generate inventory**: `python3 inventory.py`
2. **Review and prioritize**: Edit `migration_inventory.csv`
3. **Convert content**: `./batch_convert.sh`
4. **Review conversions**: Check `./converted/` directory
5. **Upload to staging wiki**: `python3 upload_to_wiki.py --dry-run`
6. **Validate migration**: `python3 validate_migration.py`
7. **Generate redirects**: `python3 generate_redirects.py`

### 7. sync_to_wiki.py - GitHub to Wiki Deployment

Syncs markdown documentation from GitHub to MediaWiki with conflict detection.

```bash
# Check for conflicts
python3 sync_to_wiki.py --check-conflicts --wiki-url https://wiki.dreamfactory.com

# Deploy (with environment variables)
export WIKI_URL=https://wiki.dreamfactory.com
export WIKI_USER=BotUser
export WIKI_PASSWORD=secret
python3 sync_to_wiki.py --source ../df-docs/docs --deploy

# Dry run
python3 sync_to_wiki.py --source ../df-docs/docs --deploy --dry-run

# Verify deployment
python3 sync_to_wiki.py --verify
```

### 8. backup_wiki_to_git.py - Wiki to Git Backup

Backs up wiki-editable namespaces (Legacy, FAQ, etc.) to a Git repository.

```bash
# Backup all legacy namespaces
python3 backup_wiki_to_git.py --wiki-url https://wiki.dreamfactory.com \
                               --output ./wiki-backup \
                               --namespaces V2 V3 V4 V5 V6 Legacy

# Backup without committing
python3 backup_wiki_to_git.py --wiki-url https://wiki.dreamfactory.com \
                               --output ./wiki-backup \
                               --no-commit
```

---

## Post-Migration Versioning Control

The scripts support a **hybrid ownership model**:

| Content Type | Edit Location | Sync Direction |
|--------------|---------------|----------------|
| Current docs (7.x) | GitHub | GitHub → Wiki (sync_to_wiki.py) |
| Legacy docs (V2-V6) | Wiki | Wiki → Git (backup_wiki_to_git.py) |

See the full plan for MediaWiki protection configuration and CI/CD setup.

---

## MediaWiki Templates Required

Before migration, create these templates in MediaWiki:

- `Template:Note` - Info/note boxes
- `Template:Warning` - Warning boxes
- `Template:Tip` - Tip boxes
- `Template:VersionBanner` - Version notices
- `Template:V2Doc` through `Template:V6Doc` - Version-specific banners
- `Template:CurrentDoc` - Current version banner
- `Template:VersionSwitcher` - Version navigation

See `/root/.claude/plans/ancient-wobbling-twilight.md` for template code.
