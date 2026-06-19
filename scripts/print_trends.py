import sys, os, json
sys.path.insert(0, os.path.abspath('.'))
from database.mongodb import db
if 'trends' not in db.list_collection_names():
    print('No trends collection')
    sys.exit(0)
for t in db['trends'].find({}).sort('trend_score', -1):
    t.pop('_id', None)
    print(json.dumps(t, indent=2, default=str))
    print('---')
