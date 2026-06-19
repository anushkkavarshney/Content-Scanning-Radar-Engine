from dotenv import load_dotenv
load_dotenv()
import os
from pymongo import MongoClient

WHITELIST = [
    'real estate','real-estate','realestate','housing','house','home','homes','mortgage','mortgages',
    'property','properties','apartment','apartments','condo','condos','condominium','rent','rental','lease',
    'realtor','broker','listing','listings','sold','sale','closing','open house','homebuilder','builder',
    'construction','building','developer','development','land','lot','multifamily','commercial','residential',
    'office','industrial','retail','affordable housing','housing demand','home prices','price','prices','reits','reit','realty'
]
BLACKLIST = ['sports','entertainment','celebrity','casino','casinos','gaming','betting','healthcare','medical','cybersecurity','smartphone','smartphones','gadgets','movie','music','politics','stock market','ai news','cryptocurrency','crypto']

uri = os.getenv('MONGO_URI')
db_name = os.getenv('DB_NAME','trend_radar')
removed_coll = os.getenv('REMOVED_COLLECTION','news_articles_removed')
articles_coll = os.getenv('ARTICLES_COLLECTION','news_articles')

print('Connecting to MongoDB...', uri)
client = MongoClient(uri, serverSelectionTimeoutMS=10000)
client.admin.command('ping')
db = client[db_name]
removed = db[removed_coll]
articles = db[articles_coll]

total_removed = removed.count_documents({})
print('Total in removed collection:', total_removed)

restored = 0
kept_removed = 0

for doc in removed.find({}):
    title = (doc.get('title') or '')
    desc = (doc.get('description') or '')
    content = (doc.get('content') or '')
    text = ' '.join([title, desc, content]).lower()
    whitelist_match = any(tok in text for tok in WHITELIST)
    blacklist_match = any(tok in text for tok in BLACKLIST)
    if whitelist_match and not blacklist_match:
        try:
            articles.insert_one(doc)
            removed.delete_one({'_id': doc['_id']})
            restored += 1
        except Exception as e:
            # duplicate key or other write issue - skip and keep in removed
            print('insert skipped (duplicate or error):', str(e))
            kept_removed += 1
    else:
        kept_removed += 1

print('Restored articles:', restored)
print('Remaining in removed:', kept_removed)
print('Articles now in news_articles:', articles.count_documents({}))

print('\nSample restored titles (up to 30):')
for d in articles.find({}, {'title':1}).limit(30):
    print('-', d.get('title'))
