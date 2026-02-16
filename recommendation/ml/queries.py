import os
import sys

import numpy as np
from django.conf import settings
from django.core.cache import cache

from api.rest.web.apps.podcasts.serializers import EpisodeListSerializer
from apps.posts.podcasts.models import Episode
from .utils import get_user_vector_ann

NMF_COMPONENTS = getattr(settings, "NMF_COMPONENTS", 64)
SVD_COMPONENTS = getattr(settings, "SVD_COMPONENTS", 64)

HYBRID_DIM = NMF_COMPONENTS + SVD_COMPONENTS

art = sys.modules.get('recommendation._ARTIFACTS', {})


# helper to run ANN query
def ann_recommend_for_user(user_id, top_k=20):
    if not art:
        return []
    faiss_index = art.get('faiss_index')
    hybrid_meta = art.get('hybrid_meta')
    episode_ids = hybrid_meta['episode_ids']
    # try use saved W mapping
    nmf_meta = art.get('nmf_meta')
    user_to_index = {u: i for i, u in enumerate(nmf_meta['user_ids'])} if nmf_meta else {}
    W = art.get('W')
    # load hybrid_item_matrix from file (large) - better to keep a memory-mapped array, but for example load from npy
    hybrid_path = os.path.join(getattr(settings, 'RECOMMENDER_ARTIFACT_DIR'), 'hybrid.npy')
    hybrid_item_matrix = None
    try:
        hybrid_item_matrix = np.load(hybrid_path)
    except Exception:
        # Not persisted in this scaffold; faiss index contains vectors for search directly
        pass

    # get a query vector
    q = None
    if user_to_index.get(user_id) is not None and W is not None:
        # simple user vector projection
        q = get_user_vector_ann(user_id, user_to_index, W,
                                hybrid_item_matrix if hybrid_item_matrix is not None else np.zeros(
                                    (1, NMF_COMPONENTS + SVD_COMPONENTS)))
    else:
        # fallback: build a centroid from user's listened episodes
        from apps.posts.podcasts.models import PlayBack
        pbs = PlayBack.objects.filter(user_id=user_id).values_list('episode_id', flat=True)[:200]
        if not pbs:
            return []
        # map episode ids to faiss IDs -> use hybrid_meta episode_ids list
        idx_map = {eid: i for i, eid in enumerate(hybrid_meta['episode_ids'])}
        ids = [idx_map[e] for e in pbs if e in idx_map]
        if not ids:
            return []
        # compute centroid by averaging the FAISS vectors via index reconstruct (if supported)
        vecs = []
        for _id in ids:
            try:
                vec = faiss_index.reconstruct(_id)
                vecs.append(vec)
            except Exception:
                continue
        if not vecs:
            return []
        q = np.mean(np.vstack(vecs), axis=0).astype('float32')
        q = q.reshape(1, -1)
        # normalize
        q = q / np.linalg.norm(q)

    # query faiss
    D, I = faiss_index.search(q, top_k + 10)  # +10 to allow filtering
    hits = []
    for idx in I[0]:
        if idx < 0:
            continue
        if idx < len(episode_ids):
            hits.append(episode_ids[idx])
        if len(hits) >= top_k:
            break
    return hits


def get_ann_recommendation(request):
    if not request.user.is_authenticated:
        return None
    cache_key = f"ann:recommend:episodes:{request.user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    ids = ann_recommend_for_user(request.user.id, top_k=12)
    # fetch minimal episode info
    eps = list(Episode.objects.filter(id__in=ids).values('id', 'title', 'slug', 'podcast_id'))
    # preserve order
    id_to_ep = {e['id']: e for e in eps}
    ordered = EpisodeListSerializer([id_to_ep.get(i) for i in ids if id_to_ep.get(i) is not None], many=True).data
    cache.set(cache_key, ordered, 300)  # 5min cache
    return ordered
