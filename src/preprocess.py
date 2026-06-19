import re
from typing import List

# Stopword fallback
try:
    from nltk.corpus import stopwords
    STOPWORDS = set(stopwords.words("english"))
except Exception:
    # Minimal fallback list
    STOPWORDS = set(["the","and","is","in","to","of","a","for","on","with","that","as","by","an"])

PUNCT_RE = re.compile(r"[^\w\s]")
URL_RE = re.compile(r"http\S+|www\.\S+", flags=re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")
ENTITY_RE = re.compile(r"&[a-z]+;", flags=re.IGNORECASE)
ARTIFACT_TOKENS = set(["href","nbsp","noscript","amp","html","div","span","script","iframe","style","svg","click","read","article","story","link","more","view"])


def clean_text(text: str) -> str:
    if not text:
        return ""
    s = text.lower()
    # remove urls and html tags/entities
    s = URL_RE.sub(" ", s)
    s = HTML_TAG_RE.sub(" ", s)
    s = ENTITY_RE.sub(" ", s)
    s = PUNCT_RE.sub(" ", s)
    tokens = [t for t in s.split()
              if t not in STOPWORDS
              and t not in ARTIFACT_TOKENS
              and len(t) > 2
              and not any(ch.isdigit() for ch in t)
              and not t.startswith('http')]
    return " ".join(tokens)


def preprocess_documents(docs: List[str]) -> List[str]:
    return [clean_text(d) for d in docs]
