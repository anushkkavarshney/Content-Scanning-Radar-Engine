Real Estate News Collection Service

Overview:
Collects real estate news from multiple APIs and RSS feeds, normalizes, deduplicates, and stores in MongoDB.

Run locally:
1. Copy .env.example to .env and fill keys.
2. pip install -r requirements.txt
3. python main.py

Scheduler:
- fetch news every 15 minutes

Collections:
- news_articles

Do not commit secrets; use .env only locally.
