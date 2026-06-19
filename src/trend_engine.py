import logging
from datetime import datetime
from collections import defaultdict, Counter
from pymongo import ASCENDING, DESCENDING
from sklearn.feature_extraction.text import TfidfVectorizer
import re

from .mongo_client import get_db
from .preprocess import preprocess_documents
from .embeddings import embed_texts
from .cluster import cluster_embeddings
from .scoring import compute_trend_score, recency_weight
from .config import TRENDS_COLLECTION, ARTICLES_COLLECTION

logger = logging.getLogger("trend_engine")

# Custom generic keyword blacklist to ignore when naming
# noisy tokens to drop from naming
GENERIC_KEYWORDS = set(["year","new","company","said","market","chars","article","news","today","report","reports","2026","2025","update","updates","href","nbsp","noscript","amp","html","div","span","script","li","rs","ft","parents","pending","third","across","strong","record","latest","source","real","press","release","announced","million","group","services","business","technology"]) 
DIRECTION_WORDS = {
    'increase': ['increase','increases','rise','rises','up','surge','surges','grow','grows','growth','boost','rise'],
    'decrease': ['decrease','decreases','decline','declines','down','drop','drops','fall','falls','slump','slowdown','slow','slows']
}


def _filter_keywords(keywords):
    """Return cleaned, deduplicated keyword list suitable for naming and summaries."""
    cleaned = []
    # tokens to always drop
    DROP_TOKENS = set(['href','nbsp','noscript','amp','html','div','span','script','iframe','style','svg'])
    DOMAIN_TOKENS = set(['housingwire','reuters','bloomberg','guardian','ft','nyt','nytimes','wsj','ap'])

    for k in keywords:
        if not k:
            continue
        kl = k.lower().strip()
        # remove generic or artifact tokens
        if kl in GENERIC_KEYWORDS or kl in DROP_TOKENS or kl in DOMAIN_TOKENS:
            continue
        # drop very short or numeric tokens
        if len(kl) <= 2:
            continue
        if any(ch.isdigit() for ch in kl):
            continue
        # drop urls / domains
        if 'http' in kl or 'href' in kl or 'www' in kl:
            continue
        # must contain alphabetic char
        if not any(c.isalpha() for c in kl):
            continue
        cleaned.append(kl)

    # dedupe while preserving order
    seen = set(); out = []
    for c in cleaned:
        if c not in seen:
            out.append(c); seen.add(c)
    return out


def _extract_sample_headlines(indices, articles, limit=5):
    heads = []
    for i in indices[:limit]:
        title = articles[i].get('title') or ''
        if title:
            heads.append(title)
    return heads


def _top_sources(indices, meta, limit=5):
    sources = [meta[i].get('source') for i in indices if meta[i].get('source')]
    cnt = Counter(sources)
    return [s for s,_ in cnt.most_common(limit)]


def _detect_direction(titles):
    text = ' '.join(titles).lower()
    for k, vocab in DIRECTION_WORDS.items():
        for w in vocab:
            if re.search(r'\b'+re.escape(w)+r'\b', text):
                return 'increase' if k=='increase' else 'decrease'
    return None


