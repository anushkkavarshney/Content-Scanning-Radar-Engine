from datetime import datetime
from dateutil import parser
import os
import re
from dotenv import load_dotenv

load_dotenv()

# Strong required whitelist terms (at least one required) for real-estate relevance
STRONG_WHITELIST = [
    'real estate', 'real-estate', 'realestate', 'property', 'properties',
    'housing', 'housing market', 'housing demand', 'housing prices', 'home sales',
    'homebuilder', 'home builders', 'builder',
    'land development', 'residential development', 'commercial development', 'mixed-use development',
    'construction', 'construction activity',
    'residential', 'residential real estate', 'commercial', 'commercial property', 'commercial real estate',
    'office market', 'office vacancy', 'industrial property',
    'multifamily', 'multifamily housing', 'apartment', 'apartments', 'condo', 'condos', 'condominium',
    'rental', 'rentals', 'rental market', 'rent', 'landlord', 'tenant',
    'mortgage', 'mortgages', 'property investment', 'investment property', 'reit', 'reits',
    'affordable housing'
]

# Additional permissive whitelist tokens
WHITELIST_TERMS = os.getenv('RE_WHITELIST', "real estate|real-estate|realestate|housing|home|mortgage|property|apartment|condo|construction|developer|land|reits|reit|office|commercial|residential|rental|rent|builder|homebuilder|listing|sold|sale|vacancy|office vacancy|multifamily|apartment building|rental market|housing demand|housing prices|affordable housing").split('|')

# Hard reject blacklist (sports, entertainment, tech, gaming, healthcare, cybersecurity, AI)
BLACKLIST_TERMS = [
    'nfl','nba','football','soccer','cricket','baseball','tennis','olympics',
    'celebrity','singer','actor','actress','movie','netflix','disney','taylor swift','travis kelce',
    'iphone','samsung','galaxy','smartphone','foldable phone',
    'casino','gambling','betting','esports',
    'radiology','hospital','medical research','clinical trial',
    'cybersecurity','malware','ransomware',
    'chatgpt','llm','generative ai','ai startup'
]

# Compile regexes
WHITELIST_RE = re.compile(r"\b(?:" + r"|".join([re.escape(w.strip()) for w in WHITELIST_TERMS if w.strip()]) + r")\b", flags=re.IGNORECASE)
BLACKLIST_RE = re.compile(r"\b(?:" + r"|".join([re.escape(w.strip()) for w in BLACKLIST_TERMS if w.strip()]) + r")\b", flags=re.IGNORECASE)
STRONG_RE = re.compile(r"\b(?:" + r"|".join([re.escape(w.strip()) for w in STRONG_WHITELIST if w.strip()]) + r")\b", flags=re.IGNORECASE)

# New stricter positive/negative keyword sets (per user request)
POSITIVE_KEYWORDS = [
    "real estate","housing","home sales","home price","mortgage","property","realtor",
    "multifamily","residential","commercial real estate","apartment","rent","rental","housing market",
    "construction","housing starts","homebuilder","reit","realty","property investment","zoning",
    "housing affordability","land development"
]

NEGATIVE_SPORTS = ["football","soccer","nba","nfl","chelsea","barcelona","liverpool","golf","cricket","tennis","baseball"]
NEGATIVE_CRYPTO = ["bitcoin","ethereum","crypto","token","blockchain"]
NEGATIVE_HEALTH = ["medical","hospital","patient","clinical","radiology","hpv","healthcare"]
NEGATIVE_TECH = ["cybersecurity","software","cloud","virtualization","ai platform","endpoint security"]
NEGATIVE_GAMBLING = ["casino","free spins","igaming","betting"]
NEGATIVE_AUTO = ["vehicle","automotive","car","truck","warranty"]

NEGATIVE_KEYWORDS = set(NEGATIVE_SPORTS + NEGATIVE_CRYPTO + NEGATIVE_HEALTH + NEGATIVE_TECH + NEGATIVE_GAMBLING + NEGATIVE_AUTO)

# Block obvious press-release spam sources (can be extended via env var)
SPAM_SOURCE_BLOCKLIST = os.getenv('SPAM_SOURCE_BLOCKLIST', '').split(',') if os.getenv('SPAM_SOURCE_BLOCKLIST') else []
# Explicit press release sources to send directly to removed collection
PRESS_RELEASE_SOURCES = set([s.lower() for s in ['PRNewswire','GlobeNewswire','BusinessWire','ACCESSWIRE','EIN Presswire']])

_POS_RE = re.compile(r"\b(?:" + r"|".join([re.escape(w) for w in POSITIVE_KEYWORDS]) + r")\b", flags=re.IGNORECASE)
_NEG_RE = re.compile(r"\b(?:" + r"|".join([re.escape(w) for w in NEGATIVE_KEYWORDS]) + r")\b", flags=re.IGNORECASE)


