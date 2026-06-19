from dotenv import load_dotenv
load_dotenv()
import os, sys, json
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pymongo import MongoClient
from services import normalizer

uri = os.getenv('MONGO_URI')
db_name = os.getenv('DB_NAME','trend_radar')
removed_coll = os.getenv('REMOVED_COLLECTION','news_articles_removed')
articles_coll = os.getenv('ARTICLES_COLLECTION','news_articles')

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
db = client[db_name]
removed = db[removed_coll]
news = db[articles_coll]

total_removed = removed.count_documents({})
print('Total documents in removed collection =', total_removed)

# sample up to 500 (to increase chance of matches)
sample_size = min(500, total_removed)
if sample_size == 0:
    print('No documents to analyze. Exiting.')
    sys.exit(0)

cursor = list(removed.aggregate([{'$sample':{'size': sample_size}}]))

restored = 0
still_rejected = 0
restored_entries = []

for doc in cursor:
    title = doc.get('title','')
    desc = doc.get('description','') or ''
    content = doc.get('content','') or ''
    combined = ' '.join([title, desc, content])
    score = normalizer.compute_relevance_score(combined)
    strong_matches = [m.group(0) for m in normalizer.STRONG_RE.finditer(combined)]
    weak_matches = [m.group(0) for m in normalizer.WHITELIST_RE.finditer(combined)]
    black_matches = [m.group(0) for m in normalizer.BLACKLIST_RE.finditer(combined)]

    reason = ''
    accept = False
    if black_matches:
        accept = False
        reason = f'BLACKLIST_MATCH:{black_matches}'
    elif score >= 60:
        accept = True
        reason = f'SCORE:{score}'
    elif strong_matches:
        accept = True
        reason = f'STRONG_MATCH:{strong_matches}'
    elif len(set(weak_matches)) >= 2:
        accept = True
        reason = f'WEAK_MATCHES:{list(set(weak_matches))}'
    else:
        accept = False
        reason = f'SCORE:{score}'

    if accept:
        try:
            if doc.get('url') and news.find_one({'url': doc.get('url')}):
                continue
            to_insert = doc.copy()
            to_insert.pop('_id', None)
            to_insert['real_estate_relevance_score'] = score
            to_insert['category'] = 'real_estate'
            to_insert['restore_reason'] = reason
            news.insert_one(to_insert)
            restored += 1
            restored_entries.append({'title': title, 'score': score, 'reason': reason})
        except Exception:
            still_rejected += 1
    else:
        still_rejected += 1

print('Restored from sample =', restored)
print('Still rejected in sample =', still_rejected)

print('\n--- Restored titles (up to 50) ---')
for e in restored_entries[:50]:
    print(json.dumps(e, ensure_ascii=False))

if restored < 50:
    print('\nFewer than 50 restored; showing 100 random removed titles with classification')
    cursor2 = list(removed.aggregate([{'$sample':{'size':100}}]))
    for d in cursor2:
        title = d.get('title','')
        combined = ' '.join([d.get('title','') or '', d.get('description','') or '', d.get('content','') or ''])
        score = normalizer.compute_relevance_score(combined)
        strong_matches = [m.group(0) for m in normalizer.STRONG_RE.finditer(combined)]
        weak_matches = [m.group(0) for m in normalizer.WHITELIST_RE.finditer(combined)]
        black_matches = [m.group(0) for m in normalizer.BLACKLIST_RE.finditer(combined)]
        category = 'REAL_ESTATE' if (score>=60 or strong_matches or len(set(weak_matches))>=2) and not black_matches else 'NOT_REAL_ESTATE'
        reason = ''
        if black_matches:
            reason = f'BLACKLIST_MATCH:{black_matches}'
        elif score>=60:
            reason = f'SCORE:{score}'
        elif strong_matches:
            reason = f'STRONG_MATCH:{strong_matches}'
        elif len(set(weak_matches))>=2:
            reason = f'WEAK_MATCHES:{list(set(weak_matches))}'
        else:
            reason = f'SCORE:{score}'
        print(json.dumps({'title': title, 'category': category, 'score': score, 'reason': reason}, ensure_ascii=False))

print('\nDone.')
