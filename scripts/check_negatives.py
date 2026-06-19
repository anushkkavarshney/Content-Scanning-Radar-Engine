import sys, os, re
sys.path.insert(0, os.path.abspath('.'))
from database.mongodb import db
coll = db['news_articles']
negatives = ['football','soccer','nba','nfl','bitcoin','ethereum','crypto','token','blockchain','casino','free spins','igaming','betting','medical','hospital','clinical','radiology','cybersecurity','malware','ransomware','software','cloud']
# use word-boundary regex for safety

found = []
for n in negatives:
    cursor = coll.find({'$or':[{'title': {'$regex': n, '$options': 'i'}},{'description': {'$regex': n, '$options': 'i'}},{'content': {'$regex': n, '$options': 'i'}}]}, limit=5)
    for d in cursor:
        found.append((n, d.get('title','')[:200], d.get('source','')))

print('Negative matches found in news_articles (up to 5 per negative term):')
for n,title,src in found:
    print(f"- term={n} title={title!r} source={src}")
if not found:
    print('None')
