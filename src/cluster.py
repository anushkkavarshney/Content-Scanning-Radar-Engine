# try HDBSCAN when available; otherwise fallback to DBSCAN
import numpy as np
from sklearn.cluster import DBSCAN
from .config import DBSCAN_EPS, DBSCAN_MIN_SAMPLES, USE_HDBSCAN, HDBSCAN_MIN_CLUSTER_SIZE, HDBSCAN_MIN_SAMPLES


def cluster_embeddings(embeddings, eps=None, min_samples=None, min_cluster_size=None, use_hdbscan=None):
    """Cluster embeddings. Prefer HDBSCAN if available and enabled; else DBSCAN.
    Returns array of labels (noise = -1).
    """
    # prefer HDBSCAN for variable-density clustering
    if use_hdbscan is None:
        use_hdbscan = USE_HDBSCAN
    if use_hdbscan:
        try:
            import hdbscan
            mcs = HDBSCAN_MIN_CLUSTER_SIZE if min_cluster_size is None else min_cluster_size
            ms = HDBSCAN_MIN_SAMPLES if min_samples is None else min_samples
            # HDBSCAN supports 'cosine' metric
            clusterer = hdbscan.HDBSCAN(min_cluster_size=mcs, min_samples=ms, metric='cosine')
            labels = clusterer.fit_predict(embeddings)
            return labels
        except Exception:
            # fallback to DBSCAN if HDBSCAN not installed
            pass

    # DBSCAN fallback
    if eps is None:
        eps = DBSCAN_EPS
    if min_samples is None:
        min_samples = DBSCAN_MIN_SAMPLES
    db = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
    labels = db.fit_predict(embeddings)
    return labels
