import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('MEDIASTACK_API_KEY')
KEYWORDS = ["real estate","housing","mortgage","property","commercial real estate","residential real estate","construction","housing market"]

def fetch_mediastack(limit=100):
    if not API_KEY:
        return []
    q = ' OR '.join(KEYWORDS)
    url = 'http://api.mediastack.com/v1/news'
    params = {'access_key': API_KEY, 'keywords': q, 'limit': limit, 'languages':'en'}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        articles = []
        for a in data.get('data', []):
            articles.append({
                'title': a.get('title'),
                'description': a.get('description'),
                'content': a.get('body') or a.get('description'),
                'source': a.get('source'),
                'url': a.get('url'),
                'published_at': a.get('published_at')
            })
        return articles
    except Exception:
        return []
