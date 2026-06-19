from dotenv import load_dotenv
load_dotenv()
import os
import sys
from pymongo import MongoClient
# ensure project root on path so services imports work
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from services.normalizer import compute_relevance_score

client = MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=10000)
db = client[os.getenv('DB_NAME','trend_radar')]
removed = db[os.getenv('REMOVED_COLLECTION','news_articles_removed')]
news = db[os.getenv('ARTICLES_COLLECTION','news_articles')]

cursor = removed.find({})
restored = 0
skipped = 0
for d in cursor:
    combined = ' '.join(filter(None, [d.get('title',''), d.get('description',''), d.get('content','')]))
    score = compute_relevance_score(combined)
    if score >= 70:
        # try insert if url not exists
        try:
            if d.get('url') and news.find_one({'url': d.get('url')}):
                skipped += 1
                continue
            to_insert = d.copy()
            to_insert.pop('_id', None)
            to_insert['real_estate_relevance_score'] = score
            to_insert['category'] = 'real_estate'
            news.insert_one(to_insert)
            restored += 1
        except Exception:
            skipped += 1
    else:
        skipped += 1

print('Restored:', restored)
print('Skipped:', skipped)
