from dotenv import load_dotenv
load_dotenv()
import os, re
from pymongo import MongoClient

# Improved whitelist and blacklist
WHITELIST = [
    'real estate','real-estate','realestate','housing','house','home','homes','mortgage','mortgages',
    'property','properties','apartment','apartments','condo','condos','condominium','rent','rental','lease',
    'realtor','broker','listing','listings','sold','sale','closing','open house','homebuilder','builder',
    'construction','building','developer','development','land','lot','multifamily','commercial','residential',
    'office','industrial','retail','affordable housing','housing demand','home prices','price','prices','reits','reit','realty'
]
BLACKLIST = ['sports','entertainment','celebrity','casino','casinos','gaming','betting','healthcare','medical','cybersecurity','smartphone','smartphones','gadgets','movie','music','politics','stock market']

WHITELIST_RE = re.compile(r"\\b(?:" + r"|".join([re.escape(w) for w in WHITELIST]) + r")\\b", flags=re.IGNORECASE)
BLACKLIST_RE = re.compile(r"\\b(?:" + r"|".join([re.escape(w) for w in BLACKLIST]) + r")\\b", flags=re.IGNORECASE)

uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
db_name = os.getenv('DB_NAME', 'trend_radar')
removed_coll = os.getenv('REMOVED_COLLECTION', 'news_articles_removed')
articles_coll = os.getenv('ARTICLES_COLLECTION', 'news_articles')

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
    title = doc.get('title','')
    desc = doc.get('description','')
    content = doc.get('content','')
    text = ' '.join([title, desc, content])
    if WHITELIST_RE.search(text) and not BLACKLIST_RE.search(text):
        # move back
        articles.insert_one(doc)
        removed.delete_one({'_id': doc['_id']})
        restored += 1
    else:
        kept_removed += 1

print('Restored articles:', restored)
print('Remaining in removed:', kept_removed)
print('Articles now in news_articles:', articles.count_documents({}))

print('\nSample restored titles (up to 30):')
for d in articles.find({}, {'title':1}).limit(30):
    print('-', d.get('title'))
