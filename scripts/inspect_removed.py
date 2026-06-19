from dotenv import load_dotenv
load_dotenv()
import os, json
from pymongo import MongoClient

uri = os.getenv('MONGO_URI')
db = os.getenv('DB_NAME','trend_radar')
removed = os.getenv('REMOVED_COLLECTION','news_articles_removed')

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
client.admin.command('ping')
dbobj = client[db]
coll = dbobj[removed]

print('Total removed:', coll.count_documents({}))
print('\nSample titles and categories:')
for d in coll.find({}, {'title':1, 'category':1}).limit(20):
    print('-', d.get('title'), ' | category:', d.get('category'))
