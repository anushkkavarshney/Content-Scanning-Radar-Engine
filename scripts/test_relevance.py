import sys, os
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from services.normalizer import compute_relevance_score, STRONG_RE, WHITELIST_RE, BLACKLIST_RE
samples = [
    "Real Estate: Prices stagnated in 2026 but remain very high — Buyer profiles by area in Attica",
    "Why do commercial spaces sit vacant?",
    "Compass expands in northern Arizona",
    "7 interior design trends driving demand in residential properties",
    "Developer Michael Klinger sells waterfront Bal Harbour mansion for $43M",
    "Kite Realty Group Completes $136 Million in Strategic Acquisitions and $255 Million in Strategic Dispositions",
    "National Homebuilder M/I Homes Hires Prophetic for Land Evaluation",
    "How to ensure business continuity in data center decommission",
    "India’s REIT, InvIT market likely to add Rs 11.6 lakh crore investments over five years",
    "Design-Build Continues to Gain Ground Across Industrial Landscape"
]
for s in samples:
    score = compute_relevance_score(s)
    strong = [m.group(0) for m in STRONG_RE.finditer(s)]
    weak = [m.group(0) for m in WHITELIST_RE.finditer(s)]
    black = [m.group(0) for m in BLACKLIST_RE.finditer(s)]
    print('---')
    print('TEXT:', s)
    print('SCORE:', score)
    print('STRONG:', strong)
    print('WEAK:', list(set(weak)))
    print('BLACK:', black)