def _generate_topic_name(keywords, titles):
    """Generate a human-friendly topic name from keywords + titles."""
    fk = _filter_keywords([k.lower() for k in (keywords or [])])
    direction = _detect_direction(titles)

    def clean(k):
        return k.replace('_',' ').strip().title()

    # specific combination rules (more readable than naive concatenation)
    kw_set = set(fk)

    # Home Sales
    if ('sales' in kw_set or 'home sales' in kw_set) and ('home' in kw_set or 'housing' in kw_set):
        base = 'Home Sales Activity'
        if direction == 'increase':
            return f"{base} — Growth"
        if direction == 'decrease':
            return f"{base} — Slowdown"
        return base

    # Mortgage lending
    if any(k.startswith('mortg') for k in kw_set):
        base = 'Mortgage Lending Trends'
        if direction == 'increase':
            return f"{base} — Growth"
        if direction == 'decrease':
            return f"{base} — Tightening"
        return base

    # Affordable housing finance
    if 'affordable' in kw_set and ('fund' in kw_set or 'bank' in kw_set or 'finance' in kw_set):
        return 'Affordable Housing Finance'

    # Indian investment localization
    if 'india' in kw_set and 'investment' in kw_set:
        return 'Indian Real Estate Investment Growth'

    # REITs
    if any('reit' in k for k in kw_set):
        return 'REIT Investment Trends'

    # Construction / homebuilder
    if any(k in kw_set for k in ('construction','homebuilder','builder','developer','development')):
        base = 'Residential Construction Activity'
        if 'commercial' in kw_set:
            base = 'Commercial Property Development'
        return base

    # Rental market
    if any(k in kw_set for k in ('rental','rent','landlord','tenant','multifamily','apartment','apartments','condo','condominium')):
        return 'Rental Market Demand'

    # Commercial real estate
    if 'commercial' in kw_set or 'office' in kw_set or 'industrial' in kw_set:
        return 'Commercial Real Estate Activity'

    # Property investment general
    if 'investment' in kw_set or 'property investment' in kw_set:
        return 'Property Investment Activity'

    # Fallback: build from top keywords
    if fk:
        if len(fk) >= 2:
            return f"{clean(fk[0])} & {clean(fk[1])}"
        return f"{clean(fk[0])}"

    # If titles exist, use them to create a short label
    if titles:
        # pick 2-3 meaningful words from first title
        first = titles[0]
        words = [w for w in re.split(r'[^a-zA-Z]+', first) if len(w) > 3]
        if words:
            return ' '.join(words[:3]).title()

    return "Real Estate Trends"


def _make_summary(topic, keywords, headlines, article_count, source_count):
    """Create a concise human-readable summary for the trend using top headlines."""
    summary_parts = []
    summary_parts.append(f"{article_count} article(s) from {source_count} source(s) discuss {topic}.")
    # include up to 3 top headlines as evidence
    top_titles = [h for h in (headlines or []) if h][:3]
    if top_titles:
        titles_joined = ' | '.join(top_titles)
        summary_parts.append(f"Representative headlines: {titles_joined}.")
    elif keywords:
        kw_sample = ', '.join(keywords[:6])
        summary_parts.append(f"Key themes include: {kw_sample}.")
    return ' '.join(summary_parts)


def _map_topic_slug_label(keywords, topic_label, sample_headlines):
    """Map keyword clusters to machine-readable topic slug and human label.
    Conservative, rules-based mapping for business-friendly labels.
    Returns (slug, label)
    """
    kw = set((k or '').lower() for k in (keywords or []))
    txt = ' '.join(sample_headlines or []).lower()

    # Rule: Home Sales Activity
    if (('home sales' in kw or 'sales' in kw) and ('home' in kw or 'housing' in kw)) or ({'home','sales','prices'}.issubset(kw)):
        return ('home_sales', 'Home Sales Activity')

    # Mortgage Market Trends
    if any(x in kw for x in ['mortgage','mortgages','loan','lending','credit','rates']):
        return ('mortgage_market', 'Mortgage Lending Trends')

    # Housing Affordability Challenges
    if ('housing' in kw and ('affordable' in kw or 'affordability' in kw or 'parents' in kw or 'prices' in kw)) or any(w in txt for w in ['living with parents','staying in parents','young adults staying']):
        return ('housing_affordability', 'Housing Affordability Challenges')

    # Affordable Housing Finance
    if ('affordable' in kw and any(x in kw for x in ['fund','bank','finance','mortgage'])):
        return ('affordable_housing_finance', 'Affordable Housing Finance')

    # Indian investment / REIT
    if ('india' in kw or 'indian' in kw) and any(x in kw for x in ['investment','reit','invit','invest']):
        return ('india_real_estate_investment', 'Indian Real Estate Investment Growth')

    # Inclusive Housing & Accessibility
    if any(x in kw for x in ['living','support','inclusive','accessibility']) or any(w in txt for w in ['community living','inclusive housing','mortgage reform']):
        return ('inclusive_housing', 'Inclusive Housing & Accessibility')

    # Real estate M&A
    if any(x in kw for x in ['acquir','acquisition','acquire','merger','m&a','buyback','takeover']) or any(c in txt for c in ['acquire','acquisition','merger','acquisition deal']):
        return ('industry_m_a', 'Real Estate Industry Mergers & Acquisitions')

    # Rental Market Demand
    if any(x in kw for x in ['rental','rent','landlord','tenant','apartment','multifamily']):
        return ('rental_market', 'Rental Market Demand')

    # Commercial Real Estate
    if any(x in kw for x in ['commercial','office','industrial','retail']):
        return ('commercial_real_estate', 'Commercial Real Estate Activity')

    # Property Investment
    if 'investment' in kw or 'property investment' in kw or 'invest' in kw:
        return ('property_investment', 'Property Investment Activity')

    # REITs
    if any('reit' in k for k in kw):
        return ('reit_trends', 'REIT Investment Trends')

    # If topic_label is company or city-like, map to broader category if keywords indicate
    company_indicators = ['fathom','beyond','bed','bed bath','bloomberg','reuters']
    if any(ci in ' '.join((keywords or [])).lower() for ci in company_indicators):
        return ('industry_m_a', 'Real Estate Industry Mergers & Acquisitions')
    if 'toronto' in txt or 'community living' in txt:
        return ('inclusive_housing', 'Inclusive Housing & Accessibility')

    # fallback: use cleaned topic_label as slug
    slug = re.sub(r'[^a-z0-9]+','_', (topic_label or '').lower()).strip('_')
    if not slug:
        slug = 'real_estate_trends'
    # ensure label is human-friendly
    label = topic_label if topic_label and not any(ch.isdigit() for ch in topic_label) else slug.replace('_',' ').title()
    return (slug, label)


