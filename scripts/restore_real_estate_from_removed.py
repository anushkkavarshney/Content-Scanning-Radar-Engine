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

# sample up to 100
sample_size = min(100, total_removed)
if sample_size == 0:
    print('No documents to analyze. Exiting.')
    sys.exit(0)

cursor = list(removed.aggregate([{'$sample':{'size': sample_size}}]))

restored = 0
still_rejected = 0
restored_titles = []
rejected_examples = []
accepted_examples = []

for doc in cursor:
    title = doc.get('title','')
    desc = doc.get('description','') or ''
    content = doc.get('content','') or ''
    combined = ' '.join([title, desc, content])
    score = normalizer.compute_relevance_score(combined)
    # find matches
    strong = [m.group(0) for m in normalizer.STRONG_RE.finditer(combined)]
    black = [m.group(0) for m in normalizer.BLACKLIST_RE.finditer(combined)]
    weak = [m.group(0) for m in normalizer.WHITELIST_RE.finditer(combined)]

    reason = ''
    if black:
        reason = f'BLACKLIST_MATCH: {black}'
        category = 'NOT_REAL_ESTATE'
    elif score >= 70:
        reason = f'SCORE:{score} (>=70)'
        category = 'REAL_ESTATE'
    elif strong:
        reason = f'STRONG_MATCH:{strong} (but score maybe lower)'
        category = 'REAL_ESTATE'
    elif weak and len(set(weak)) >= 2:
        reason = f'WEAK_MATCHES:{list(set(weak))}'
        category = 'REAL_ESTATE'
    else:
        reason = f'SCORE:{score} (low)'
        category = 'NOT_REAL_ESTATE'

    if category == 'REAL_ESTATE':
        # restore to news_articles if not already present
        try:
            if doc.get('url') and news.find_one({'url': doc.get('url')}):
                # already exists
                restored_titles.append(doc.get('title',''))
            else:
                to_insert = doc.copy()
                to_insert.pop('_id', None)
                to_insert['real_estate_relevance_score'] = score
                to_insert['category'] = 'real_estate'
                news.insert_one(to_insert)
                restored += 1
                restored_titles.append(doc.get('title',''))
            accepted_examples.append({'title': title, 'score': score, 'reason': reason})
        except Exception as e:
            still_rejected += 1
            rejected_examples.append({'title': title, 'score': score, 'reason': f'insert_error:{e}'})
    else:
        still_rejected += 1
        rejected_examples.append({'title': title, 'score': score, 'reason': reason})

# Print summary
print('\nAnalysis sample size =', sample_size)
print('Restored from sample =', restored)
print('Still rejected in sample =', still_rejected)

print('\n--- Examples accepted (up to 10) ---')
for ex in accepted_examples[:10]:
    print(json.dumps(ex, ensure_ascii=False))

print('\n--- Examples rejected (up to 10) ---')
for ex in rejected_examples[:10]:
    print(json.dumps(ex, ensure_ascii=False))

# Now show counts for restored and remaining
print('\nNow checking overall collections:')
print('news_articles count =', news.count_documents({}))
print('news_articles_removed count =', removed.count_documents({}))

print('\nRestored titles (up to 50):')
for t in restored_titles[:50]:
    print(t)

print('\nDone.')
