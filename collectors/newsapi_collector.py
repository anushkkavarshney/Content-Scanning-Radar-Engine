import os
import requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
API_KEY = os.getenv('NEWSAPI_KEY')

KEYWORDS = ["real estate","housing","mortgage","property","commercial real estate","residential real estate","construction","housing market"]

def fetch_newsapi(page_size=100):
    if not API_KEY:
        return []
    q = ' OR '.join(KEYWORDS)
    url = 'https://newsapi.org/v2/everything'
    params = {'q': q, 'pageSize': page_size, 'apiKey': API_KEY, 'language': 'en', 'sortBy': 'publishedAt'}
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
                'source': a.get('source', {}).get('name'),
                'url': a.get('url'),
                'published_at': a.get('publishedAt')
            })
        return articles
    except Exception:
        return []
