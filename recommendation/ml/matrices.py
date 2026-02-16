from datetime import timedelta

import joblib
import numpy as np
import pandas as pd
from django.utils import timezone
from scipy.sparse import csr_matrix
from scipy.sparse import hstack
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

from apps.posts.podcasts.models import Episode, PlayBack

# lookback window
LOOKBACK_DAYS = 365

since = timezone.now() - timedelta(days=LOOKBACK_DAYS)

# Pull PlayBack rows in lookback window
pb_qs = PlayBack.objects.filter(last_played_at__gte=since).select_related('episode', 'user', 'episode__podcast')
# Convert to DataFrame
rows = []
for pb in pb_qs.iterator():
    user_id = pb.user_id or 0  # decide how to treat anonymous plays
    episode_id = pb.episode_id
    # scoring rule (you can tune): base play = 1, completion bonus = +3
    score = 1.0 + (3.0 if pb.is_completed else 0.0)
    rows.append({'user_id': user_id, 'episode_id': episode_id, 'score': score, 'last_played_at': pb.last_played_at})
df = pd.DataFrame(rows)

# Aggregate by (user, episode) in case multiple rows exist
interactions = df.groupby(['user_id', 'episode_id']).agg({
    'score': 'sum',
    'last_played_at': 'max'
}).reset_index()

# index mappings
user_ids = interactions['user_id'].unique().tolist()
episode_ids = interactions['episode_id'].unique().tolist()
user_to_index = {u: i for i, u in enumerate(user_ids)}
episode_to_index = {e: i for i, e in enumerate(episode_ids)}

rows = interactions['user_id'].map(user_to_index).to_numpy()
cols = interactions['episode_id'].map(episode_to_index).to_numpy()
data = interactions['score'].to_numpy()

user_item = csr_matrix((data, (rows, cols)), shape=(len(user_ids), len(episode_ids)))

n_components = 50  # tune
nmf = NMF(n_components=n_components, init='nndsvda', random_state=42, max_iter=200)
# Fit: returns W (users x n_components)
W = nmf.fit_transform(user_item)  # dense array (n_users x k)
H = nmf.components_  # (k x n_items)  -> item_factors = H.T

# Save model and metadata for later use
joblib.dump(nmf, 'models/nmf_model.joblib')
joblib.dump({'user_ids': user_ids, 'episode_ids': episode_ids}, 'models/nmf_meta.joblib')

# Build item metadata corpus
episodes = Episode.objects.select_related('podcast').prefetch_related('categories').all()
ep_rows = []
cat_ids = set()
for e in episodes:
    tags = getattr(e, 'tags', '') or ''
    podcast_title = e.podcast.title if e.podcast else ''
    text = ' '.join(filter(None, [e.title or '', e.description or '', tags, podcast_title]))
    cats = [c.id for c in e.categories.all()] + [c.id for c in (e.podcast.categories.all() if e.podcast else [])]
    ep_rows.append({'episode_id': e.id, 'text': text, 'cats': cats})
    cat_ids.update(cats)
cat_list = sorted(cat_ids)
cat_to_index = {c: i for i, c in enumerate(cat_list)}

corpus = [r['text'] for r in ep_rows]
tf = TfidfVectorizer(max_features=20000, ngram_range=(1, 2))
X_text = tf.fit_transform(corpus)  # sparse (n_items x features)

# category one-hot sparse matrix
from scipy.sparse import csr_matrix

rows, cols, vals = [], [], []
for i, r in enumerate(ep_rows):
    for c in r['cats']:
        rows.append(i)
        cols.append(cat_to_index[c])
        vals.append(1.0)
X_cat = csr_matrix((vals, (rows, cols)), shape=(len(ep_rows), len(cat_list)))

# combine features (text + category)
X_item = hstack([X_text, X_cat], format='csr')

# build NearestNeighbors index
nn = NearestNeighbors(n_neighbors=50, metric='cosine', algorithm='brute')
nn.fit(X_item)
joblib.dump(nn, 'models/nn_item.joblib')
joblib.dump(tf, 'models/tfidf.joblib')
joblib.dump({'ep_order': [r['episode_id'] for r in ep_rows], 'cat_list': cat_list}, 'models/content_meta.joblib')


def recommend_episodes_cf(user_id, top_k=20):
    meta = joblib.load('models/nmf_meta.joblib')
    nmf = joblib.load('models/nmf_model.joblib')
    user_ids = meta['user_ids']
    episode_ids = meta['episode_ids']
    if user_id not in user_to_index:
        return []  # cold start fallback elsewhere

    u_idx = user_to_index[user_id]
    # Recompute W for the entire matrix? better to persist W as well:
    W = nmf.transform(user_item)  # (n_users x k) - faster if stored
    user_vec = W[u_idx]  # (k,)

    # Scores = user_vec dot H  -> H shape (k x n_items)
    scores = user_vec.dot(nmf.components_)  # (n_items,)
    # mask already-seen items
    seen_cols = user_item[u_idx].nonzero()[1]
    scores[seen_cols] = -np.inf

    top_idx = np.argpartition(-scores, range(top_k))[:top_k]
    top_sorted = top_idx[np.argsort(-scores[top_idx])]
    return [episode_ids[i] for i in top_sorted]


def recommend_episodes_content(user_id, top_k=20):
    meta = joblib.load('models/content_meta.joblib')
    nn = joblib.load('models/nn_item.joblib')
    tf = joblib.load('models/tfidf.joblib')
    ep_order = meta['ep_order']  # episode_id list aligned with X_item rows
    ep_index = {eid: i for i, eid in enumerate(ep_order)}

    # get episodes user listened to (PlayBack)
    pbs = PlayBack.objects.filter(user_id=user_id).values_list('episode_id', flat=True)
    listened = [ep_index[eid] for eid in pbs if eid in ep_index]
    if not listened:
        return []  # fallback to category/popular

    # load X_item (or access it from global if persisted)
    # For memory efficiency you may reload X_item from disk; here we assume X_item in scope
    listened_vectors = X_item[listened]
    user_vector = listened_vectors.mean(axis=0)  # centroid (sparse)
    distances, indices = nn.kneighbors(user_vector, n_neighbors=top_k + len(listened))
    results = []
    for idx in indices[0]:
        eid = ep_order[idx]
        if eid not in pbs:
            results.append(eid)
        if len(results) >= top_k:
            break
    return results


def recommend_hybrid(user_id, k=20, alpha=0.7):
    # alpha: weight for CF (0..1), (1-alpha) for content
    cf_list = recommend_episodes_cf(user_id, top_k=500)  # returns episode ids ranked by CF
    content_list = recommend_episodes_content(user_id, top_k=500)

    # build score dicts
    cf_scores = {eid: (len(cf_list) - i) for i, eid in enumerate(cf_list)}
    content_scores = {eid: (len(content_list) - i) for i, eid in enumerate(content_list)}

    all_eids = set(cf_scores) | set(content_scores)
    combined = []
    for eid in all_eids:
        s_cf = cf_scores.get(eid, 0)
        s_ct = content_scores.get(eid, 0)
        score = alpha * s_cf + (1 - alpha) * s_ct
        combined.append((eid, score))
    combined.sort(key=lambda x: x[1], reverse=True)
    return [eid for eid, _ in combined[:k]]
