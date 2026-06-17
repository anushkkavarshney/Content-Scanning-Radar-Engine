import os
import feedparser
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
DEFAULT_FEEDS = os.getenv('RSS_FEEDS')
if DEFAULT_FEEDS:
    DEFAULT_FEEDS = [u.strip() for u in DEFAULT_FEEDS.split(',') if u.strip()]
else:
    DEFAULT_FEEDS = [
        'https://www.housingwire.com/feed/',
        'https://www.inman.com/feed/'
    ]

def fetch_rss_feeds():
    articles = []
    for feed_url in DEFAULT_FEEDS:
        try:
            d = feedparser.parse(feed_url)
            for entry in d.entries:
                published = entry.get('published') or entry.get('updated')
                articles.append({
                    'title': entry.get('title'),
                    'description': entry.get('summary'),
                    'content': entry.get('content')[0].value if entry.get('content') else entry.get('summary'),
                    'source': d.feed.get('title') or feed_url,
                    'url': entry.get('link'),
                    'published_at': published
                })
        except Exception:
            continue
    return articles