def _score_article_text(title: str, description: str, content: str):
    t = (title or '').lower()
    d = (description or '').lower()
    c = (content or '').lower()

    pos_matches = set()
    neg_matches = set()
    score = 0

    # positive signals
    if _POS_RE.search(t):
        score += 25
        pos_matches.update(m.group(0).lower() for m in _POS_RE.finditer(t))
    if _POS_RE.search(d):
        score += 15
        pos_matches.update(m.group(0).lower() for m in _POS_RE.finditer(d))
    if _POS_RE.search(c):
        score += 10
        pos_matches.update(m.group(0).lower() for m in _POS_RE.finditer(c))

    # negative signals
    if _NEG_RE.search(t):
        score -= 30
        neg_matches.update(m.group(0).lower() for m in _NEG_RE.finditer(t))
    if _NEG_RE.search(d):
        score -= 20
        neg_matches.update(m.group(0).lower() for m in _NEG_RE.finditer(d))
    if _NEG_RE.search(c):
        score -= 10
        neg_matches.update(m.group(0).lower() for m in _NEG_RE.finditer(c))

    return score, sorted(pos_matches), sorted(neg_matches)


def validate_real_estate_article(article: dict) -> dict:
    """
    Returns a dict with keys:
      - accepted (bool)
      - score (int)
      - pos_matches (list)
      - neg_matches (list)
      - reason (str)
    """
    title = article.get('title','')
    description = article.get('description','')
    content = article.get('content','')
    source = (article.get('source') or article.get('source_name') or '').strip()

    if source and source.lower() in [s.strip().lower() for s in SPAM_SOURCE_BLOCKLIST if s.strip()]:
        return {'accepted': False, 'score': 0, 'pos_matches': [], 'neg_matches': [f'spam_source:{source}'], 'reason': f'spam source {source}'}

    # Press release source check
    if source and any(ps in source.lower() for ps in PRESS_RELEASE_SOURCES):
        return {'accepted': False, 'score': 0, 'pos_matches': [], 'neg_matches': [f'press_release_source:{source}'], 'reason': 'press_release_source'}

    score, pos, neg = _score_article_text(title, description, content)
    accepted = False
    reason = ''
    # accepted only if score >= 50 and at least one positive match
    if score >= 50 and pos and not neg:
        accepted = True
        reason = 'strong_positive_no_negatives'
    elif score >= 50 and pos and neg:
        # if negatives present, reject but record that positives existed
        accepted = False
        reason = 'negatives_present'
    else:
        accepted = False
        reason = 'insufficient_positive_signals'

    return {'accepted': accepted, 'score': score, 'pos_matches': pos, 'neg_matches': neg, 'reason': reason}


def is_real_estate_article(article: dict) -> bool:
    # Backward-compatible wrapper
    res = validate_real_estate_article(article)
    if res.get('accepted'):
        print(f"Accepted score={res.get('score')} | positives={res.get('pos_matches')} | negatives={res.get('neg_matches')}")
        return True
    print(f"Rejected score={res.get('score')} | positives={res.get('pos_matches')} | negatives={res.get('neg_matches')} | reason={res.get('reason')}")
    return False


# Keep original compute_relevance_score for backward compatibility (used elsewhere)
def compute_relevance_score(text: str) -> int:
    """Return a 0-100 relevance score for real-estate content.
    Rules:
      - If any BLACKLIST_RE matches -> 0
      - If STRONG_RE matches -> 90 + (extra unique strong matches * 2) capped at 100
      - Else count unique WHITELIST terms matched: 3+ ->75, 2 ->70, 1 ->50, 0 ->0
    """
    if not text:
        return 0
    t = text.lower()
    if BLACKLIST_RE.search(t):
        return 0
    strong_matches = set(m.group(0).lower() for m in STRONG_RE.finditer(t))
    if strong_matches:
        score = 90 + min(10, len(strong_matches) * 2)
        return min(100, score)
    # permissive matches
    matches = set(m.group(0).lower() for m in WHITELIST_RE.finditer(t))
    count = len(matches)
    if count >= 3:
        return 75
    if count == 2:
        return 70
    if count == 1:
        return 50
    return 0


def is_real_estate_text(text: str) -> bool:
    # Backward-compatible wrapper that uses compute_relevance_score
    score = compute_relevance_score(text)
    return score >= 70


def normalize_article(raw):
    # Ensure required fields and consistent keys
    title = raw.get('title') or ''
    description = raw.get('description') or ''
    content = raw.get('content') or description or ''
    source = raw.get('source') or raw.get('source_name') or 'unknown'
    url = raw.get('url')
    published_raw = raw.get('published_at') or raw.get('published')
    published_at = None
    if published_raw:
        try:
            published_at = parser.parse(published_raw).isoformat()
        except Exception:
            published_at = None
    collected_at = datetime.utcnow().isoformat()

    combined = ' '.join([title, description, content])
    # New category decision uses stricter per-article validator
    res = validate_real_estate_article({'title': title, 'description': description, 'content': content, 'source': source})
    is_re = res.get('accepted')
    category = 'real_estate' if is_re else 'other'
    score = compute_relevance_score(combined)

    return {
        'title': title.strip(),
        'description': description.strip(),
        'content': content.strip(),
        'source': source,
        'url': url,
        'published_at': published_at,
        'collected_at': collected_at,
        'category': category,
        'real_estate_relevance_score': score,
        'validation': res
    }
