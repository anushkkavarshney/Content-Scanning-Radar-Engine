import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "trend_radar")
TRENDS_COLLECTION = os.getenv("TRENDS_COLLECTION", "trends")
ARTICLES_COLLECTION = os.getenv("ARTICLES_COLLECTION", "news_articles")

# DBSCAN params
# Lower default eps to create more, tighter clusters
DBSCAN_EPS = float(os.getenv("DBSCAN_EPS", "0.45"))
DBSCAN_MIN_SAMPLES = int(os.getenv("DBSCAN_MIN_SAMPLES", "1"))
# HDBSCAN params (used if hdbscan is available and enabled)
USE_HDBSCAN = os.getenv("USE_HDBSCAN", "1") == "1"  # enable HDBSCAN by default for finer clusters
HDBSCAN_MIN_CLUSTER_SIZE = int(os.getenv("HDBSCAN_MIN_CLUSTER_SIZE", "3"))
HDBSCAN_MIN_SAMPLES = int(os.getenv("HDBSCAN_MIN_SAMPLES", "1"))

# Embedding model
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
