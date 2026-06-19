from dotenv import load_dotenv
load_dotenv()
import os,json
from pymongo import MongoClient
from collections import Counter

client=MongoClient(os.getenv('MONGO_URI'), serverSelectionTimeoutMS=10000)
db=client[os.getenv('DB_NAME','trend_radar')]
trends=list(db[os.getenv('TRENDS_COLLECTION','trends')].find())
labels=[t.get('topic_label') for t in trends]
cnt=Counter(labels)
print('Trends in DB:', len(trends))
print('Duplicate labels:')
has_dup=False
for label,count in cnt.items():
    if count>1:
        print(f"{label}: {count}")
        has_dup=True
if not has_dup:
    print('No duplicate labels detected')
print('\nAll trend documents:')
for t in sorted(trends, key=lambda x: x.get('trend_score',0), reverse=True):
    t.pop('_id', None)
    print(json.dumps(t, default=str))
