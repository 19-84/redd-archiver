# Jinja2 Templates for Redd-Archiver

This directory contains the new Jinja2-based template system for generating HTML archives.

## Directory Structure

```
templates_jinja2/
├── base/               # Master layouts and base templates
│   └── base.html       # Main layout with blocks (header, content, footer)
├── components/         # Reusable UI components
│   ├── navigation.html # Site navigation bar
│   ├── footer.html     # Site footer
│   └── pagination.html # Pagination controls
├── pages/              # Full page templates
│   ├── index.html      # Dashboard/homepage
│   ├── subreddit.html  # Subreddit post listings
│   ├── link.html       # Individual post pages
│   ├── user.html       # User profile pages
│   └── search.html     # Search pages
└── macros/             # Reusable template functions (macros)
    ├── reddit_macros.html  # Reddit-specific components
    └── seo_macros.html     # SEO meta tag generators
```

## Template Inheritance

Templates use Jinja2's inheritance system:

1. **Base Template** (`base/base.html`) - Defines overall HTML structure
2. **Page Templates** (`pages/*.html`) - Extend base and fill in content blocks
3. **Components** (`components/*.html`) - Included in pages for modularity
4. **Macros** (`macros/*.html`) - Imported and called as functions

## Example Usage

### Extending Base Template

```jinja2
{% extends "base/base.html" %}

{% block title %}r/{{ subreddit }} Archive{% endblock %}

{% block content %}
<h1>Posts from r/{{ subreddit }}</h1>
{% for post in posts %}
  {% include 'components/post_card.html' %}
{% endfor %}
{% endblock %}
```

### Using Macros

```jinja2
{% from 'macros/reddit_macros.html' import user_link, score_badge %}

<p>
  {{ score_badge(post.score, score_ranges) }}
  Posted by {{ user_link(post.author) }}
</p>
```

## Custom Filters

Available custom filters (defined in `html_modules/jinja_filters.py`):

- `reddit_date` - Format Unix timestamp as readable date
- `format_number` - Add thousands separators (1,234)
- `score_class` - Get badge CSS class based on score percentiles
- `truncate_smart` - Truncate text at word boundaries
- `date_tooltip` - Generate full date/time hover tooltip
- `author_tooltip` - Generate author account age tooltip
- `pluralize` - Return singular/plural suffix
- `extract_domain` - Extract domain from URL

## Usage

The Jinja2 templates in this directory are the primary template system for Redd-Archiver and are always used during HTML generation.

## Development

To test template changes:

```bash
# Clear bytecode cache to force recompilation
python -c "from html_modules.jinja_env import clear_bytecode_cache; clear_bytecode_cache()"

# Test with sample data
python reddarc.py /test/data/ --output test-output/
```

## Documentation

- **Project README**: `README.md`
- **Jinja2 Docs**: https://jinja.palletsprojects.com/
