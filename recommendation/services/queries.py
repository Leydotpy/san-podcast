from django.db.models import Sum
from django.db.models import Q
from django.utils import timezone

from api.rest.web.apps.podcasts.serializers import PodcastListSerializer, EpisodeListSerializer
from apps.posts.podcasts.models import Podcast, Episode, PlayBack
from apps.posts.podcasts.queries import trending_podcasts, trending_episodes

from ..models import UserCategoryAffinity
from ..cache import get_cached_recommendations, set_cached_recommendations

from .recommend import compute_user_category_affinity


def recommend_episodes_for_user(user, limit=30, lookback_days=90):
    affinity = compute_user_category_affinity(user, lookback_days=lookback_days)
    now = timezone.now()
    if not affinity:
        # fallback
        return trending_episodes(limit=limit)

    # choose top categories
    top_cats = sorted(affinity.items(), key=lambda kv: kv[1], reverse=True)[:6]
    top_cat_ids = [c for c, _ in top_cats]

    # candidate pool: recent episodes in those categories, plus from subscribed podcasts
    qs = Episode.objects.filter(
        Q(categories__id__in=top_cat_ids) | Q(podcast__categories__id__in=top_cat_ids)
    ).select_related('podcast').prefetch_related('categories').distinct()

    # exclude episodes user already completed recently (optional)
    played_episode_ids = PlayBack.objects.filter(user=user).values_list('episode_id', flat=True)
    qs = qs.exclude(id__in=played_episode_ids)

    # score episodes
    candidates = list(qs.order_by('-timestamp')[:100])  # a candidate pool you can tune
    scored = []
    for ep in candidates:
        cat_score = sum(affinity.get(cat.id, 0.0) for cat in ep.categories.all())
        cat_score += sum(0.5 * affinity.get(cat.id, 0.0) for cat in ep.podcast.categories.all())

        # recency factor (days)
        age_days = (now - ep.timestamp).total_seconds() / (3600 * 24)
        recency_factor = max(0.0, 1.0 - (age_days / 30.0))  # linear decay over 30 days

        trend = getattr(ep, 'trend_score', 0.0)
        playcount_longterm = getattr(ep, 'view_count', 0)  # or play_count if you added it

        total = (cat_score * 1.2) + (trend * 0.8) + (recency_factor * 2.0) + (playcount_longterm * 0.01)
        scored.append((ep, total))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [e for e, _ in scored[:limit]]


def recommend_podcasts_for_user(user, limit=20):
    affinities = UserCategoryAffinity.objects.filter(user=user).order_by('-score')[:8]
    cat_ids = [a.category_id for a in affinities]
    if not cat_ids:
        # fallback to trending
        return trending_podcasts(limit=limit)

    # candidates: podcasts in those categories
    qs = Podcast.objects.filter(categories__id__in=cat_ids).annotate(
        cat_match_score=Sum('categories__id')  # placeholder; compute properly below
    ).distinct()

    # Simpler: compute final scores in Python by fetching required fields
    podcasts = list(qs.select_related('image').prefetch_related('categories')[:200])
    cat_score_map = {a.category_id: a.score for a in affinities}
    scored = []
    for p in podcasts:
        cat_score = sum(cat_score_map.get(c.id, 0.0) for c in p.categories.all())
        total = cat_score + (getattr(p, 'view_count', 0) * 0.001) + (getattr(p, 'trend_score', 0) * 0.5)
        scored.append((p, total))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored[:limit]]


def get_recommended_podcast_payload(user):
    cached = get_cached_recommendations(user.id, kind="podcasts")
    if cached is not None:
        return cached
    recs = recommend_podcasts_for_user(user)
    payload = [ {"id": p.id, "title": p.title, "slug": p.slug, "image": p.image.url if p.image else None} for p in recs ]
    set_cached_recommendations(user.id, kind="podcasts", data=payload)
    return payload


def recommend_podcasts_for_user_cached(user, limit=20):
    """Check cache; if miss compute using UserCategoryAffinity table and set cache."""
    cached = get_cached_recommendations(user.id, kind="podcasts")
    if cached is not None:
        return cached

    # Fetch top categories for user
    affinities = UserCategoryAffinity.objects.filter(user=user).order_by("-score")[:8]
    cat_ids = [a.category_id for a in affinities]
    if not cat_ids:
        # fallback: trending podcasts - implement or import
        from apps.posts.podcasts.queries import trending_podcasts
        pods = trending_podcasts(limit=limit)
        # payload = [serialize_podcast(p) for p in pods]
        payload = PodcastListSerializer(pods, many=True).data
        set_cached_recommendations(user.id, kind="podcasts", data=payload)
        return payload

    # candidates
    qs = Podcast.objects.filter(categories__id__in=cat_ids).distinct().prefetch_related("categories")[:200]
    cat_map = {a.category_id: a.score for a in affinities}
    scored = []
    for p in qs:
        cat_score = sum(cat_map.get(c.id, 0.0) for c in p.categories.all())
        total = cat_score + (getattr(p, "view_count", 0) * 0.001) + (getattr(p, "trend_score", 0) * 0.5)
        scored.append((p, total))
    scored.sort(key=lambda x: x[1], reverse=True)
    # payload = [serialize_podcast(p) for p, _ in scored[:limit]]
    qs = [p for _, p in scored[:limit]]
    payload = PodcastListSerializer(qs, many=True).data
    set_cached_recommendations(user.id, kind="podcasts", data=payload)
    return payload


def recommend_episodes_for_user_cached(user, limit=30):
    cached = get_cached_recommendations(user.id, kind="episodes")
    if cached is not None:
        return cached

    affinities = UserCategoryAffinity.objects.filter(user=user).order_by("-score")[:8]
    cat_ids = [a.category_id for a in affinities]
    if not cat_ids:
        from apps.posts.podcasts.queries import trending_episodes
        eps = trending_episodes(limit=limit)
        # payload = [serialize_episode(e) for e in eps]
        payload = EpisodeListSerializer(eps, many=True).data
        set_cached_recommendations(user.id, kind="episodes", data=payload)
        return payload

    cat_map = {a.category_id: a.score for a in affinities}
    qs = Episode.objects.filter(categories__id__in=cat_ids).select_related("podcast").prefetch_related("categories") \
        .order_by("-timestamp").distinct()[:200]
    scored = []
    from django.utils import timezone
    now = timezone.now()
    for e in qs:
        cat_score = sum(cat_map.get(c.id, 0.0) for c in e.categories.all())
        cat_score += sum(0.5 * cat_map.get(c.id, 0.0) for c in e.podcast.categories.all())
        age_days = (now - e.timestamp).total_seconds() / (3600 * 24)
        recency_factor = max(0.0, 1.0 - (age_days / 30.0))
        total = (cat_score * 1.2) + (getattr(e, "trend_score", 0.0) * 0.8) + (recency_factor * 2.0) + (
                    getattr(e, "view_count", 0) * 0.01)
        scored.append((e, total))
    scored.sort(key=lambda x: x[1], reverse=True)
    # payload = [serialize_episode(e) for e, _ in scored[:limit]]
    qs = [e for e, _ in scored[:limit]]
    payload = EpisodeListSerializer(qs, many=True).data
    set_cached_recommendations(user.id, kind="episodes", data=payload)
    return payload