from dotenv import load_dotenv
load_dotenv()
import os
from pymongo import MongoClient

uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
db_name = os.getenv('DB_NAME', 'trend_radar')
articles_coll = os.getenv('ARTICLES_COLLECTION', 'news_articles')

print('Testing MongoDB connection...')
try:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client[db_name]
    count = db[articles_coll].count_documents({})
    print('OK: connected to', uri)
    print('DB:', db_name)
    print('Collection:', articles_coll)
    print('Articles count:', count)
except Exception as e:
    print('ERROR:', str(e))
