from datetime import datetime
from dateutil import parser

def normalize_article(raw):
    # Ensure required fields and consistent keys
    title = raw.get('title') or ''
    description = raw.get('description') or ''
    content = raw.get('content') or description or ''
    source = raw.get('source') or raw.get('source_name') or 'unknown'
    url = raw.get('url')
    published_raw = raw.get('published_at') or raw.get('published')
    published_at = None
    if published_raw:
        try:
            published_at = parser.parse(published_raw).isoformat()
        except Exception:
            published_at = None
    collected_at = datetime.utcnow().isoformat()
    return {
        'title': title.strip(),
        'description': description.strip(),
        'content': content.strip(),
        'source': source,
        'url': url,
        'published_at': published_at,
        'collected_at': collected_at,
        'category': 'real_estate'
    }
