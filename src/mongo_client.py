import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()
from .config import MONGO_URI, DB_NAME
import logging

logger = logging.getLogger('mongo_client')

# Allow .env or environment to override config values
MONGO_URI_FINAL = os.getenv('MONGO_URI', MONGO_URI)
DB_NAME_FINAL = os.getenv('DB_NAME', DB_NAME)

# Create client with a short server selection timeout for fast feedback
_client = MongoClient(MONGO_URI_FINAL, serverSelectionTimeoutMS=5000)
try:
    _client.admin.command('ping')
    logger.info('Connected to MongoDB')
except Exception as e:
    logger.exception('MongoDB connection failed')

_db = _client[DB_NAME_FINAL]


def get_db():
    return _db
