import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.scheduler import collect_all_news

if __name__ == '__main__':
    collect_all_news()
