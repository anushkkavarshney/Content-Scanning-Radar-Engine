from dotenv import load_dotenv
load_dotenv()
import os, json, sys
from pymongo import MongoClient
from datetime import datetime

# ensure project root is on sys.path so "src" imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.preprocess import preprocess_documents
from src.embeddings import embed_texts
from src.cluster import cluster_embeddings
from src.scoring import compute_trend_score, recency_weight
from sklearn.feature_extraction.text import TfidfVectorizer
# import naming helpers
from src.trend_engine import _derive_label_from_keywords, _make_summary, _extract_sample_headlines, _top_sources, _map_topic_slug_label, _filter_keywords

# Config
uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
db_name = os.getenv('DB_NAME', 'trend_radar')
articles_coll = os.getenv('ARTICLES_COLLECTION', 'news_articles')
trends_coll_name = os.getenv('TRENDS_COLLECTION', 'trends')

print('Connecting to MongoDB...')
client = MongoClient(uri, serverSelectionTimeoutMS=10000)
client.admin.command('ping')
db = client[db_name]

articles = list(db[articles_coll].find({}))
print('Articles read:', len(articles))

# Filter by real-estate relevance before preprocessing/embeddings
import sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from services.normalizer import validate_real_estate_article

accepted = []
rejected = []
REMOVED_COLLECTION = os.getenv('REMOVED_COLLECTION', 'news_articles_removed')
removed_coll = db[REMOVED_COLLECTION]

for a in articles:
    # validate using strict validator
    res = validate_real_estate_article({'title': a.get('title',''), 'description': a.get('description',''), 'content': a.get('content',''), 'source': a.get('source','')})
    if res.get('accepted'):
        accepted.append((a, res))
    else:
        rejected.append((a, res))
        # move rejected to removed collection (if not already there)
        try:
            doc = dict(a)
            doc['rejection_reason'] = res.get('reason')
            doc['rejection_pos'] = res.get('pos_matches')
            doc['rejection_neg'] = res.get('neg_matches')
            doc['removed_at'] = datetime.utcnow().isoformat() + 'Z'
            removed_coll.insert_one(doc)
            # delete from source articles collection
            db[articles_coll].delete_one({'_id': a.get('_id')})
        except Exception as e:
            print(f"Failed to move rejected article to removed: {e}")

print('Articles Accepted:', len(accepted))
print('Articles Rejected:', len(rejected))

# Build a map of article_id -> validation result for per-article checks later
res_map = {a.get('_id'): r for a, r in accepted}
print('\n--- Sample Rejected Titles (up to 20) ---')
for a, r in rejected[:20]:
    print(f"[{r.get('score')}] {a.get('title','')} -> reason={r.get('reason')} negatives={r.get('neg_matches')}")
print('\n--- Sample Accepted Titles (up to 20) ---')
for a, r in accepted[:20]:
    print(f"[{r.get('score')}] {a.get('title','')} -> positives={r.get('pos_matches')}")

# Continue only with accepted articles
articles = [a for a,_ in accepted]

# Combine fields
texts = [" ".join(filter(None, [a.get('title',''), a.get('description',''), a.get('content','')])) for a in articles]
print('Documents for preprocessing:', len(texts))

cleaned = preprocess_documents(texts)
print('Documents after preprocessing:', len(cleaned))

if not cleaned:
    print('Embeddings generated: 0')
    print('Clusters generated (excluding noise): 0')
    print('Trend documents created: 0')
    trends_coll = db[trends_coll_name]
    trends_coll.delete_many({})
    print('\nFinal counts:')
    print('news_articles =', db[articles_coll].count_documents({}))
    print('trends =', trends_coll.count_documents({}))
    sys.exit(0)

# Embeddings
print('Generating embeddings... (this may take a while if model not cached)')
embeddings = embed_texts(cleaned)
print('Embeddings generated:', len(embeddings))

# Assign categories per article before clustering
CATEGORY_KEYWORDS = {
    'home_sales': set(['home','home sales','sales','housing','closing','transaction','buyer','seller']),
    'mortgage_market': set(['mortgage','mortgages','loan','lending','rates','refinance','credit']),
    'housing_affordability': set(['affordability','affordable','afford','young','parents','starter home','starter','first-time','first time','prices']),
    'residential_construction': set(['construction','homebuilder','builder','development','starts','groundbreaking','permit','housing starts']),
    'rental_multifamily': set(['rental','rent','landlord','tenant','multifamily','apartment','apartments','condo','condominium']),
    'commercial_real_estate': set(['commercial','office','industrial','retail','lease','office space','industrial property']),
    'reit_investment': set(['reit','invit','fund','property investment','investment','asset manager']),
    'proptech': set(['proptech','platform','listing','search','software','ai','machine learning']),
    'industry_m_a': set(['acquire','acquisition','merger','m&a','buy','takeover','bid','acquiring']),
    'misc': set()
}

