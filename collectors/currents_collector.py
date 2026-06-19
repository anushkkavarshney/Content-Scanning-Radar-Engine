import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Simplified single term to ensure their free-tier indexing catches it
KEYWORDS = ["housing"]

def fetch_currents(limit=10):
    API_KEY = os.getenv("CURRENTS_API_KEY")
    if not API_KEY:
        print("❌ Currents Error: CURRENTS_API_KEY is not defined in the .env file.")
        return []

    url = 'https://api.currentsapi.services/v1/search'
    q = ' '.join(KEYWORDS)
    
    params = {
        'keywords': q,
        'apiKey': API_KEY,  # Required camelCase syntax
        'language': 'en',
        'limit': limit
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        
        # Keeping a clean debug status tracker (no text wall)
        print(f"🔍 Currents Server Response Status: {r.status_code}")
        if r.status_code != 200:
            print(f"🔍 Currents Details: {r.text}")
            
        r.raise_for_status()
        response_data = r.json()
        
        if "news" in response_data:
            articles = response_data["news"]
            processed_articles = []
            for a in articles:
                processed_articles.append({
                    'title': a.get('title'),
                    'description': a.get('description'),
                    'content': a.get('description') or a.get('content'),
                    'source': a.get('author'),
                    'url': a.get('url'),
                    'published_at': a.get('published')
                })
            return processed_articles
        else:
            return []
            
    except Exception as e:
        print(f"❌ Currents Collector Failed: {e}")
        return []