def _derive_label_from_keywords(keywords, titles, sample_headlines):
    """Derive a human-readable label from keywords and sample headlines.
    Conservative heuristics to avoid keyword-concatenated labels.
    """
    kw_set = set(k.lower() for k in (keywords or []))

    # Home Sales
    if ('sales' in kw_set or 'home sales' in kw_set) and ('home' in kw_set or 'housing' in kw_set):
        return 'Home Sales Activity'

    # Mortgage lending
    if any(k.startswith('mortg') or k in ('loan','lending','credit') for k in kw_set):
        return 'Mortgage Lending Trends'

    # Affordable housing finance
    if 'affordable' in kw_set and any(x in kw_set for x in ('fund','bank','finance')):
        return 'Affordable Housing Finance'

    # Indian investment localization
    if 'india' in kw_set and 'investment' in kw_set:
        return 'Indian Real Estate Investment Growth'

    # REITs
    if any('reit' in k for k in kw_set):
        return 'REIT Investment Trends'

    # Construction / homebuilder
    if any(k in kw_set for k in ('construction','homebuilder','builder','developer','development')):
        if 'commercial' in kw_set:
            return 'Commercial Property Development'
        return 'Residential Construction Activity'

    # Rental market
    if any(k in kw_set for k in ('rental','rent','landlord','tenant','multifamily','apartment','apartments','condo','condominium')):
        return 'Rental Market Demand'

    # Commercial real estate
    if 'commercial' in kw_set or 'office' in kw_set or 'industrial' in kw_set:
        return 'Commercial Real Estate Activity'

    # Property investment general
    if 'investment' in kw_set or 'property investment' in kw_set:
        return 'Property Investment Activity'

    # handle young adults / parents housing stories
    weak_parent_terms = set(['parent','parents','young','young adults','30','30s','thirties','staying','stay'])
    if any(w in ' '.join(keywords).lower() for w in weak_parent_terms) and any(h in ' '.join((titles or []) + (sample_headlines or [])).lower() for h in ['parents','stay','staying','living with parents','young adults','30-somethings','30s']):
        return 'Housing Affordability Challenges'

    # Fallback: try to craft from titles or sample_headlines (take 2-3 meaningful words)
    for src in (titles or []) + (sample_headlines or []):
        words = [w for w in re.split(r'[^a-zA-Z]+', src) if len(w) > 4]
        if words:
            return ' '.join(words[:3]).title()

    # final fallback: join top keywords in readable form
    if keywords:
        cleaned = [k.replace('/',' ').replace('_',' ').title() for k in keywords[:3] if k.lower() not in GENERIC_KEYWORDS]
        if cleaned:
            return ' '.join(cleaned)

    return 'Real Estate Trends'