def detect_categories_for_text(text):
    tx = (text or '').lower()
    cats = set()
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in tx:
                cats.add(cat)
                break
    return cats

CATEGORY_PRIORITY = ['home_sales','mortgage_market','residential_construction','rental_multifamily','housing_affordability','commercial_real_estate','reit_investment','industry_m_a','proptech','misc']
article_categories = []
for i, txt in enumerate(cleaned):
    cats = detect_categories_for_text(txt)
    if not cats:
        # fallback to title-based detection
        cats = detect_categories_for_text(texts[i])
    chosen = 'misc'
    for p in CATEGORY_PRIORITY:
        if p in cats:
            chosen = p
            break
    article_categories.append(chosen)

# Print category distribution before merging
from collections import Counter, defaultdict
cat_dist = Counter(article_categories)
print('\nCategory distribution before clustering:')
for cat, cnt in cat_dist.most_common():
    print(f"  {cat}: {cnt}")

# Do NOT merge small categories; preserve category independence
cat_dist = Counter(article_categories)
print('\nCategory distribution (no merging applied):')
for cat, cnt in cat_dist.most_common():
    print(f"  {cat}: {cnt}")

# Clustering: lower strictness
labels = cluster_embeddings(embeddings, min_cluster_size=2, min_samples=1)
# diagnostics
import numpy as np
labels_arr = np.array(labels)
total_articles = len(labels_arr)
clustered_articles = int((labels_arr != -1).sum())
noise_articles = int((labels_arr == -1).sum())
unique_labels = set([l for l in labels if l != -1])
num_clusters = len(unique_labels)
# articles per cluster
from collections import Counter
cnt = Counter([l for l in labels if l != -1])
articles_per_cluster = dict(cnt)
coverage = (clustered_articles / total_articles) * 100 if total_articles>0 else 0
print('Clusters generated (excluding noise):', num_clusters)
print('Clustering diagnostics:')
print(f'  total_articles = {total_articles}')
print(f'  clustered_articles = {clustered_articles}')
print(f'  noise_articles = {noise_articles}')
print(f'  cluster_count = {num_clusters}')
print(f'  articles_per_cluster = {articles_per_cluster}')
print(f'  coverage_percent = {coverage:.1f}%')

# Build clusters
clusters = {}
for idx, label in enumerate(labels):
    clusters.setdefault(label, []).append(idx)

# compute cluster_count_per_category
cluster_count_per_category = Counter()
for k, idxs in clusters.items():
    if k == -1:
        continue
    # determine dominant category for this cluster
    cats = [article_categories[i] for i in idxs]
    dominant = Counter(cats).most_common(1)[0][0]
    cluster_count_per_category[dominant] += 1

print('\nCluster count per category:')
for cat, cnt in cluster_count_per_category.most_common():
    print(f"  {cat}: {cnt}")

# Build clusters
clusters = {}
for idx, label in enumerate(labels):
    clusters.setdefault(label, []).append(idx)

# Prepare cluster infos
cluster_infos = []
max_article_count = max((len(idxs) for k,idxs in clusters.items() if k!=-1), default=1)
max_source_count = 0
metas = [{'source': a.get('source'), 'published_at': a.get('published_at')} for a in articles]
import numpy as np
for k, idxs in clusters.items():
    if k == -1:
        continue
    cluster_texts = [cleaned[i] for i in idxs]
    try:
        vec = TfidfVectorizer(ngram_range=(1,2), max_features=50)
        X = vec.fit_transform(cluster_texts)
        scores = X.sum(axis=0).A1
        terms = vec.get_feature_names_out()
        ranked = [terms[i] for i in scores.argsort()[::-1]]
        keywords = list(ranked[:12])
    except Exception:
        keywords = []

    # filter noisy keywords
    filtered_keywords = _filter_keywords(keywords)

    article_count = len(idxs)
    sources = set(metas[i]['source'] for i in idxs if metas[i].get('source'))
    source_count = len(sources)
    max_source_count = max(max_source_count, source_count)
    recency_scores = [recency_weight(metas[i].get('published_at')) for i in idxs]
    trend_score = compute_trend_score(article_count, source_count, recency_scores, max_article_count, max_source_count if max_source_count>0 else max(1, source_count))
    topic = " / ".join(filtered_keywords[:3]) if filtered_keywords else (" / ".join(keywords[:3]) if keywords else f"cluster-{k}")
    sample_headlines = _extract_sample_headlines(idxs, articles, limit=5)
    topic_label = _derive_label_from_keywords(filtered_keywords or keywords, [articles[i].get('title','') for i in idxs], sample_headlines)
    centroid = np.mean([embeddings[i] for i in idxs], axis=0)

    # compute mapped slug for protected-merge checks
    slug, mapped_label = _map_topic_slug_label(filtered_keywords or keywords, topic_label, sample_headlines)

    cluster_infos.append({
    'cluster': k,
    'idxs': idxs,
    'keywords': filtered_keywords or keywords,
    'article_count': article_count,
    'source_count': source_count,
    'trend_score': trend_score,
    'topic': topic,
    'topic_label': topic_label,
    'mapped_slug': slug,
    'mapped_label': mapped_label,
    'sample_headlines': sample_headlines,
    'centroid': centroid
    })

