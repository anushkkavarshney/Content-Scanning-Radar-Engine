from .normalizer import normalize_article, validate_real_estate_article, SPAM_SOURCE_BLOCKLIST
from database.mongodb import db, news_collection
from difflib import SequenceMatcher
from datetime import datetime
import os

REMOVED_COLLECTION = os.getenv('REMOVED_COLLECTION', 'news_articles_removed')
removed_collection = db[REMOVED_COLLECTION]

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
        # validate using strict validator
        res = validate_real_estate_article({'title': norm.get('title',''), 'description': norm.get('description',''), 'content': norm.get('content',''), 'source': norm.get('source','')})
        if not res.get('accepted'):
            # move to removed collection with reason
            try:
                doc = dict(norm)
                doc['rejection_reason'] = res.get('reason')
                doc['rejection_pos'] = res.get('pos_matches')
                doc['rejection_neg'] = res.get('neg_matches')
                doc['removed_at'] = datetime.utcnow().isoformat() + 'Z'
                removed_collection.insert_one(doc)
            except Exception:
                pass
            continue
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
    inserted = 0
    try:
        for a in articles:
            # assume already normalized
            cat = a.get('category')
            if cat != 'real_estate':
                # move to removed collection with default reason
                try:
                    doc = dict(a)
                    doc['rejection_reason'] = 'category_not_real_estate'
                    doc['removed_at'] = datetime.utcnow().isoformat() + 'Z'
                    removed_collection.insert_one(doc)
                except Exception:
                    pass
                continue
            source = (a.get('source') or '').strip()
            if source and source.lower() in [s.strip().lower() for s in SPAM_SOURCE_BLOCKLIST if s.strip()]:
                print(f"Skipping article from spam source: {source}")
                try:
                    doc = dict(a)
                    doc['rejection_reason'] = 'spam_source'
                    doc['removed_at'] = datetime.utcnow().isoformat() + 'Z'
                    removed_collection.insert_one(doc)
                except Exception:
                    pass
                continue
            try:
                news_collection.insert_one(a)
                inserted += 1
            except Exception:
                continue
        return inserted
    except Exception:
        return 0