def generate_trends():
    from services.normalizer import compute_relevance_score

    db = get_db()
    articles = list(db[ARTICLES_COLLECTION].find({}))
    total = len(articles)
    if not articles:
        logger.info("No articles found")
        return []

    accepted = []
    rejected = []
    for a in articles:
        combined = " ".join(filter(None, [a.get('title',''), a.get('description',''), a.get('content','')]))
        score = compute_relevance_score(combined)
        if score >= 70:
            accepted.append((a, score))
        else:
            rejected.append((a, score))

    # Logging counts
    logger.info(f"Total Articles Read: {total}")
    logger.info(f"Articles Accepted: {len(accepted)}")
    logger.info(f"Articles Rejected: {len(rejected)}")

    # print sample titles for user visibility (20 each)
    print(f"Total Articles Read: {total}")
    print(f"Articles Accepted: {len(accepted)}")
    print(f"Articles Rejected: {len(rejected)}")
    print("\n--- Sample Rejected Titles (up to 20) ---")
    for a, s in rejected[:20]:
        print(f"[{s}] {a.get('title','')}")
    print("\n--- Sample Accepted Titles (up to 20) ---")
    for a, s in accepted[:20]:
        print(f"[{s}] {a.get('title','')}")

    # Prepare texts/meta for accepted only
    texts = []
    ids = []
    meta = []
    articles_accepted = [a for a,_ in accepted]
    for a in articles_accepted:
        txt = " ".join(filter(None, [a.get('title',''), a.get('description',''), a.get('content','')]))
        texts.append(txt)
        ids.append(a.get('_id'))
        meta.append({'source': a.get('source'), 'published_at': a.get('published_at'), 'title': a.get('title',''), 'raw': txt})

    logger.info(f"Processing {len(texts)} articles (accepted)")

    # 1) Deduplicate exact titles
    unique_idx = []
    seen_titles = set()
    for i, m in enumerate(meta):
        t = (m.get('title') or '').strip().lower()
        if t and t in seen_titles:
            continue
        seen_titles.add(t)
        unique_idx.append(i)

    # 2) Remove near-duplicates using simple fingerprint (normalized prefix)
    def fingerprint(s):
        s2 = re.sub(r'[^a-z0-9 ]',' ', (s or '').lower())
        s2 = re.sub(r'\s+',' ', s2).strip()
        return s2[:200]

    final_idx = []
    seen_fps = set()
    for i in unique_idx:
        fp = fingerprint(texts[i])
        if fp in seen_fps:
            continue
        seen_fps.add(fp)
        final_idx.append(i)

    # Build cleaned texts and corresponding metadata arrays
    filtered_texts = [texts[i] for i in final_idx]
    filtered_meta = [meta[i] for i in final_idx]
    filtered_ids = [ids[i] for i in final_idx]

    cleaned_texts = preprocess_documents(filtered_texts)

    # Normalize company names / locations in titles/meta to reduce noise in clustering
    def normalize_names(s):
        if not s:
            return s
        s = s.lower()
        # simple mappings
        s = re.sub(r'bed\s*and\s*bath|bedbath','bed_bath', s)
        s = re.sub(r'\b(los angeles|l\.a\.|la)\b','los_angeles', s)
        s = re.sub(r'\b(new york|nyc)\b','new_york', s)
        s = re.sub(r'\b(bengaluru|bangalore)\b','bengaluru', s)
        return s

    for m in filtered_meta:
        m['title_norm'] = normalize_names(m.get('title',''))
        m['raw_norm'] = normalize_names(m.get('raw',''))

    # Category keyword sets for pre-clustering assignment
    CATEGORY_KEYWORDS = {
        'home_sales': set(['home','home sales','sales','housing','closing','transaction','buyer','seller']),
        'mortgage_market': set(['mortgage','mortgages','loan','lending','rates','refinance','credit']),
        'housing_affordability': set(['affordability','affordable','afford','young','parents','starter home','starter','first-time','first time','prices']),
        'residential_construction': set(['construction','homebuilder','builder','development','starts','groundbreaking','permit','housing starts']),
        'rental_multifamily': set(['rental','rent','landlord','tenant','multifamily','apartment','apartments','condo','condominium']),
        'commercial_real_estate': set(['commercial','office','industrial','retail','lease','office space','industrial property']),
        'reit_investment': set(['reit','invit','fund','property investment','investment','asset manager']),
        'proptech': set(['proptech','platform','listing','search','software','ai','machine learning']),
        'industry_m_a': set(['acquire','acquisition','merger','m&a','buy','takeover','bid','acquiring'])
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

    embeddings = embed_texts(cleaned_texts)

    # Assign a primary category per article using keyword rules
    CATEGORY_PRIORITY = ['home_sales','mortgage_market','residential_construction','rental_multifamily','housing_affordability','commercial_real_estate','reit_investment','industry_m_a','proptech','misc']
    article_categories = []
    for i, txt in enumerate(cleaned_texts):
        cats = detect_categories_for_text(txt)
        if not cats:
            cats = detect_categories_for_text(filtered_meta[i].get('title_norm',''))
        chosen = 'misc'
        for p in CATEGORY_PRIORITY:
            if p in cats:
                chosen = p
                break
        article_categories.append(chosen)

    # Group indices by category
    cat_indices = defaultdict(list)
    for idx, cat in enumerate(article_categories):
        cat_indices[cat].append(idx)

    # Print category distribution before clustering
    print('\nCategory distribution before clustering:')
    category_distribution = {cat: len(idxs) for cat, idxs in cat_indices.items()}
    for cat, cnt in sorted(category_distribution.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")

    # Do NOT merge small categories; preserve category independence
    print('\nPreserving categories without merging small categories.')

    # Recompute distribution after merging
    print('\nCategory distribution after merging small categories:')
    category_distribution = {cat: len(idxs) for cat, idxs in cat_indices.items()}
    for cat, cnt in sorted(category_distribution.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")

    # Cluster inside each category separately to improve diversity
    clusters = defaultdict(list)
    cluster_count_per_category = defaultdict(int)
    global_cluster_counter = 0
    for cat, idxs in cat_indices.items():
        if not idxs:
            continue
        # Extract embeddings for this category
        emb_sub = [embeddings[i] for i in idxs]
        # If there are few articles, don't over-cluster; assign a single cluster per category if <=2
        try:
            if len(emb_sub) <= 2:
                # each article becomes its own small cluster entry
                for i in idxs:
                    clusters[f"{cat}_c{global_cluster_counter}"] = [i]
                    cluster_count_per_category[cat] += 1
                    global_cluster_counter += 1
                continue
            # Run clustering on the subset (use existing cluster_embeddings wrapper)
            # Lower strictness: min_cluster_size=2, min_samples=1
            sub_labels = cluster_embeddings(emb_sub, min_cluster_size=2, min_samples=1)
        except Exception:
            # fallback: place all idxs in one cluster
            clusters[f"{cat}_c{global_cluster_counter}"] = list(idxs)
            cluster_count_per_category[cat] += 1
            global_cluster_counter += 1
            continue

        # Map subcluster labels back to original indices
        local_cluster_ids = set([l for l in sub_labels if l != -1])
        for pos, lbl in enumerate(sub_labels):
            orig_idx = idxs[pos]
            if lbl == -1:
                # noise: create small single-item cluster to preserve article
                clusters[f"{cat}_noise_{global_cluster_counter}"] = [orig_idx]
                cluster_count_per_category[cat] += 1
                global_cluster_counter += 1
            else:
                clusters[f"{cat}_clust_{lbl}"] .append(orig_idx)
        # update cluster count for this category
        cluster_count_per_category[cat] += len(local_cluster_ids)

    # Diagnostics
    n_clusters = len([k for k in clusters.keys()])
    total_articles = len(filtered_texts)
    clustered_articles = sum(len(v) for v in clusters.values())
    noise_articles = 0  # treated as clusters above
    logger.info(f"Clusters generated: {n_clusters}")
    print('\nCluster count per category:')
    for cat, cnt in sorted(cluster_count_per_category.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt}")

    # Diagnostics
    total_articles = len(filtered_texts)
    articles_per_cluster = {k: len(v) for k,v in clusters.items() if k!=-1}
    avg_cluster_size = (sum(articles_per_cluster.values()) / max(1, len(articles_per_cluster))) if articles_per_cluster else 0
    print('Clustering diagnostics:')
    print(f'  total_articles = {total_articles}')
    print(f'  clustered_articles = {clustered_articles}')
    print(f'  noise_articles = {noise_articles}')
    print(f'  cluster_count = {n_clusters}')
    print(f'  average_cluster_size = {avg_cluster_size:.1f}')


    # Build final cluster groups, splitting large/mixed clusters by category signals
    expanded_clusters = []
    for k, idxs in clusters.items():
        if k == -1:
            continue
        # map idxs to global filtered indices
        if len(idxs) == 0:
            continue
        # detect category membership per article
        membership = defaultdict(list)
        for local_idx in idxs:
            text = cleaned_texts[local_idx]
            cats = detect_categories_for_text(text)
            if not cats:
                # fallback: use title_norm
                cats = detect_categories_for_text(filtered_meta[local_idx].get('title_norm',''))
            if not cats:
                membership['misc'].append(local_idx)
            else:
                for c in cats:
                    membership[c].append(local_idx)
        # if cluster is large (>25) or membership contains multiple strong categories, split
        if len(idxs) > 25 or (len([c for c in membership if c!='misc' and len(membership[c])>=3]) >= 2):
            # If very large, first partition into subclusters using KMeans to create smaller coherent groups
            partition_list = [idxs]
            if len(idxs) > 25:
                try:
                    from sklearn.cluster import KMeans
                    # aim for subclusters roughly 10-20 articles; allow up to 8 subclusters
                    n_sub = min(max(2, len(idxs)//12), 8)
                    emb_sub = [embeddings[i] for i in idxs]
                    km = KMeans(n_clusters=n_sub, random_state=42).fit(emb_sub)
                    labels_sub = km.labels_
                    sub_groups = defaultdict(list)
                    for pos, lbl in enumerate(labels_sub):
                        sub_groups[lbl].append(idxs[pos])
                    partition_list = [g for g in sub_groups.values() if g]
                except Exception:
                    partition_list = [idxs]

            # Greedy prioritized splitting applied to each partition
            PRIORITY = ['mortgage_market','home_sales','housing_affordability','residential_construction','rental_multifamily','commercial_real_estate','reit_investment','proptech','industry_m_a']
            any_created = False
            for part in partition_list:
                # build membership for this partition
                part_membership = defaultdict(list)
                for local_idx in part:
                    text = cleaned_texts[local_idx]
                    cats = detect_categories_for_text(text)
                    if not cats:
                        cats = detect_categories_for_text(filtered_meta[local_idx].get('title_norm',''))
                    if not cats:
                        part_membership['misc'].append(local_idx)
                    else:
                        for c in cats:
                            part_membership[c].append(local_idx)
                assigned = set()
                created_any = False
                for cat in PRIORITY:
                    lst = [i for i in part_membership.get(cat, []) if i not in assigned]
                    if len(lst) >= 2:
                        expanded_clusters.append({'label': cat, 'idxs': lst})
                        assigned.update(lst)
                        created_any = True
                        any_created = True
                # other buckets
                for c, lst in part_membership.items():
                    if c == 'misc':
                        continue
                    remaining = [i for i in lst if i not in assigned]
                    if len(remaining) >= 2:
                        expanded_clusters.append({'label': c, 'idxs': remaining})
                        assigned.update(remaining)
                        created_any = True
                        any_created = True
                leftover = [i for i in part if i not in assigned]
                if len(leftover) >= 2:
                    expanded_clusters.append({'label': 'misc', 'idxs': leftover})
                    any_created = True
                elif not created_any:
                    expanded_clusters.append({'label': 'mixed', 'idxs': part})
            if not any_created:
                # fallback to keeping original cluster
                expanded_clusters.append({'label': 'mixed', 'idxs': idxs})
        else:
            expanded_clusters.append({'label': 'mixed', 'idxs': idxs})

    # if no expanded clusters produced (small total), fallback to original clusters
    if not expanded_clusters:
        for k, idxs in clusters.items():
            if k == -1:
                continue
            expanded_clusters.append({'label': 'mixed', 'idxs': idxs})

    # Prepare cluster_docs from expanded_clusters
    cluster_docs = []
    max_article_count = max((len(c['idxs']) for c in expanded_clusters), default=1)
    # compute max source count
    max_source_count = 0
    for g in expanded_clusters:
        idxs = g['idxs']
        sources = set(filtered_meta[i]['source'] for i in idxs if filtered_meta[i].get('source'))
        max_source_count = max(max_source_count, len(sources))

    for group in expanded_clusters:
        idxs = group['idxs']
        cluster_texts = [cleaned_texts[i] for i in idxs]
        titles = [filtered_meta[i].get('title','') for i in idxs]
        # TF-IDF keywords
        try:
            vec = TfidfVectorizer(ngram_range=(1,2), max_features=60)
            X = vec.fit_transform(cluster_texts)
            scores = X.sum(axis=0).A1
            terms = vec.get_feature_names_out()
            ranked = [terms[i] for i in scores.argsort()[::-1]]
            keywords = ranked[:16]
        except Exception:
            keywords = []

        raw_kw = [k.lower() for k in keywords]
        filtered_kw = _filter_keywords(raw_kw)
        final_kw = filtered_kw if filtered_kw else [k for k in raw_kw if 'http' not in k and 'href' not in k]
        # dedupe keywords preserving order
        seen_kw = set(); final_keywords = []
        for k in final_kw:
            if k not in seen_kw:
                final_keywords.append(k); seen_kw.add(k)
        filtered_kw = final_keywords

        article_count = len(idxs)
        sources = [filtered_meta[i]['source'] for i in idxs if filtered_meta[i].get('source')]
        source_count = len(set(sources))
        recency_scores = [recency_weight(filtered_meta[i].get('published_at')) for i in idxs]
        trend_score = compute_trend_score(article_count, source_count, recency_scores, max_article_count, max_source_count)

        topic = _generate_topic_name(filtered_kw or keywords, titles)
        sample_headlines = [filtered_meta[i].get('title','') for i in idxs[:5]]
        top_sources = _top_sources(idxs, filtered_meta, limit=5)
        summary = _make_summary(topic, filtered_kw or keywords, sample_headlines, article_count, source_count)
        topic_label = _derive_label_from_keywords(filtered_kw or keywords, titles, sample_headlines)

        cluster_doc = {
            "topic": topic,
            "topic_label": topic_label,
            "summary": summary,
            "trend_score": int(trend_score),
            "article_count": article_count,
            "source_count": source_count,
            "keywords": filtered_kw,
            "top_sources": top_sources,
            "sample_headlines": sample_headlines,
            "member_idxs": idxs,
            "member_article_ids": [filtered_ids[i] for i in idxs],
            "created_at": datetime.utcnow().isoformat() + 'Z'
        }
        cluster_docs.append(cluster_doc)

    # Post-process: split overly large clusters (>15) into meaningful sub-trends using KMeans
    def choose_subtrend_label_from_kw(kw_list, titles):
        kw = set((k or '').lower() for k in (kw_list or []))
        txt = ' '.join(titles or []).lower()
        if any('price' in k or 'pricing' in k for k in kw) or 'price' in txt:
            return ('home_prices','Home Prices')
        if any(k in kw for k in ('sale','sales','sold','pending','closing')) or 'home sales' in txt:
            return ('home_sales','Home Sales')
        if any(k in kw for k in ('mortgage','mortgages','loan','lending','refinance','rates')) or 'mortgage' in txt:
            return ('mortgage_activity','Mortgage Activity')
        if any(k in kw for k in ('construction','starts','pipeline','permit','development')) or 'housing starts' in txt:
            # further check for builder terms
            if any(k in kw for k in ('builder','homebuilder','developer')):
                return ('builder_activity','Builder Activity')
            return ('housing_supply','Housing Supply')
        if any(k in kw for k in ('reit','invit','fund','investment')) or 'reit' in txt:
            return ('reit_trends','REIT Investment Trends')
        return ('home_sales','Home Sales')

    new_cluster_docs = []
    for doc in cluster_docs:
        if doc.get('article_count',0) > 15:
            idxs = doc.get('member_idxs', [])
            try:
                from sklearn.cluster import KMeans
                n_sub = min(max(2, len(idxs)//8), 8)
                emb_sub = [embeddings[i] for i in idxs]
                km = KMeans(n_clusters=n_sub, random_state=42).fit(emb_sub)
                labels_sub = km.labels_
                sub_groups = defaultdict(list)
                for pos, lbl in enumerate(labels_sub):
                    sub_groups[lbl].append(idxs[pos])
                for grp in sub_groups.values():
                    if len(grp) >= 3:
                        cluster_texts = [cleaned_texts[i] for i in grp]
                        titles = [filtered_meta[i].get('title','') for i in grp]
                        try:
                            vec = TfidfVectorizer(ngram_range=(1,2), max_features=40)
                            X = vec.fit_transform(cluster_texts)
                            scores = X.sum(axis=0).A1
                            terms = vec.get_feature_names_out()
                            ranked = [terms[i] for i in scores.argsort()[::-1]]
                            keywords = ranked[:12]
                        except Exception:
                            keywords = []
                        filtered_kw = _filter_keywords([k.lower() for k in keywords])
                        article_count = len(grp)
                        sources = [filtered_meta[i]['source'] for i in grp if filtered_meta[i].get('source')]
                        source_count = len(set(sources))
                        recency_scores = [recency_weight(filtered_meta[i].get('published_at')) for i in grp]
                        trend_score = compute_trend_score(article_count, source_count, recency_scores, max_article_count, max_source_count)
                        slug, label = choose_subtrend_label_from_kw(filtered_kw or keywords, titles)
                        sample_headlines = [filtered_meta[i].get('title','') for i in grp[:5]]
                        # acceptance: for subgroups from a large parent cluster, allow single-source with >=3 articles
                        allow_single_source_from_large_parent = True
                        if (article_count >=3 and (source_count >=2 or allow_single_source_from_large_parent)) or (article_count >=4 and source_count >=1):
                            new_cluster_docs.append({
                                'topic': slug,
                                'topic_label': label,
                                'summary': _make_summary(label, filtered_kw or keywords, sample_headlines, article_count, source_count),
                                'trend_score': int(trend_score),
                                'article_count': article_count,
                                'source_count': source_count,
                                'keywords': filtered_kw,
                                'top_sources': [],
                                'sample_headlines': sample_headlines,
                                'member_idxs': grp,
                                'member_article_ids': [filtered_ids[i] for i in grp],
                                'created_at': datetime.utcnow().isoformat() + 'Z'
                            })
                if not new_cluster_docs:
                    new_cluster_docs.append(doc)
            except Exception:
                new_cluster_docs.append(doc)
        else:
            new_cluster_docs.append(doc)

    cluster_docs = new_cluster_docs

    # Filter clusters: relaxed acceptance rule
    final_insertable = []
    for d in cluster_docs:
        ac = d.get('article_count',0)
        sc = d.get('source_count',0)
        if (ac >= 3 and sc >= 2) or (ac >= 4 and sc >= 1):
            final_insertable.append(d)

    trends_coll = db[TRENDS_COLLECTION]
    trends_coll.delete_many({})
    if final_insertable:
        trends_coll.insert_many(final_insertable)
    logger.info(f"Trends created: {len(final_insertable)}")
    # Diagnostics
    print('\nArticles per category:')
    for cat, idxs in cat_indices.items():
        print(f"  {cat}: {len(idxs)}")
    print('\nClusters per category:')
    for cat, cnt in cluster_count_per_category.items():
        print(f"  {cat}: {cnt}")
    print('\nFinal trends inserted:', len(final_insertable))
    return final_insertable


def fetch_trends():
    db = get_db()
    trends = list(db[TRENDS_COLLECTION].find({}).sort('trend_score', DESCENDING))
    # convert ObjectId if present
    for t in trends:
        t.pop('_id', None)
    return trends