# Merge similar clusters (keyword overlap > 60% or centroid cosine > 0.85 or same label)
def cosine(a,b):
    if a is None or b is None:
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na==0 or nb==0:
        return 0.0
    return float(np.dot(a,b) / (na*nb))

protected_slugs = set(['mortgage_market','residential_construction','rental_market','commercial_real_estate','reit_trends','proptech','industry_m_a'])

merged = [False]*len(cluster_infos)
final_clusters = []
for i in range(len(cluster_infos)):
    if merged[i]:
        continue
    base = cluster_infos[i].copy()
    merged[i] = True
    for j in range(i+1, len(cluster_infos)):
        if merged[j]:
            continue
        other = cluster_infos[j]
        # keyword overlap
        s1 = set([k.lower() for k in base['keywords'] if k])
        s2 = set([k.lower() for k in other['keywords'] if k])
        overlap = 0.0
        if s1 or s2:
            overlap = len(s1 & s2) / max(1, len(s1 | s2))
        sim = cosine(base['centroid'], other['centroid'])
        same_label = base['topic_label'].lower() == other['topic_label'].lower()
        should_merge = (overlap > 0.6 or sim > 0.85 or same_label)
        # Prevent merging protected categories into home_sales or each other
        if should_merge:
            bslug = base.get('mapped_slug')
            oslug = other.get('mapped_slug')
            # if one is protected and the other is home_sales, skip merge
            if (bslug in protected_slugs and oslug == 'home_sales') or (oslug in protected_slugs and bslug == 'home_sales'):
                should_merge = False
        if should_merge:
            # merge other into base
            merged[j] = True
            # combine counts
            base['article_count'] += other['article_count']
            base['source_count'] = len(set().union([base.get('source_count',0)], [other.get('source_count',0)]))
            # combine keywords (union, preserve order)
            seen = set([k.lower() for k in base['keywords'] if k])
            combined_kw = base['keywords'][:]
            for kw in other['keywords']:
                if kw and kw.lower() not in seen:
                    combined_kw.append(kw)
                    seen.add(kw.lower())
            base['keywords'] = combined_kw
            # merge headlines
            base['sample_headlines'] = list(dict.fromkeys(base.get('sample_headlines',[]) + other.get('sample_headlines',[])))[:5]
            # merge topic_label: prefer mapped labels (not generated from titles)
            if base['topic_label'] == 'Real Estate Trends' and other['topic_label'] != 'Real Estate Trends':
                base['topic_label'] = other['topic_label']
            # recompute trend_score weighted by article_count
            total_articles = base['article_count']
            base_score = base.get('trend_score',0)
            other_score = other.get('trend_score',0)
            # weighted average
            base['trend_score'] = int((base_score * (base['article_count'] - other['article_count']) + other_score * other['article_count']) / max(1, total_articles))
            # recompute centroid as average of member centroids weighted by member size
            base['centroid'] = (base['centroid'] * (base['article_count'] - other['article_count']) + other['centroid'] * other['article_count']) / max(1, base['article_count'])
    final_clusters.append(base)

# Build final cluster_docs with mapping to machine-friendly topic slugs and human labels
cluster_docs = []
for c in final_clusters:
    # map to slug + nice label
    slug, nice_label = _map_topic_slug_label(c.get('keywords',[]), c.get('topic_label',''), c.get('sample_headlines',[]))
    summary = _make_summary(nice_label, c.get('keywords',[]), c.get('sample_headlines',[]), c.get('article_count',0), c.get('source_count',0))
    cluster_doc = {
        'topic': slug,
        'topic_label': nice_label,
        'summary': summary,
        'trend_score': int(c.get('trend_score',0)),
        'article_count': c.get('article_count',0),
        'source_count': c.get('source_count',0),
        'keywords': c.get('keywords',[]),
        'member_idxs': c.get('idxs', []),
        'member_article_ids': [articles[i].get('_id') for i in c.get('idxs', [])] if c.get('idxs') else [],
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }
    cluster_docs.append(cluster_doc)

