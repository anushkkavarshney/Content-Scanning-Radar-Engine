from datetime import datetime
import math


def compute_trend_score(article_count, source_count, recency_scores, max_article_count, max_source_count):
    """Combine normalized article count, source diversity, and recency into 0-100."""
    if max_article_count <= 0:
        return 0
    a = article_count / max_article_count  # 0-1
    s = (source_count / max_source_count) if max_source_count>0 else 0
    # recency_scores: list of recency weights (0-1), take mean
    r = (sum(recency_scores) / len(recency_scores)) if recency_scores else 0
    # weights
    score = 0.5 * a + 0.3 * s + 0.2 * r
    return int(max(0, min(100, round(score * 100))))


def recency_weight(published_at):
    """Return recency weight 0-1 based on days since published. More recent -> closer to 1."""
    if not published_at:
        return 0
    try:
        if isinstance(published_at, str):
            from dateutil import parser
            dt = parser.parse(published_at)
        else:
            dt = published_at
        days = (datetime.utcnow() - dt).days
        # exponential decay with 30-day half-life approx
        w = math.exp(-days / 30.0)
        return float(w)
    except Exception:
        return 0
