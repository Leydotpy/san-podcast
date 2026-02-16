import json
from django.core.cache import cache
from django.conf import settings

# TTL (seconds)
RECOMMEND_TTL = getattr(settings, "RECOMMEND_CACHE_TTL", 600)  # 10 minutes default

def _podcasts_key(user_id):
    return f"recommend:podcasts:{user_id}"

def _episodes_key(user_id):
    return f"recommend:episodes:{user_id}"

def get_cached_recommendations(user_id, kind="podcasts"):
    key = _podcasts_key(user_id) if kind == "podcasts" else _episodes_key(user_id)
    payload = cache.get(key)
    if not payload:
        return None
    try:
        return json.loads(payload)
    except Exception:
        return None

def set_cached_recommendations(user_id, kind="podcasts", data=None, ttl=RECOMMEND_TTL):
    key = _podcasts_key(user_id) if kind == "podcasts" else _episodes_key(user_id)
    payload = json.dumps(data or [])
    cache.set(key, payload, ttl)

def invalidate_user_recommendations(user_id):
    cache.delete(_podcasts_key(user_id))
    cache.delete(_episodes_key(user_id))
