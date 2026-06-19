from dotenv import load_dotenv
load_dotenv()
import os, re
from pymongo import MongoClient

WHITELIST = ['real estate','real-estate','realestate','housing','house','home','homes','mortgage','mortgages','property','properties','apartment','apartments','condo','condos','condominium','rent','rental','lease','realtor','broker','listing','listings','sold','sale','closing','open house','homebuilder','builder','construction','building','developer','development','land','lot','multifamily','commercial','residential','office','industrial','retail','affordable housing','housing demand','home prices','price','prices','reits','reit','realty']
WHITELIST_RE = re.compile(r"\\b(?:" + r"|".join([re.escape(w) for w in WHITELIST]) + r")\\b", flags=re.IGNORECASE)

uri = os.getenv('MONGO_URI')
db = os.getenv('DB_NAME','trend_radar')
removed_coll = os.getenv('REMOVED_COLLECTION','news_articles_removed')
client = MongoClient(uri, serverSelectionTimeoutMS=10000)
client.admin.command('ping')
dbobj = client[db]
coll = dbobj[removed_coll]

count=0
for d in coll.find({}).limit(100):
    title = d.get('title','')
    m = WHITELIST_RE.search(title or '')
    print(title, '| match:', bool(m))
    if m:
        print(' matched:', m.group(0))
    count += 1

print('Done sample check')
