import os
from datetime import timedelta

import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from scipy.sparse import csr_matrix
# sklearn
from sklearn.decomposition import NMF, TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

# faiss
try:
    import faiss
except Exception:
    faiss = None

# Django models
from apps.posts.podcasts.models import Episode, PlayBack

# Output paths (tune to your project)
ARTIFACT_DIR = getattr(settings, "RECOMMENDER_ARTIFACT_DIR")
os.makedirs(ARTIFACT_DIR, exist_ok=True)

NMF_COMPONENTS = getattr(settings, "NMF_COMPONENTS", 64)
SVD_COMPONENTS = getattr(settings, "SVD_COMPONENTS", 64)

LOOK_BACK_DAYS = getattr(settings, "SK_LOOK_BACK_DAYS", 365)
MIN_USER_INTERACTIONS = getattr(settings, "MIN_USER_INTERACTIONS", 3)

HYBRID_DIM = NMF_COMPONENTS + SVD_COMPONENTS


def _ensure_faiss():
    if faiss is None:
        raise RuntimeError("faiss is not installed. Install faiss-cpu or faiss-gpu to use ANN indexing.")


class Command(BaseCommand):
    help = "Train NMF (collaborative) and content (TF-IDF+SVD) models, build FAISS ANN index, and save artifacts."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Building interaction dataframe..."))
        now = timezone.now()
        since = now - timedelta(days=LOOK_BACK_DAYS)

        # Extract PlayBacks within lookback window
        pbs = PlayBack.objects.filter(last_played_at__gte=since).select_related('episode', 'user', 'episode__podcast')
        rows = []
        for pb in pbs.iterator():
            if not pb.user_id:
                continue  # skip anonymous; adapt if you want to include IP-based anonymous
            score = 1.0 + (3.0 if pb.is_completed else 0.0)
            rows.append({'user_id': pb.user_id, 'episode_id': pb.episode_id, 'score': score})
        if not rows:
            self.stdout.write(self.style.ERROR("No playback rows found in look back window. Nothing to train."))
            return

        df = pd.DataFrame(rows)
        df = df.groupby(['user_id', 'episode_id']).agg({'score': 'sum'}).reset_index()

        user_ids = df['user_id'].unique().tolist()
        episode_ids = df['episode_id'].unique().tolist()
        user_to_index = {u: i for i, u in enumerate(user_ids)}
        episode_to_index = {e: i for i, e in enumerate(episode_ids)}

        rows_idx = df['user_id'].map(user_to_index).to_numpy()
        cols_idx = df['episode_id'].map(episode_to_index).to_numpy()
        data = df['score'].to_numpy()

        user_item = csr_matrix((data, (rows_idx, cols_idx)), shape=(len(user_ids), len(episode_ids)))

        # Filter users with very few interactions
        user_counts = (user_item > 0).sum(axis=1).A1
        keep_user_mask = user_counts >= MIN_USER_INTERACTIONS
        kept_indices = np.where(keep_user_mask)[0]
        if len(kept_indices) == 0:
            self.stdout.write(self.style.ERROR("No users with enough interactions to train."))
            return
        user_item_filtered = user_item[kept_indices]
        user_ids_filtered = [user_ids[i] for i in kept_indices]

        # ------- Train NMF (Collaborative) -------
        self.stdout.write(self.style.NOTICE("Training NMF collaborative model..."))
        nmf = NMF(n_components=NMF_COMPONENTS, init='nndsvda', random_state=42, max_iter=300)
        W = nmf.fit_transform(user_item_filtered)  # users x k
        H = nmf.components_  # k x items

        # Persist nmf, metadata, and factors
        joblib.dump(nmf, os.path.join(ARTIFACT_DIR, 'nmf_model.joblib'))
        joblib.dump({'user_ids': user_ids_filtered, 'episode_ids': episode_ids},
                    os.path.join(ARTIFACT_DIR, 'nmf_meta.joblib'))
        np.save(os.path.join(ARTIFACT_DIR, 'W.npy'), W)
        np.save(os.path.join(ARTIFACT_DIR, 'H.npy'), H)

        # ------- Train content model (TF-IDF + SVD) -------
        self.stdout.write(self.style.NOTICE("Building TF-IDF corpus for episodes..."))
        ep_qs = Episode.objects.filter(id__in=episode_ids).select_related('podcast').prefetch_related('categories')
        ep_map = {e.id: e for e in ep_qs}
        corpus = []
        ep_order = []
        for eid in episode_ids:
            e = ep_map.get(eid)
            if not e:
                corpus.append("")
                ep_order.append(eid)
                continue
            tags = getattr(e, 'tags', '') or ''
            podcast_title = e.podcast.title if e.podcast else ''
            text = ' '.join(filter(None, [e.title or '', e.description or '', tags, podcast_title]))
            corpus.append(text)
            ep_order.append(eid)

        tf = TfidfVectorizer(max_features=20000, ngram_range=(1, 2))
        X_text = tf.fit_transform(corpus)

        self.stdout.write(self.style.NOTICE("Reducing text features with SVD..."))
        svd = TruncatedSVD(n_components=SVD_COMPONENTS, random_state=42)
        X_svd = svd.fit_transform(X_text)  # dense (n_items x SVD_COMPONENTS)

        # normalize
        X_svd = normalize(X_svd, axis=1)

        joblib.dump(tf, os.path.join(ARTIFACT_DIR, 'tfidf.joblib'))
        joblib.dump(svd, os.path.join(ARTIFACT_DIR, 'svd.joblib'))
        joblib.dump({'episode_order': ep_order}, os.path.join(ARTIFACT_DIR, 'content_meta.joblib'))
        np.save(os.path.join(ARTIFACT_DIR, 'X_svd.npy'), X_svd)

        # ------- Build hybrid item vectors (concat item_factors + content SVD) -------
        self.stdout.write(self.style.NOTICE("Building hybrid item vectors and FAISS index..."))
        # H: k x n_items -> item_factors = H.T (n_items x k)
        item_factors = H.T  # shape (n_items, NMF_COMPONENTS)

        # Align item_factors rows with ep_order (episode_ids). Our nmf used 'episode_ids' order
        # item_factors currently correspond to episode_ids order used earlier.

        # Ensure same length
        assert item_factors.shape[0] == len(episode_ids)
        assert X_svd.shape[0] == len(ep_order)

        hybrid = np.hstack([item_factors, X_svd])  # shape (n_items, HYBRID_DIM)
        # normalize vectors for cosine/inner-product search
        hybrid = normalize(hybrid, axis=1).astype('float32')

        # Build FAISS index (HNSW flat, inner product) for ANN
        _ensure_faiss()
        d = hybrid.shape[1]
        index = faiss.IndexHNSWFlat(d, 32)  # M=32; tune
        index.hnsw.efConstruction = 200
        index.verbose = True
        # use inner product -> since vectors normalized, inner product ~ cosine
        faiss.normalize_L2(hybrid)
        index.add(hybrid)

        faiss.write_index(index, os.path.join(ARTIFACT_DIR, 'faiss_index.ivf'))
        joblib.dump({'episode_ids': episode_ids, 'user_ids': user_ids_filtered},
                    os.path.join(ARTIFACT_DIR, 'hybrid_meta.joblib'))

        self.stdout.write(self.style.SUCCESS("Training complete. Artifacts written to %s" % ARTIFACT_DIR))
