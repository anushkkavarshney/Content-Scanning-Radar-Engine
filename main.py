import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()
from services.scheduler import start_scheduler, collect_all_news
from database import mongodb

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger('news_app')

app = FastAPI()

@app.on_event('startup')
def startup_event():
    logger.info('Starting service and scheduler')
    start_scheduler()

@app.get('/health')
def health():
    return {'status': 'ok'}

@app.post('/collect_now')
def collect_now():
    collect_all_news()
    return {'status': 'collected'}

if __name__ == '__main__':
    import uvicorn
    start_scheduler()
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=False)
