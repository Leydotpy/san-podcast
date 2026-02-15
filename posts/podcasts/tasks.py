from celery import shared_task, Task
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import Episode, PlayBack

class BaseTaskWithRetry(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 5, "countdown": 10}
    retry_backoff = True
    acks_late = True


@shared_task(bind=True, base=BaseTaskWithRetry)
def recalc_episode_trending():
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    # Aggregate playback stats in one pass
    aggregates = (
        PlayBack.objects
        .filter(last_played_at__gte=since_7d)
        .values("episode_id")
        .annotate(
            plays_7d=Count("id"),
            plays_24h=Count("id", filter=Q(last_played_at__gte=since_24h)),
            completions=Count("id", filter=Q(is_completed=True)),
        )
    )

    agg_map = {a["episode_id"]: a for a in aggregates}

    episodes = Episode.objects.only("id", "trend_score")

    updates = []
    for ep in episodes:
        stats = agg_map.get(ep.id, {})
        score = (
            stats.get("plays_24h", 0) * 4.0 +
            stats.get("plays_7d", 0) * 1.5 +
            stats.get("completions", 0) * 2.0
        )
        ep.trend_score = score
        updates.append(ep)

    with transaction.atomic():
        Episode.objects.bulk_update(updates, ["trend_score"])

    return len(updates)
