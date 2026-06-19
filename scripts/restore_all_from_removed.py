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

cursor = removed.find({})
restored = 0
skipped = 0
restored_list = []
rejected_list = []

for doc in cursor:
    title = doc.get('title','')
    desc = doc.get('description','') or ''
    content = doc.get('content','') or ''
    combined = ' '.join([title, desc, content])
    score = normalizer.compute_relevance_score(combined)
    strong_matches = [m.group(0) for m in normalizer.STRONG_RE.finditer(combined)]
    weak_matches = [m.group(0) for m in normalizer.WHITELIST_RE.finditer(combined)]
    black_matches = [m.group(0) for m in normalizer.BLACKLIST_RE.finditer(combined)]

    accept = False
    reason = ''
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
                skipped += 1
                continue
            to_insert = doc.copy()
            to_insert.pop('_id', None)
            to_insert['real_estate_relevance_score'] = score
            to_insert['category'] = 'real_estate'
            to_insert['restore_reason'] = reason
            news.insert_one(to_insert)
            restored += 1
            restored_list.append({'title': title, 'score': score, 'reason': reason})
        except Exception as e:
            skipped += 1
            rejected_list.append({'title': title, 'score': score, 'reason': f'insert_error:{e}'})
    else:
        rejected_list.append({'title': title, 'score': score, 'reason': reason})

print('Restored total =', restored)
print('Still rejected total in removed =', len(rejected_list))

print('\n--- Restored titles (up to 50) ---')
for e in restored_list[:50]:
    print(json.dumps(e, ensure_ascii=False))

print('\nDone.')