print('Trend documents created:', len(cluster_docs))

# Category-based fallback trends: ensure each category with >=3 articles has a candidate
CATEGORY_FALLBACK = {
    'home_sales': ('home_sales','Home Sales Activity'),
    'mortgage_market': ('mortgage_market','Mortgage Lending Trends'),
    'residential_construction': ('residential_construction','Residential Construction Activity'),
    'rental_multifamily': ('rental_market','Rental & Multifamily Market'),
    'housing_affordability': ('housing_affordability','Housing Affordability Challenges'),
    'commercial_real_estate': ('commercial_real_estate','Commercial Real Estate Activity'),
    'reit_investment': ('reit_trends','REIT & Property Investment'),
    'proptech': ('proptech','PropTech Innovation'),
    'industry_m_a': ('industry_m_a','Real Estate Mergers & Acquisitions')
}

# Build category index lists from article_categories
cat_indices = defaultdict(list)
for i, c in enumerate(article_categories):
    cat_indices[c].append(i)

# For each category, create a fallback trend candidate if none exists.
existing_slugs = set(d.get('topic') for d in cluster_docs)
fallback_docs = []
# define trusted sources heuristic for single-article acceptance
TRUSTED_SOURCES = set([s.strip().lower() for s in os.getenv('TRUSTED_SOURCES','reuters,nytimes,bloomberg,wsj,ft,guardian').split(',') if s.strip()])
for cat, idxs in cat_indices.items():
    if cat not in CATEGORY_FALLBACK:
        continue
    slug, label = CATEGORY_FALLBACK[cat]
    if slug in existing_slugs:
        continue
    # If category has only 1 article, apply strict single-article rule
    if len(idxs) == 1:
        i = idxs[0]
        art = articles[i]
        art_id = art.get('_id')
        res = res_map.get(art_id, {})
        source = (art.get('source') or '').strip().lower()
        # require high relevance and trusted source
        if res.get('score',0) >= 90 and (source in TRUSTED_SOURCES) and res.get('pos_matches'):
            chosen_idxs = idxs
        else:
            # skip single-article fallback
            continue
    else:
        chosen_idxs = idxs
    # build cluster doc from these indices
    cluster_texts = [cleaned[i] for i in chosen_idxs]
    try:
        vec = TfidfVectorizer(ngram_range=(1,2), max_features=40)
        X = vec.fit_transform(cluster_texts)
        scores = X.sum(axis=0).A1
        terms = vec.get_feature_names_out()
        ranked = [terms[i] for i in scores.argsort()[::-1]]
        keywords = list(ranked[:12])
    except Exception:
        keywords = []
    filtered_keywords = _filter_keywords(keywords)
    article_count = len(chosen_idxs)
    sources = set(metas[i]['source'] for i in chosen_idxs if metas[i].get('source'))
    source_count = len(sources)
    recency_scores = [recency_weight(metas[i].get('published_at')) for i in chosen_idxs]
    trend_score = compute_trend_score(article_count, source_count, recency_scores, max_article_count, max_source_count if max_source_count>0 else max(1, source_count))
    sample_headlines = _extract_sample_headlines(chosen_idxs, articles, limit=5)
    summary = _make_summary(label, filtered_keywords or keywords, sample_headlines, article_count, source_count)
    doc = {'topic': slug, 'topic_label': label, 'summary': summary, 'trend_score': int(trend_score), 'article_count': article_count, 'source_count': source_count, 'keywords': filtered_keywords, 'member_idxs': chosen_idxs, 'member_article_ids': [articles[i].get('_id') for i in chosen_idxs], 'created_at': datetime.utcnow().isoformat() + 'Z'}
    fallback_docs.append(doc)

# append fallback docs to cluster_docs
if fallback_docs:
    print(f"Adding {len(fallback_docs)} category fallback trend(s)")
    cluster_docs.extend(fallback_docs)

