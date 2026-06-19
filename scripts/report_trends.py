import os, json, requests
from dotenv import load_dotenv
load_dotenv()

API_URL = os.getenv('LOCAL_API_URL', 'http://127.0.0.1:8000')
print('Calling POST', API_URL + '/generate_trends')
try:
    resp = requests.post(API_URL + '/generate_trends', timeout=900)
    print('POST status:', resp.status_code)
    try:
        j = resp.json()
        print('Returned trends count:', len(j.get('data', [])))
    except Exception as e:
        print('Failed to parse JSON response:', e)
except Exception as e:
    print('POST failed:', e)

from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()
uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
db_name = os.getenv('DB_NAME', 'trend_radar')
articles_coll = os.getenv('ARTICLES_COLLECTION', 'news_articles')
trends_coll_name = os.getenv('TRENDS_COLLECTION', 'trends')

print('\nConnecting to MongoDB...')
try:
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    client.admin.command('ping')
    db = client[db_name]
    total_articles = db[articles_coll].count_documents({})
    trends_coll = db[trends_coll_name]
    trends_count = trends_coll.count_documents({})
    sum_articles = sum(t.get('article_count', 0) for t in trends_coll.find({}))
    print('Articles in news_articles:', total_articles)
    print('Articles included in trends:', sum_articles)
    print('Number of trends (clusters stored):', trends_count)
    one = trends_coll.find_one(sort=[('trend_score', -1)])
    if one:
        one.pop('_id', None)
        print('\nExample trend document:')
        print(json.dumps(one, default=str, indent=2))
    else:
        print('\nNo trend documents found in trends collection')
except Exception as e:
    print('Mongo check failed:', e)
