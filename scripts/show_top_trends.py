import os, json
from dotenv import load_dotenv
load_dotenv()
from pymongo import MongoClient

uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
db_name = os.getenv('DB_NAME', 'trend_radar')
trends_coll = os.getenv('TRENDS_COLLECTION', 'trends')

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
client.admin.command('ping')
db = client[db_name]

trends = list(db[trends_coll].find({}).sort('trend_score', -1).limit(10))
print('Top trends:')
for t in trends:
    t.pop('_id', None)
    print(json.dumps({
        'topic': t.get('topic'),
        'trend_score': t.get('trend_score'),
        'article_count': t.get('article_count'),
        'source_count': t.get('source_count'),
        'keywords': t.get('keywords'),
        'summary': t.get('summary')
    }, indent=2, default=str))
    print('-' * 40)
