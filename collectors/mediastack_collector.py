import os
import requests
from dotenv import load_dotenv

load_dotenv()

KEYWORDS = ["realestate"]

def fetch_mediastack(limit=10):
    API_KEY = os.getenv("MEDIASTACK_API_KEY")
    if not API_KEY:
        print("❌ Mediastack Error: MEDIASTACK_API_KEY is not defined in the .env file.")
        return []

    url = 'http://api.mediastack.com/v1/news'
    q = ','.join(KEYWORDS)
    
    params = {
        'access_key': API_KEY,
        'keywords': q,
        'languages': 'en',
        'limit': limit
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        response_data = r.json()
        
        if "data" in response_data:
            articles = response_data["data"]
            processed_articles = []
            for a in articles:
                processed_articles.append({
                    'title': a.get('title'),
                    'description': a.get('description'),
                    'content': a.get('body') or a.get('description'),
                    'source': a.get('source'),
                    'url': a.get('url'),
                    'published_at': a.get('published_at')
                })
            return processed_articles
        else:
            return []
            
    except Exception as e:
        print(f"❌ Mediastack Collector Failed: {e}")
        return []