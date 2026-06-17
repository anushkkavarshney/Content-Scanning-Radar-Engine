import logging
from apscheduler.schedulers.background import BackgroundScheduler
from collectors.newsapi_collector import fetch_newsapi
from collectors.gnews_collector import fetch_gnews
from collectors.mediastack_collector import fetch_mediastack
from collectors.currents_collector import fetch_currents
from collectors.rss_collector import fetch_rss_feeds
from services.deduplication import remove_duplicates, save_articles_bulk

logger = logging.getLogger('news_scheduler')

def collect_all_news():
    logger.info('Starting collection run')
    all_raw = []
    try:
        sources = [fetch_newsapi, fetch_gnews, fetch_mediastack, fetch_currents, fetch_rss_feeds]
        for fn in sources:
            try:
                res = fn()
                logger.info(f"Fetched {len(res)} from {fn.__name__}")
                all_raw.extend(res)
            except Exception as e:
                logger.exception(f"Collector {fn.__name__} failed: {e}")
        unique = remove_duplicates(all_raw)
        stored = save_articles_bulk(unique)
        logger.info(f"Collection complete: fetched={len(all_raw)} unique_stored={stored}")
    except Exception as e:
        logger.exception(f"Collection run failed: {e}")

_scheduler = None

def start_scheduler():
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(collect_all_news, 'interval', minutes=15, id='collect_news')
    _scheduler.start()
    logger.info('Scheduler started with collect job every 15 minutes')
    return _scheduler