# Finalize cluster_docs: filter small/single-source clusters and insert as-is
print('Initial cluster docs:', len(cluster_docs))
# Acceptance rule: insert if (article_count >=2) OR (source_count >=2)
filtered_docs = [d for d in cluster_docs if (d.get('article_count',0) >=2) or (d.get('source_count',0) >=2)]
print('Clusters after acceptance filter:', len(filtered_docs))
# Split large clusters (>15) using KMeans into sub-trends and map to sub-trend labels
final_docs = []
for d in filtered_docs:
    if d.get('article_count',0) > 15:
        try:
            from sklearn.cluster import KMeans
            idxs = d.get('member_idxs') if d.get('member_idxs') else []
            emb_sub = [embeddings[i] for i in idxs]
            # aim for finer-grained subclusters
            n_sub = min(max(2, len(idxs)//8), 8)
            km = KMeans(n_clusters=n_sub, random_state=42).fit(emb_sub)
            labels_sub = km.labels_
            sub_groups = defaultdict(list)
            for pos, lbl in enumerate(labels_sub):
                sub_groups[lbl].append(idxs[pos])

            # helper to choose subtrend label
            def choose_subtrend_label(keywords, titles):
                kw = set((k or '').lower() for k in (keywords or []))
                txt = ' '.join(titles or []).lower()
                if any('price' in k or 'pricing' in k or 'price' in txt for k in kw):
                    return ('home_prices','Home Prices')
                if any(k in kw for k in ('sale','sales','sold','pending','closing')) or any(w in txt for w in ['home sales','pending home sales']):
                    return ('home_sales','Home Sales')
                if any(k in kw for k in ('mortgage','mortgages','loan','lending','refinance','rates')) or 'mortgage' in txt:
                    return ('mortgage_activity','Mortgage Activity')
                if any(k in kw for k in ('construction','starts','pipeline','permit','development','builder','homebuilder')) or any(w in txt for w in ['housing starts','construction']):
                    # distinguish builder vs supply
                    if any(k in kw for k in ('builder','homebuilder','developer')):
                        return ('builder_activity','Builder Activity')
                    return ('housing_supply','Housing Supply')
                return ('home_sales','Home Sales')

            for grp in sub_groups.values():
                if len(grp) < 3:
                    continue
                cluster_texts = [cleaned_texts[i] for i in grp]
                try:
                    vec = TfidfVectorizer(ngram_range=(1,2), max_features=40)
                    X = vec.fit_transform(cluster_texts)
                    scores = X.sum(axis=0).A1
                    terms = vec.get_feature_names_out()
                    ranked = [terms[i] for i in scores.argsort()[::-1]]
                    keywords = list(ranked[:12])
                except Exception:
                    keywords = []
                filtered_keywords = _filter_keywords(keywords)
                article_count = len(grp)
                sources = set(filtered_meta[i]['source'] for i in grp if filtered_meta[i].get('source'))
                source_count = len(sources)
                # relaxed acceptance for subgroups from a large parent: allow single-source if article_count >=3
                allow_single_source_from_large_parent = True
                if (article_count >=3 and (source_count >=2 or allow_single_source_from_large_parent)) or (article_count >=4 and source_count >=1):
                    slug, label = choose_subtrend_label(filtered_keywords or keywords, [filtered_meta[i]['title'] for i in grp[:5]])
                    summary = _make_summary(label, filtered_keywords or keywords, [filtered_meta[i]['title'] for i in grp[:5]], article_count, source_count)
                    final_docs.append({'topic': slug, 'topic_label': label, 'summary': summary, 'trend_score': int(d.get('trend_score',0)), 'article_count': article_count, 'source_count': source_count, 'keywords': filtered_keywords, 'created_at': datetime.utcnow().isoformat() + 'Z'})
        except Exception:
            final_docs.append(d)
    else:
        final_docs.append(d)

# Diversity safeguard: ensure at least 6 trends by promoting best remaining candidates
if len(final_docs) < 6:
    existing_topics = set(d.get('topic') for d in final_docs)
    pool = [d for d in (cluster_docs + fallback_docs) if d.get('topic') not in existing_topics]
    pool_sorted = sorted(pool, key=lambda d: (-d.get('trend_score',0), -d.get('article_count',0), -d.get('source_count',0)))
    added = 0
    for cand in pool_sorted:
        if len(final_docs) >= 6:
            break
        final_docs.append(cand)
        added += 1
    if added:
        print(f"Diversity safeguard added {added} candidate(s) to reach minimum trends")

# persist to DB: replace current trends with final_docs
print('Final trends to insert:', len(final_docs))
trends_coll = db[trends_coll_name]
trends_coll.delete_many({})
if final_docs:
    trends_coll.insert_many(final_docs)
print('Trend documents inserted:', trends_coll.count_documents({}))

# Show one example
one = trends_coll.find_one(sort=[('trend_score', -1)])
if one:
    one.pop('_id', None)
    print('\nExample trend document:')
    print(json.dumps(one, default=str, indent=2))

print('\nFinal counts:')
print('news_articles =', db[articles_coll].count_documents({}))
print('trends =', trends_coll.count_documents({}))
