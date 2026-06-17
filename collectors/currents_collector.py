import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('CURRENTS_API_KEY')
KEYWORDS = ["real estate","housing","mortgage","property","commercial real estate","residential real estate","construction","housing market"]

def fetch_currents(limit=100):
    if not API_KEY:
        return []
    q = ' OR '.join(KEYWORDS)
    url = 'https://api.currentsapi.services/v1/search'
    params = {'keywords': q, 'apiKey': API_KEY, 'language': 'en', 'limit': limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        articles = []
        for a in data.get('news', []):
            articles.append({
                'title': a.get('title'),
                'description': a.get('description'),
                'content': a.get('description') or a.get('content'),
                'source': a.get('source'),
                'url': a.get('url'),
                'published_at': a.get('published')
            })
        return articles
    except Exception:
        return []
