from dotenv import load_dotenv
load_dotenv()
import os, sys, json, re
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pymongo import MongoClient
from services import normalizer

uri = os.getenv('MONGO_URI')
db_name = os.getenv('DB_NAME','trend_radar')
articles_coll = os.getenv('ARTICLES_COLLECTION','news_articles')
removed_coll = os.getenv('REMOVED_COLLECTION','news_articles_removed')

client = MongoClient(uri, serverSelectionTimeoutMS=10000)
db = client[db_name]
news = db[articles_coll]
removed = db[removed_coll]

# Context phrases that indicate real-estate context
CONTEXT_PHRASES = [
    'housing market', 'mortgage lending', 'mortgage', 'home sales', 'residential development',
    'residential development', 'commercial real estate', 'rental market', 'rental', 'rentals', 'land acquisition',
    'construction activity', 'construction', 'reit', 'property investment', 'investment property',
    'homebuilder', 'home builders', 'builder', 'developers', 'land development', 'office market', 'office vacancy',
    'multifamily', 'apartment', 'apartments', 'condo', 'condominium', 'housing demand', 'home prices'
]

# Incidental phrases that should NOT count as real-estate context
INCIDENTAL = [
    r'home care', r'homework', r'care home', r'commercial disputes?', r'house democrat', r'caregiver',
    r'clinical trial', r'medical research', r'crypto', r'bitcoin', r'aws outage', r'auto', r'electric vehicle', r'ev\b'
]

CONTEXT_RE = re.compile(r"\b(?:" + r"|".join([re.escape(p) for p in CONTEXT_PHRASES]) + r")\b", flags=re.IGNORECASE)
INCIDENTAL_RE = re.compile(r"\b(?:" + r"|".join(INCIDENTAL) + r")\b", flags=re.IGNORECASE)

# Load all current articles
docs = list(news.find({}))
before = len(docs)
removed_count = 0
kept = []
removed_examples = []

for d in docs:
    title = (d.get('title') or '')
    desc = (d.get('description') or '')
    content = (d.get('content') or '')
    combined = ' '.join([title, desc, content])
    # Stage A: keyword relevance
    score = normalizer.compute_relevance_score(combined)
    has_keyword = score >= 60 or bool(list(normalizer.STRONG_RE.finditer(combined))) or len(set([m.group(0).lower() for m in normalizer.WHITELIST_RE.finditer(combined)]))>=2
    # Stage B: context match
    has_context = bool(CONTEXT_RE.search(combined)) and not bool(INCIDENTAL_RE.search(combined))
    if has_keyword and has_context:
        kept.append(d)
    else:
        # move to removed with reason
        reason = {
            'score': score,
            'has_keyword': has_keyword,
            'has_context': has_context,
            'keyword_matches': list(set([m.group(0) for m in normalizer.WHITELIST_RE.finditer(combined)])),
            'strong_matches': list(set([m.group(0) for m in normalizer.STRONG_RE.finditer(combined)])),
            'context_matches': CONTEXT_RE.findall(combined),
            'incidental_matches': INCIDENTAL_RE.findall(combined)
        }
        to_move = d.copy()
        to_move.pop('_id', None)
        to_move['second_stage_removed'] = True
        to_move['second_stage_reason'] = reason
        removed.insert_one(to_move)
        news.delete_one({'_id': d.get('_id')})
        removed_count += 1
        removed_examples.append({'title': title, 'reason': reason})

remaining = len(kept)
print('Articles Before Validation:', before)
print('Articles Removed:', removed_count)
print('Articles Remaining:', remaining)

print('\n--- 50 Final Accepted Titles ---')
for d in kept[:50]:
    print(d.get('title',''))

print('\n--- Examples Removed (up to 10) ---')
for ex in removed_examples[:10]:
    print(json.dumps(ex, ensure_ascii=False))

print('\nDone.')
