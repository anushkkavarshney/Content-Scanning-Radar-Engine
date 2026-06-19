from sentence_transformers import SentenceTransformer
import numpy as np
from .config import EMBEDDING_MODEL

_model = None

def _load_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts):
    model = _load_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return np.array(embeddings)
