# MediaWiki Templates for DreamFactory Documentation

These templates should be imported into MediaWiki before migrating documentation content.

## Templates Included

### Admonition Templates
- **Template:Note** - Blue info box for notes
- **Template:Warning** - Yellow warning box for cautions
- **Template:Tip** - Green tip box for helpful suggestions

### Version Templates
- **Template:VersionBanner** - Base template for version notices (used by V*Doc templates)
- **Template:V2Doc** - Banner for DreamFactory 2.x documentation
- **Template:V3Doc** - Banner for DreamFactory 3.x documentation
- **Template:V4Doc** - Banner for DreamFactory 4.x documentation
- **Template:V5Doc** - Banner for DreamFactory 5.x documentation
- **Template:V6Doc** - Banner for DreamFactory 6.x documentation
- **Template:CurrentDoc** - Banner for current (7.x) documentation
- **Template:VersionSwitcher** - Navigation box for pages that exist in multiple versions

## Installation

### Manual Installation
1. Go to your MediaWiki's Special:Import page (or create pages manually)
2. Create each template as `Template:TemplateName` (e.g., `Template:Note`)
3. Copy the content from the corresponding .wiki file

### Using upload_to_wiki.py
```bash
cd /documentation-consolidation/scripts

# Upload all templates
for template in mediawiki_templates/*.wiki; do
    page_name="Template:$(basename ${template%.wiki} | sed 's/Template_//')"
    python3 upload_to_wiki.py --wiki-url https://wiki.dreamfactory.com \
        --single-page "$template" \
        --username YOUR_USER --password YOUR_PASS
done
```

## Usage Examples

### Admonitions
```mediawiki
{{Note|This is important information.}}
{{Warning|Be careful when doing this.}}
{{Tip|Here's a helpful suggestion.}}
```

### Version Banners
```mediawiki
{{CurrentDoc}}         <!-- For current 7.x documentation -->
{{V6Doc}}              <!-- For 6.x documentation -->
{{V5Doc}}              <!-- For 5.x documentation -->
```

### Version Switcher
```mediawiki
{{VersionSwitcher|page=Docker_Installation}}
```
This creates a navigation box linking to the same page across all version namespaces.

## Color Scheme

| Version | Background | Border |
|---------|------------|--------|
| 2.x | #ffebee (light red) | #ef5350 (red) |
| 3.x | #fff3cd (light yellow) | #ffc107 (amber) |
| 4.x | #e8f5e9 (light green) | #4caf50 (green) |
| 5.x | #e3f2fd (light blue) | #2196f3 (blue) |
| 6.x | #f3e5f5 (light purple) | #ab47bc (purple) |
| 7.x (Current) | #e8f5e9 (light green) | #4caf50 (green) |
