import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('GNEWS_API_KEY')
KEYWORDS = ["real estate","housing","mortgage","property","commercial real estate","residential real estate","construction","housing market"]

def fetch_gnews(page_size=100):
    if not API_KEY:
        return []
    q = ' OR '.join(KEYWORDS)
    url = 'https://gnews.io/api/v4/search'
    params = {'q': q, 'token': API_KEY, 'lang': 'en', 'max': page_size}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        articles = []
        for a in data.get('articles', []):
            articles.append({
                'title': a.get('title'),
                'description': a.get('description'),
                'content': a.get('content') or a.get('description'),
                'source': a.get('source', {}).get('name') if isinstance(a.get('source'), dict) else a.get('source'),
                'url': a.get('url'),
                'published_at': a.get('publishedAt') or a.get('published_at')
            })
        return articles
    except Exception:
        return []
