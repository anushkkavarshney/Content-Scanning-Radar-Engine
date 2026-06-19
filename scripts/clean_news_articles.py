from dotenv import load_dotenv
load_dotenv()
import os, re, sys
from pymongo import MongoClient

# Config: whitelist and blacklist (configurable via env overrides)
WHITELIST = os.getenv('RE_WHITELIST', "real estate|real-estate|housing|housing market|mortgage|property|homebuilder|home sales|rental market|commercial real estate|residential real estate|construction|land development|property investment|housing demand|home prices|affordable housing|reits|reit|real estate investment trust|office market|industrial property|multifamily").split('|')
BLACKLIST = os.getenv('RE_BLACKLIST', "sports|entertainment|celebrity|gaming|casino|casinos|betting|healthcare|medical|cybersecurity|smartphone|smartphones|gadgets|movie|music|politics|stock market|ai news|general ai|technology").split('|')

# compile regex
WHITELIST_RE = re.compile(r"\\b(?:" + r"|".join([re.escape(w.strip()) for w in WHITELIST if w.strip()]) + r")\\b", flags=re.IGNORECASE)
BLACKLIST_RE = re.compile(r"\\b(?:" + r"|".join([re.escape(w.strip()) for w in BLACKLIST if w.strip()]) + r")\\b", flags=re.IGNORECASE)

uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
db_name = os.getenv('DB_NAME', 'trend_radar')
articles_coll = os.getenv('ARTICLES_COLLECTION', 'news_articles')
removed_coll = os.getenv('REMOVED_COLLECTION', 'news_articles_removed')

print('Connecting to MongoDB...', uri)
client = MongoClient(uri, serverSelectionTimeoutMS=10000)
client.admin.command('ping')
db = client[db_name]
coll = db[articles_coll]
removed = db[removed_coll]

total = coll.count_documents({})
print('Total articles before cleanup:', total)

cursor = coll.find({})
removed_count = 0
kept_count = 0

for doc in cursor:
    title = (doc.get('title') or '')
    desc = (doc.get('description') or '')
    content = (doc.get('content') or '')
    text = ' '.join([title, desc, content])
    # apply whitelist: must match at least one whitelist term
    if WHITELIST_RE.search(text):
        kept_count += 1
        continue
    else:
        # move to removed collection for safety
        removed.insert_one(doc)
        coll.delete_one({'_id': doc['_id']})
        removed_count += 1

print('Articles removed:', removed_count)
print('Articles remaining:', coll.count_documents({}))

# show 30 sample titles remaining
print('\nSample remaining titles (up to 30):')
for d in coll.find({}, {'title':1}).limit(30):
    print('-', d.get('title'))

# summary
print('\nDone. Moved non-real-estate articles to collection:', removed_coll)
