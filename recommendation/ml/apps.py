from django.apps import AppConfig

class MLRecommendationConfig(AppConfig):
    name = 'apps.recommendation.ml'
    label = 'ml'

    def ready(self):
        # Load heavy artifacts once at startup so views can reuse them
        try:
            from .utils import load_nmf, load_content, load_faiss_index
            nmf, nmf_meta, W, H = load_nmf()
            tf, svd, content_meta, X_svd = load_content()
            faiss_index, hybrid_meta = load_faiss_index()

            # store on module for easy import
            import sys
            sys.modules.setdefault('recommendation._ARTIFACTS', {})
            a = sys.modules['recommendation._ARTIFACTS']
            a['nmf'] = nmf
            a['nmf_meta'] = nmf_meta
            a['W'] = W
            a['H'] = H
            a['tf'] = tf
            a['svd'] = svd
            a['content_meta'] = content_meta
            a['X_svd'] = X_svd
            a['faiss_index'] = faiss_index
            a['hybrid_meta'] = hybrid_meta

            print("ML Recommender artifacts loaded into memory")
        except Exception as exc:
            # Log fail but don't crash import; it's okay if artifacts are missing during development
            print("Warning: failed loading recommender artifacts on startup:", exc)

