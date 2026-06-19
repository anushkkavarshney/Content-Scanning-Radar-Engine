import sys, os
sys.path.insert(0, os.path.abspath('..'))
from database.mongodb import db
print('news_articles=', db['news_articles'].count_documents({}))
print('news_articles_removed=', db['news_articles_removed'].count_documents({}) if 'news_articles_removed' in db.list_collection_names() else 0)
print('trends=', db['trends'].count_documents({}) if 'trends' in db.list_collection_names() else 0)
