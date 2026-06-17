from pymongo import MongoClient, errors
import os
from dotenv import load_dotenv
import logging

load_dotenv()
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
DB_NAME = os.getenv('MONGO_DB', 'trend_radar')

logger = logging.getLogger('mongodb')

# Create client with a short server selection timeout to fail fast if Atlas URI is invalid
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    # Ping to verify connection
    client.admin.command('ping')
    logger.info('Connected to MongoDB')
except Exception as e:
    logger.exception(f'Failed to connect to MongoDB using MONGO_URI={MONGO_URI}: {e}')
    # Fallback: create client anyway (operations will raise on use)
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

db = client[DB_NAME]
news_collection = db['news_articles']

# Ensure basic indexes
try:
    news_collection.create_index([('url', 1)], unique=True, sparse=True)
    news_collection.create_index([('title', 1)])
    news_collection.create_index([('published_at', -1)])
    news_collection.create_index([('collected_at', -1)])
except Exception:
    logger.exception('Failed to create indexes on news_articles')
