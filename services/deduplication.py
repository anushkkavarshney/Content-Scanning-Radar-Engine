from .normalizer import normalize_article
from database.mongodb import news_collection
from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.9

def is_similar(a, b):
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD

def is_duplicate(article):
    # Check URL exact
    url = article.get('url')
    if url and news_collection.find_one({'url': url}):
        return True
    # Check exact title
    title = article.get('title')
    if title and news_collection.find_one({'title': title}):
        return True
    # Check similar titles
    if title:
        cursor = news_collection.find({}, {'title': 1}).limit(200)
        for doc in cursor:
            if is_similar(title, doc.get('title', '')):
                return True
    return False

def remove_duplicates(articles):
    unique = []
    seen_urls = set()
    seen_titles = []
    for raw in articles:
        norm = normalize_article(raw)
        if not norm.get('url') and not norm.get('title'):
            continue
        if norm.get('url') in seen_urls:
            continue
        duplicate = is_duplicate(norm)
        if duplicate:
            continue
        seen_urls.add(norm.get('url'))
        seen_titles.append(norm.get('title'))
        unique.append(norm)
    return unique

def save_articles_bulk(articles):
    if not articles:
        return 0
    try:
        for a in articles:
            try:
                news_collection.insert_one(a)
            except Exception:
                continue
        return len(articles)
    except Exception:
        return 0
