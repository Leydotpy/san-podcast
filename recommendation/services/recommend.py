from collections import defaultdict
from datetime import timedelta
from math import exp

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import (
    Case, When, Value, FloatField, ExpressionWrapper
)
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.analytics.models import ObjectView
from apps.posts.podcasts.models import PlayBack, Podcast


DECAY_TAU_DAYS = getattr(settings, "RECOMMEND_DECAY_TAU_DAYS", 30.0)  # tau for exponential decay
PLAY_WEIGHT = getattr(settings, "RECOMMEND_PLAY_WEIGHT", 1.0)
COMPLETION_WEIGHT = getattr(settings, "RECOMMEND_COMPLETION_WEIGHT", 3.0)
PODCAST_VIEW_WEIGHT = getattr(settings, "RECOMMEND_PODCAST_VIEW_WEIGHT", 0.5)


def _decay_weight(age_seconds, tau_days=DECAY_TAU_DAYS):
    # exponential decay, returns multiplier in (0,1]
    age_days = age_seconds / (3600 * 24)
    return exp(-age_days / tau_days)


# decay buckets (fast and simple; change multipliers to taste)
# (0-1 day): 1.0, (1-7 days): 0.6, (7-30 days): 0.3, (>30 days): 0.1
def _decay_case_for_field(ts_field_name):
    now = timezone.now()
    since_1d = now - timedelta(days=1)
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)

    # returns a Case expression to be used against a timestamp field name,
    # so usage will be: Case(When(**{f"{ts_field_name}__gte": since_1d}, then=Value(1.0)), ...)
    return [
        ({f"{ts_field_name}__gte": since_1d}, Value(1.0)),
        ({f"{ts_field_name}__gte": since_7d}, Value(0.6)),
        ({f"{ts_field_name}__gte": since_30d}, Value(0.3)),
    ]


def aggregated_playback_scores(lookback_days=90):
    """
    Returns a queryset-like list of dicts with keys:
      {'user_id': ..., 'category_id': ..., 'score': ...}
    Computed from PlayBack rows aggregated by episode -> episode.categories.
    """
    now = timezone.now()
    since = now - timedelta(days=lookback_days)

    # Build decay CASE for PlayBack.last_played_at
    decay_whens = _decay_case_for_field("last_played_at")
    decay_case = Case(
        *[When(**conds, then=val) for conds, val in decay_whens],
        default=Value(0.1),
        output_field=FloatField()
    )

    # per-row weight = (completion ? COMPLETION_WEIGHT : PLAY_WEIGHT) * decay_case
    row_weight_case = Case(
        When(is_completed=True, then=Value(COMPLETION_WEIGHT)),
        default=Value(PLAY_WEIGHT),
        output_field=FloatField()
    )
    signal_expr = ExpressionWrapper(row_weight_case * decay_case, output_field=FloatField())

    # Aggregate per user_id + episode__categories
    # This will create one row per (user, category) because episode__categories expands M2M
    pb_agg = (
        PlayBack.objects
        .filter(last_played_at__gte=since)
        .values("user_id", "episode__categories")
        .annotate(score=Coalesce(Sum(signal_expr), Value(0.0)))
        .values("user_id", "episode__categories", "score")
    )

    # Normalize keys: rename episode__categories -> category_id
    results = []
    for row in pb_agg:
        cat_id = row.get("episode__categories")
        if not cat_id:
            continue
        results.append({
            "user_id": row["user_id"],
            "category_id": cat_id,
            "score": float(row["score"]),
        })
    return results


def aggregated_podcast_view_scores(lookback_days=90):
    """
    Returns list of dicts: {'user_id':..., 'category_id':..., 'score': ...}
    Computed from Podcast.view_logs (ObjectView) aggregated by podcast.categories.
    """
    now = timezone.now()
    since = now - timedelta(days=lookback_days)

    # Build decay CASE for view_logs__timestamp
    decay_whens = _decay_case_for_field("view_logs__timestamp")
    decay_case = Case(
        *[When(**conds, then=val) for conds, val in decay_whens],
        default=Value(0.1),
        output_field=FloatField()
    )

    # view row weight = PODCAST_VIEW_WEIGHT * decay_case
    view_signal_expr = ExpressionWrapper(Value(PODCAST_VIEW_WEIGHT) * decay_case, output_field=FloatField())

    # Use Podcast.view_logs GenericRelation to group by view_logs__user_id and categories
    pv_agg = (
        Podcast.objects
        .filter(view_logs__timestamp__gte=since)
        .values("view_logs__user_id", "categories__id")
        .annotate(score=Coalesce(Sum(view_signal_expr), Value(0.0)))
        .values("view_logs__user_id", "categories__id", "score")
    )

    results = []
    for row in pv_agg:
        user_id = row.get("view_logs__user_id")
        cat_id = row.get("categories__id")
        if not user_id or not cat_id:
            continue
        results.append({
            "user_id": user_id,
            "category_id": cat_id,
            "score": float(row["score"]),
        })
    return results


def compute_user_category_affinity(user, lookback_days=90):
    """
    Returns {category_id: score} for the given user.
    Uses PlayBack (episode plays + completions) and Podcast ObjectView.
    """
    now = timezone.now()
    since = now - timedelta(days=lookback_days)

    # 1) Aggregate PlayBack per category via episode->categories
    # We'll iterate PlayBack rows and add per-category weighted scores.
    affinity = defaultdict(float)

    pb_qs = PlayBack.objects.filter(last_played_at__gte=since, user=user).select_related('episode')
    for pb in pb_qs.iterator():
        age_seconds = (now - pb.last_played_at).total_seconds()
        decay = _decay_weight(age_seconds)
        play_weight = 1.0 * decay
        completion_weight = 3.0 * decay if pb.is_completed else 0.0

        # episode may have categories and podcast has categories
        ep = pb.episode
        # episode categories
        for cat in ep.categories.all():
            affinity[cat.id] += play_weight + completion_weight
        # podcast categories (count them too)
        for cat in ep.podcast.categories.all():
            affinity[cat.id] += (0.5 * play_weight)  # smaller weight for podcast affiliation

    # 2) Add Podcast ObjectView signals (interest)
    podcast_ct = ContentType.objects.get_for_model(Podcast)
    views_qs = ObjectView.objects.filter(
        content_type=podcast_ct, user=user, timestamp__gte=since
    ).values('object_id', 'timestamp').order_by('-timestamp')

    for v in views_qs.iterator():
        # get podcast categories
        try:
            pod = Podcast.objects.get(pk=v['object_id'])
        except Podcast.DoesNotExist:
            continue
        age_seconds = (now - v['timestamp']).total_seconds()
        decay = _decay_weight(age_seconds)
        view_weight = 0.5 * decay
        for cat in pod.categories.all():
            affinity[cat.id] += view_weight

    return dict(affinity)
