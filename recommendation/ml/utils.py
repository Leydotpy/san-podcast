import os
import joblib
import numpy as np
from django.conf import settings

ARTIFACT_DIR = getattr(settings, "RECOMMENDER_ARTIFACT_DIR")

def load_nmf():
    nmf = joblib.load(os.path.join(ARTIFACT_DIR, 'nmf_model.joblib'))
    meta = joblib.load(os.path.join(ARTIFACT_DIR, 'nmf_meta.joblib'))
    W = np.load(os.path.join(ARTIFACT_DIR, 'W.npy'))
    H = np.load(os.path.join(ARTIFACT_DIR, 'H.npy'))
    return nmf, meta, W, H

def load_content():
    tf = joblib.load(os.path.join(ARTIFACT_DIR, 'tfidf.joblib'))
    svd = joblib.load(os.path.join(ARTIFACT_DIR, 'svd.joblib'))
    meta = joblib.load(os.path.join(ARTIFACT_DIR, 'content_meta.joblib'))
    X_svd = np.load(os.path.join(ARTIFACT_DIR, 'X_svd.npy'))
    return tf, svd, meta, X_svd

def load_faiss_index():
    import faiss
    idx = faiss.read_index(os.path.join(ARTIFACT_DIR, 'faiss_index.ivf'))
    hybrid_meta = joblib.load(os.path.join(ARTIFACT_DIR, 'hybrid_meta.joblib'))
    return idx, hybrid_meta

# compute user vector for ANN query:
# Option A: if W saved and user present in user_ids -> use W row
# Option B: compute weighted centroid of item vectors for user's listened episodes


def get_user_vector_ann(user_id, user_to_index, W, hybrid_item_matrix):
    """Return normalized user vector for ANN query. hybrid_item_matrix should be numpy array (n_items x dim)
    user_to_index maps user_id -> row index in W (if W saved for that user set)."""
    if user_id in user_to_index:
        uidx = user_to_index[user_id]
        vec_nmf = W[uidx]  # shape (k,)
        # project to hybrid space by simple composition: here we tile nmf into hybrid dims
        # Better: precompute user hybrid by multiplying user latent * item_factors.T -> yields pseudo-item vector
        # Simpler approach: concatenate nmf user vector with zeros for content part
        k = vec_nmf.shape[0]
        content_part = np.zeros(hybrid_item_matrix.shape[1] - k, dtype='float32')
        vec = np.concatenate([vec_nmf.astype('float32'), content_part])
        # normalize
        vec = vec.reshape(1, -1)
        vec = vec / np.linalg.norm(vec)
        return vec.astype('float32')
    # fallback: centroid of listened items
    return None
